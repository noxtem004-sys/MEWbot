"""
MeowBotRuntime: the real backend, wrapped so a GUI can Start/Stop it as many
times as it likes within one process (no sys.exit, no process-per-run).

Responsible for:
- the aiogram Bot/Dispatcher (admin panel)
- the MeowUserClient (Telethon automation)
- the three background schedulers
- a clean, awaitable start() / stop() lifecycle
- routing Telethon's interactive login through GUI-supplied async callables
  instead of input()

Nothing here touches Qt. The GUI layer (gui/) depends on this module, never
the other way around.
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Callable, Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from database import init_db
from handlers.admin import router as admin_router
from handlers.start import router as start_router
from user_client import MeowUserClient

logger = logging.getLogger(__name__)


class Status(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    NEED_LOGIN = "need_login"
    RUNNING = "running"
    ERROR = "error"


class MeowBotRuntime:
    def __init__(self, config):
        self.config = config
        self.user_client = MeowUserClient(config)

        self._bot: Optional[Bot] = None
        self._dp: Optional[Dispatcher] = None
        self._tasks: list[asyncio.Task] = []
        self._polling_task: Optional[asyncio.Task] = None

        self.status: Status = Status.STOPPED
        self.on_status_changed: Optional[Callable[[Status], None]] = None
        # Called with "phone" | "code" | "password" when the GUI needs to
        # show the corresponding input field right now.
        self.on_login_required: Optional[Callable[[str], None]] = None

        self._pending_phone: Optional[asyncio.Future] = None
        self._pending_code: Optional[asyncio.Future] = None
        self._pending_password: Optional[asyncio.Future] = None

        # True while a deliberate stop() is in progress, so _run_polling and
        # _connect_with_retry know not to treat it as an unexpected failure.
        self._stopping: bool = False
        # Values of CRITICAL_KEYS_RESTART at the moment we last started, so
        # MainWindow can detect when a Settings save needs a soft-restart.
        self._active_critical_snapshot: dict = {}

        # The asyncio.Task currently running start() (if any). stop() cancels
        # this directly instead of relying only on the _stopping flag, which
        # otherwise races: _stop_internal() clears _stopping as soon as ITS
        # own (fast) teardown finishes, which can be well before a
        # concurrently-sleeping _connect_with_retry() ever wakes up to check
        # it -- leaving that retry loop looping forever, immune to Stop.
        self._start_task: Optional[asyncio.Task] = None
        # The asyncio.Task running _auto_recover() (if any), so stop() can
        # cancel it -- otherwise an auto-recover from an old crash can fire
        # after a fresh, legitimate restart and tear it down unexpectedly.
        self._auto_recover_task: Optional[asyncio.Task] = None
        # Bumped every time start() begins a new attempt. _auto_recover()
        # captures this and refuses to act if it's changed by the time its
        # backoff elapses -- belt-and-suspenders against the race above.
        self._generation: int = 0

    # -- status -------------------------------------------------------------
    def _set_status(self, s: Status) -> None:
        self.status = s
        if self.on_status_changed:
            self.on_status_changed(s)

    @property
    def is_running(self) -> bool:
        return self.status == Status.RUNNING

    # -- login providers (awaited from user_client.start) --------------------
    async def _ask_phone(self) -> str:
        loop = asyncio.get_running_loop()
        self._pending_phone = loop.create_future()
        if self.on_login_required:
            self.on_login_required("phone")
        return await self._pending_phone

    async def _ask_code(self) -> str:
        loop = asyncio.get_running_loop()
        self._pending_code = loop.create_future()
        if self.on_login_required:
            self.on_login_required("code")
        return await self._pending_code

    async def _ask_password(self) -> str:
        loop = asyncio.get_running_loop()
        self._pending_password = loop.create_future()
        if self.on_login_required:
            self.on_login_required("password")
        return await self._pending_password

    # Called by the GUI's login dialog when the user submits a field.
    def submit_phone(self, value: str) -> None:
        if self._pending_phone and not self._pending_phone.done():
            self._pending_phone.set_result(value)

    def submit_code(self, value: str) -> None:
        if self._pending_code and not self._pending_code.done():
            self._pending_code.set_result(value)

    def submit_password(self, value: str) -> None:
        if self._pending_password and not self._pending_password.done():
            self._pending_password.set_result(value)

    def cancel_login(self) -> None:
        for fut in (self._pending_phone, self._pending_code, self._pending_password):
            if fut and not fut.done():
                fut.cancel()

    # -- lifecycle -----------------------------------------------------------
    async def start(self) -> bool:
        if self.status in (Status.STARTING, Status.RUNNING):
            logger.warning("برنامه از قبل در حال اجراست.")
            return True

        problems = self.config.validate()
        if problems:
            logger.error("امکان اجرای برنامه وجود ندارد.")
            for p in problems:
                logger.error(f"• {p}")
            self._set_status(Status.ERROR)
            return False

        self._stopping = False
        self._generation += 1
        self._start_task = asyncio.current_task()
        self._set_status(Status.STARTING)
        logger.info("در حال بررسی تنظیمات...")

        try:
            return await self._start_body()
        except asyncio.CancelledError:
            # stop() cancelled us directly (see _stop_internal) -- it owns
            # the status/teardown, so just let the cancellation propagate.
            raise
        except Exception as e:
            # Anything unexpected here (e.g. a malformed BOT_TOKEN raising
            # aiogram's TokenValidationError synchronously) must not leave
            # the app stuck at STARTING with no feedback in the GUI.
            logger.error(f"خطای غیرمنتظره هنگام شروع: {e}")
            if self.status != Status.STOPPED:
                self._set_status(Status.ERROR)
            return False
        finally:
            if self._start_task is asyncio.current_task():
                self._start_task = None

    async def _start_body(self) -> bool:
        try:
            await init_db()
            logger.info("پایگاه داده آماده شد.")
        except Exception as e:
            logger.error(f"راه‌اندازی پایگاه داده ناموفق بود: {e}")
            self._set_status(Status.ERROR)
            return False

        self._bot = Bot(
            token=str(self.config.get("BOT_TOKEN")),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._dp = Dispatcher(storage=MemoryStorage())
        self._dp.include_router(admin_router)
        self._dp.include_router(start_router)
        # Dependency injection: handlers declare `config` / `user_client`
        # parameters and aiogram supplies them from here automatically.
        self._dp["config"] = self.config
        self._dp["user_client"] = self.user_client

        logger.info("در حال اتصال...")
        connected = await self._connect_with_retry()
        if not connected:
            if self.status != Status.STOPPED:  # don't clobber a legit Stop
                self._set_status(Status.ERROR)
            return False

        self._start_tasks_and_polling()
        self._active_critical_snapshot = self.config.snapshot_critical()
        logger.log(25, "برنامه با موفقیت اجرا شد.")
        self._set_status(Status.RUNNING)
        return True

    async def _connect_with_retry(self) -> bool:
        """Recovered behaviour from an earlier prototype (runtime.pyc — see
        AUDIT.md): on a transient/network-ish failure, retry every 5s
        instead of giving up immediately. Non-transient failures (bad
        code/password, no login UI) are NOT retried — that would either
        spam Telegram or silently re-prompt the user; those surface as an
        error and require pressing Start again. Cancellable via stop()."""
        while True:
            connected = await self.user_client.start(
                phone_provider=self._ask_phone,
                code_provider=self._ask_code,
                password_provider=self._ask_password,
            )
            if connected:
                return True
            if not self.user_client.last_failure_transient:
                logger.error("اتصال حساب کاربری ناموفق بود.")
                return False
            if self._stopping:
                return False
            logger.warning("اتصال ناموفق بود. تلاش مجدد تا ۵ ثانیه دیگر...")
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return False
            if self._stopping:
                return False

    def _start_tasks_and_polling(self) -> None:
        self._tasks = [
            asyncio.create_task(self.user_client.run_meow_toggle_scheduler()),
            asyncio.create_task(self.user_client.run_auto_meow_scheduler()),
            asyncio.create_task(self.user_client.run_cat_scheduler()),
            asyncio.create_task(self.user_client.run_fish_scheduler()),
        ]
        logger.info("زمان‌بندها فعال شدند: تعویض متن + میو + گربه + ماهی")
        self._polling_task = asyncio.create_task(self._run_polling())

    async def _run_polling(self) -> None:
        try:
            await self._dp.start_polling(self._bot, handle_signals=False)
            if not self._stopping:
                # Recovered behaviour from the earlier prototype: polling
                # ending on its own (not via our cancellation) means aiogram
                # gave up — auto-recover rather than silently going dark.
                logger.warning("پنل ادمین به‌طور غیرمنتظره متوقف شد. تلاش برای راه‌اندازی مجدد تا ۳ ثانیه دیگر...")
                self._spawn_auto_recover()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self._stopping:
                logger.error(f"خطای پنل ادمین (polling): {e}")
                self._spawn_auto_recover()

    def _spawn_auto_recover(self) -> None:
        # Never stack a second recovery attempt on top of one already
        # pending -- avoids duplicate schedulers/clients if polling somehow
        # fails twice in quick succession.
        if self._auto_recover_task and not self._auto_recover_task.done():
            return
        self._auto_recover_task = asyncio.create_task(self._auto_recover(self._generation))

    async def _auto_recover(self, generation: int) -> None:
        try:
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            return
        if self._stopping or self.status != Status.RUNNING or generation != self._generation:
            # Either a deliberate Stop happened, or a fresh start()/restart
            # already superseded the session this recovery was meant for.
            return
        logger.info("در حال راه‌اندازی مجدد سرویس‌ها...")
        # Must hand back Status.STOPPED (not STARTING) here: start()'s own
        # guard refuses to run while status is already STARTING/RUNNING, so
        # passing STARTING would make the following start() call a silent
        # no-op that just returns True without reconnecting anything.
        await self._stop_internal(final_status=Status.STOPPED)
        if generation != self._generation:
            return  # something else started in the meantime; don't fight it
        await self.start()

    async def soft_restart(self, reason: str = "") -> None:
        """Stop and start again in place — used when a critical setting
        (API/token/session) changes while the bot is running. Recovered
        concept from the earlier prototype's settings watcher."""
        if reason:
            logger.log(25, f"تنظیمات حیاتی تغییر کرد ({reason}) -> راه‌اندازی مجدد نرم.")
        else:
            logger.log(25, "راه‌اندازی مجدد نرم آغاز شد.")
        was_running = self.status in (Status.RUNNING, Status.STARTING, Status.NEED_LOGIN)
        await self.stop()
        if was_running:
            await self.start()

    async def apply_settings_change(self) -> None:
        """Call this right after Settings are saved. If the bot isn't
        running, this is a no-op — new values are simply read next Start.
        If it IS running and a CRITICAL_KEYS_RESTART field changed, the
        old connection is now using stale credentials/session, so this
        triggers a soft-restart automatically."""
        if self.status not in (Status.RUNNING, Status.STARTING, Status.NEED_LOGIN):
            return
        changed = self.config.critical_keys_changed(self._active_critical_snapshot)
        if changed:
            await self.soft_restart(reason=", ".join(sorted(changed)))

    async def stop(self) -> None:
        if self.status == Status.STOPPED:
            return
        self._stopping = True
        await self._stop_internal(final_status=Status.STOPPED)

    async def _stop_internal(self, final_status: Status) -> None:
        logger.info("در حال توقف برنامه...")
        self.cancel_login()

        # Directly cancel an in-flight start() (e.g. stuck in
        # _connect_with_retry's backoff sleep) instead of only setting
        # _stopping and hoping it notices in time. A cooperative flag alone
        # races here: this function can finish its own teardown (fast, since
        # there may be nothing to tear down yet) and — for a full stop()
        # only — reset _stopping back to False before that other coroutine
        # ever wakes up to check it, leaving it retrying forever, immune to
        # Stop. Cancellation is immediate and unambiguous.
        if self._start_task and not self._start_task.done() and self._start_task is not asyncio.current_task():
            self._start_task.cancel()
            try:
                await self._start_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"start() در حال لغو با خطای دیگری پایان یافت: {e}")

        if self._auto_recover_task and not self._auto_recover_task.done():
            self._auto_recover_task.cancel()
            try:
                await self._auto_recover_task
            except asyncio.CancelledError:
                pass
            self._auto_recover_task = None

        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []

        if self._polling_task:
            if self._dp:
                try:
                    self._dp.stop_polling()
                except Exception:
                    pass
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None

        await self.user_client.disconnect()

        if self._bot:
            await self._bot.session.close()
            self._bot = None

        logger.info("برنامه متوقف شد.")
        self._set_status(final_status)
        if final_status == Status.STOPPED:
            self._stopping = False
