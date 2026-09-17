"""
Telethon User Client (refactored for GUI integration).

Behavioural logic is unchanged from the original project:
- auto 'میو'
- 'انتقال میویی X'
- auto 'گربه' -> collect -> extract amount -> bank deposit -> confirm
- auto 'ماهی' -> click 'بده پیشی' after a delay

What changed vs. the original:
- All values come from a ConfigManager instance (core/config_manager.py)
  instead of module-level constants imported from config.py.
- start_user_client() no longer calls input(). Phone / verification code /
  2FA password are obtained through async "provider" callables supplied by
  the caller (the GUI's login dialog), so this module has zero terminal
  dependency and zero UI dependency of its own.
- Nothing sensitive (phone, code, password, API hash) is ever passed to
  logger calls.
"""
import asyncio
import logging
import random
import re
from typing import Awaitable, Callable, Optional, Tuple

# Recovered from an earlier prototype (settings_store.pyc — see AUDIT.md):
# the auto-meow text alternates between two configurable values on its own
# timer, independent of the send interval. Falls back to AUTO_MEOW_TEXT_A
# ("میو") if nothing has toggled yet.

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

logger = logging.getLogger(__name__)

# Async callables the GUI provides at start() time.
PhoneProvider = Callable[[], Awaitable[str]]
CodeProvider = Callable[[], Awaitable[str]]
PasswordProvider = Callable[[], Awaitable[str]]


class MeowUserClient:
    """Owns the Telethon client + all game-automation actions for one config."""

    def __init__(self, config):
        self.config = config
        self._client: Optional[TelegramClient] = None
        self._is_connected = False
        self._action_lock = asyncio.Lock()
        self._game_bot_id: Optional[int] = None
        self._current_meow_text: Optional[str] = None  # set by run_meow_toggle_scheduler
        # True when the last start() failure looks transient/network-related
        # (safe to blindly retry); False when it needs new user input (bad
        # code/password, no login UI available) and retrying blindly would
        # just re-prompt the user or hammer Telegram. See bot_core.py.
        self.last_failure_transient: bool = False

    # -- config convenience -------------------------------------------------
    def _cfg(self, key: str):
        return self.config.get(key)

    def _client_or_raise(self) -> TelegramClient:
        if self._client is None:
            raise RuntimeError("Telethon client not created yet")
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def build_client(self) -> TelegramClient:
        if self._client is None:
            self._client = TelegramClient(
                self.config.session_path(),
                int(self._cfg("API_ID")),
                str(self._cfg("API_HASH")),
                system_version="4.16.30-vxCUSTOM",
            )
        return self._client

    async def _resolve_game_bot_id(self) -> Optional[int]:
        if self._game_bot_id is not None:
            return self._game_bot_id
        username = self._cfg("GAME_BOT_USERNAME")
        if not username:
            return None
        try:
            ent = await self._client_or_raise().get_entity(username)
            self._game_bot_id = ent.id
            return self._game_bot_id
        except Exception as e:
            logger.warning(f"شناسایی ربات بازی ناموفق بود: {e}")
            return None

    # -- connection / auth ----------------------------------------------------
    async def start(
        self,
        phone_provider: Optional[PhoneProvider] = None,
        code_provider: Optional[CodeProvider] = None,
        password_provider: Optional[PasswordProvider] = None,
    ) -> bool:
        """Connect and, if needed, run the interactive login via the given
        async providers instead of input(). Returns True on success."""
        client = self.build_client()
        self.last_failure_transient = False
        try:
            await client.connect()

            if not await client.is_user_authorized():
                logger.info("نیاز به ورود اولیه است.")
                if phone_provider is None or code_provider is None:
                    logger.error("اطلاعات ورود در دسترس نیست (رابط کاربری ورود فراهم نشده).")
                    self.last_failure_transient = False
                    return False

                phone = (await phone_provider()).strip()
                try:
                    await client.send_code_request(phone)
                except Exception as e:
                    logger.error(f"ارسال کد تایید ناموفق بود: {e}")
                    self.last_failure_transient = True  # network/API issue, safe to retry
                    return False

                code = (await code_provider()).strip()
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    if password_provider is None:
                        logger.error("رمز دومرحله‌ای لازم است اما رابط ورود آن فراهم نشده.")
                        self.last_failure_transient = False
                        return False
                    password = (await password_provider()).strip()
                    await client.sign_in(password=password)
                except (PhoneCodeInvalidError, PhoneCodeExpiredError):
                    logger.error("کد تایید نامعتبر یا منقضی شده است.")
                    self.last_failure_transient = False  # needs a fresh code from the user, don't auto-retry
                    return False

                logger.log(25, "ورود با موفقیت انجام شد.")  # SUCCESS level

            me = await client.get_me()
            display = me.first_name or (me.username or "")
            logger.log(25, f"اتصال حساب کاربری برقرار شد: {display}")
            self._is_connected = True
            await self._resolve_game_bot_id()
            return True

        except FloodWaitError as e:
            logger.error(f"محدودیت ارسال (Flood Wait): {e.seconds} ثانیه صبر کنید.")
            self.last_failure_transient = True
            return False
        except Exception as e:
            logger.error(f"اتصال ناموفق بود: {e}")
            self.last_failure_transient = True  # unexpected/network-ish error, worth a retry
            return False

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected():
            await self._client.disconnect()
        self._is_connected = False
        logger.info("اتصال حساب کاربری قطع شد.")

    # -- low level helpers ------------------------------------------------------
    async def send_message_to_group(self, text: str, reply_to: Optional[int] = None) -> bool:
        client = self._client_or_raise()
        if not client.is_connected():
            logger.error("کلاینت متصل نیست.")
            return False
        try:
            await client.send_message(entity=int(self._cfg("GROUP_ID")), message=text, reply_to=reply_to)
            preview = text if len(text) <= 60 else text[:60] + "..."
            logger.info(f"پیام ارسال شد: {preview}")
            return True
        except FloodWaitError as e:
            logger.warning(f"محدودیت ارسال: {e.seconds} ثانیه. تلاش مجدد...")
            await asyncio.sleep(e.seconds + 1)
            return await self.send_message_to_group(text, reply_to)
        except Exception as e:
            logger.error(f"ارسال پیام ناموفق بود: {e}")
            return False

    @staticmethod
    def _normalize_digits(s: str) -> str:
        if not s:
            return s
        trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        return s.translate(trans)

    def _extract_cat_produced_points(self, text: str) -> Optional[int]:
        if not text:
            return None
        t = self._normalize_digits(text)
        pattern = r"میو\s*پوینت(?:‌| )?های\s*تولید\s*شده\s*:\s*([0-9][0-9,٬]*)"
        m = re.search(pattern, t)
        if not m:
            return None
        num = m.group(1).replace(",", "").replace("٬", "").strip()
        try:
            return int(num)
        except ValueError:
            return None

    @staticmethod
    def _iter_buttons(msg):
        if not msg or not msg.buttons:
            return
        for r, row in enumerate(msg.buttons):
            for c, btn in enumerate(row):
                yield r, c, (btn.text or "")

    def _find_button_coords_contains(self, msg, needle: str) -> Optional[Tuple[int, int]]:
        needle = (needle or "").strip()
        if not needle:
            return None
        for r, c, txt in self._iter_buttons(msg):
            if needle in txt:
                return (r, c)
        return None

    async def _click_button_contains(self, msg, needle: str) -> bool:
        try:
            coords = self._find_button_coords_contains(msg, needle)
            if coords is None:
                return False
            r, c = coords
            await msg.click(r, c)
            return True
        except FloodWaitError as e:
            logger.warning(f"محدودیت ارسال حین کلیک: {e.seconds} ثانیه.")
            await asyncio.sleep(e.seconds + 1)
            return await self._click_button_contains(msg, needle)
        except Exception as e:
            logger.error(f"کلیک روی دکمه ناموفق بود ({needle}): {e}")
            return False

    async def _wait_for_bot_message(self, predicate: Callable, timeout: int):
        client = self._client_or_raise()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        bot_id = await self._resolve_game_bot_id()
        group_id = int(self._cfg("GROUP_ID"))

        async def handler(event):
            try:
                msg = event.message
                if bot_id is not None and event.sender_id != bot_id:
                    return
                if predicate(msg, event) and not fut.done():
                    fut.set_result(msg)
            except Exception as e:
                logger.debug(f"خطای پردازش رویداد: {e}")

        client.add_event_handler(handler, events.NewMessage(chats=group_id))
        client.add_event_handler(handler, events.MessageEdited(chats=group_id))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            client.remove_event_handler(handler)

    # -- admin / simple actions --------------------------------------------------
    async def send_auto_meow(self) -> bool:
        try:
            async with self._action_lock:
                text = self._current_meow_text or str(self._cfg("AUTO_MEOW_TEXT_A"))
                return await self.send_message_to_group(text)
        except Exception as e:
            logger.error(f"خطا در ارسال میو خودکار: {e}")
            return False

    async def send_transfer_meow(self, number: int) -> bool:
        try:
            async with self._action_lock:
                template = str(self._cfg("TRANSFER_TEMPLATE"))
                try:
                    text = template.format(number=number)
                except (KeyError, ValueError, IndexError):
                    logger.warning("الگوی پیام انتقال نامعتبر است؛ از الگوی پیش‌فرض استفاده شد.")
                    text = f"انتقال میویی {number}"
                reply_id = int(self._cfg("REPLY_MESSAGE_ID")) or None
                return await self.send_message_to_group(text, reply_to=reply_id)
        except Exception as e:
            logger.error(f"خطا در انتقال میویی: {e}")
            return False

    async def do_fish_feed(self) -> bool:
        client = self._client_or_raise()
        if not client.is_connected():
            logger.error("کلاینت متصل نیست.")
            return False
        async with self._action_lock:
            try:
                fish_btn = self._cfg("FISH_FEED_BUTTON_TEXT")
                timeout = int(self._cfg("CAT_RESPONSE_TIMEOUT"))
                panel_waiter = asyncio.create_task(self._wait_for_bot_message(
                    predicate=lambda msg, ev: (msg.buttons is not None)
                    and (self._find_button_coords_contains(msg, fish_btn) is not None),
                    timeout=timeout,
                ))
                if not await self.send_message_to_group(self._cfg("FISH_COMMAND_TEXT")):
                    panel_waiter.cancel()
                    return False
                panel = await panel_waiter
                if not panel:
                    logger.warning("پنل ماهی دریافت نشد (پایان مهلت).")
                    return False
                await asyncio.sleep(int(self._cfg("FISH_CLICK_DELAY")))
                ok = await self._click_button_contains(panel, fish_btn)
                logger.info(f"نتیجه کلیک غذا دادن: {ok}")
                return ok
            except Exception as e:
                logger.error(f"خطا در چرخه ماهی: {e}")
                return False

    def _is_bank_panel(self, msg) -> bool:
        t = msg.raw_text or ""
        return ("بانک" in t) and ("میویی" in t)

    def _is_deposit_prompt(self, msg) -> bool:
        t = msg.raw_text or ""
        if not t:
            return False
        keys = ["درحال واریز", "واریز میو", "واریز", "لطفا مبلغ", "مبلغ مورد نظر", "در جواب همین", "ارسال کنید"]
        return sum(1 for k in keys if k in t) >= 2

    def _is_confirm_panel(self, msg) -> bool:
        t = msg.raw_text or ""
        if msg.buttons is None:
            return False
        if any(k in t for k in ("اطمینان", "آیا", "تایید", "تأیید")):
            return True
        return any(("✅" in txt or "❌" in txt) for _, _, txt in self._iter_buttons(msg))

    async def _bank_deposit(self, amount: int) -> bool:
        if amount <= 0:
            logger.warning("واریز بانک رد شد: مبلغ صفر یا منفی.")
            return False
        client = self._client_or_raise()
        if not client.is_connected():
            logger.error("کلاینت متصل نیست.")
            return False

        deposit_btn = self._cfg("BANK_DEPOSIT_BUTTON_CONTAINS")
        prompt_timeout = int(self._cfg("BANK_DEPOSIT_PROMPT_TIMEOUT"))
        confirm_timeout = int(self._cfg("BANK_CONFIRM_TIMEOUT"))

        if not await self.send_message_to_group(self._cfg("BANK_COMMAND_TEXT")):
            return False

        bank_panel = await self._wait_for_bot_message(
            predicate=lambda msg, ev: (msg.buttons is not None)
            and (self._is_bank_panel(msg) or self._find_button_coords_contains(msg, deposit_btn) is not None),
            timeout=prompt_timeout,
        )
        if not bank_panel:
            logger.warning("پنل بانک دریافت نشد (پایان مهلت).")
            return False

        deposit_prompt_waiter = asyncio.create_task(self._wait_for_bot_message(
            predicate=lambda msg, ev: self._is_deposit_prompt(msg), timeout=prompt_timeout,
        ))
        if not await self._click_button_contains(bank_panel, deposit_btn):
            deposit_prompt_waiter.cancel()
            logger.warning("کلیک دکمه واریز ناموفق بود.")
            return False

        deposit_panel = await deposit_prompt_waiter
        if not deposit_panel:
            logger.warning("پنل واریز دریافت نشد (پایان مهلت).")
            return False

        confirm_waiter = asyncio.create_task(self._wait_for_bot_message(
            predicate=lambda msg, ev: self._is_confirm_panel(msg), timeout=confirm_timeout,
        ))
        try:
            await deposit_panel.reply(str(amount))
            logger.info(f"مبلغ واریزی ارسال شد: {amount}")
        except Exception as e:
            logger.error(f"ریپلای ناموفق بود، تلاش با ارسال معمولی: {e}")
            try:
                await client.send_message(entity=int(self._cfg("GROUP_ID")), message=str(amount))
            except Exception as e2:
                logger.error(f"ارسال جایگزین مبلغ نیز ناموفق بود: {e2}")
                confirm_waiter.cancel()
                return False

        confirm_msg = await confirm_waiter
        if not confirm_msg:
            logger.warning("پنل تایید بانک دریافت نشد (پایان مهلت).")
            return False

        if await self._click_button_contains(confirm_msg, "✅"):
            logger.log(25, "واریز بانکی تایید شد.")
            return True
        try:
            await confirm_msg.click(0, 0)
            logger.log(25, "واریز بانکی تایید شد (دکمه اول).")
            return True
        except Exception as e:
            logger.error(f"تایید واریز ناموفق بود: {e}")
            return False

    async def collect_cat_and_deposit_to_bank(self) -> bool:
        client = self._client_or_raise()
        if not client.is_connected():
            logger.error("کلاینت متصل نیست.")
            return False
        async with self._action_lock:
            try:
                collect_btn = self._cfg("CAT_COLLECT_BUTTON_TEXT")
                timeout = int(self._cfg("CAT_RESPONSE_TIMEOUT"))
                cat_panel_waiter = asyncio.create_task(self._wait_for_bot_message(
                    predicate=lambda msg, ev: (msg.buttons is not None)
                    and (self._find_button_coords_contains(msg, collect_btn) is not None),
                    timeout=timeout,
                ))
                if not await self.send_message_to_group(self._cfg("CAT_COMMAND_TEXT")):
                    cat_panel_waiter.cancel()
                    return False
                panel = await cat_panel_waiter
                if not panel:
                    logger.warning("پنل گربه دریافت نشد (پایان مهلت).")
                    return False
                amount = self._extract_cat_produced_points(panel.raw_text or "") or 0
                logger.info(f"مقدار استخراج‌شده از گربه: {amount}")
                if not await self._click_button_contains(panel, collect_btn):
                    logger.warning("کلیک دکمه برداشت ناموفق بود.")
                    return False
                await asyncio.sleep(2)
                if amount > 0:
                    return await self._bank_deposit(amount)
                logger.warning("واریز انجام نشد چون مقدار استخراج‌شده صفر بود.")
                return True
            except Exception as e:
                logger.error(f"خطا در چرخه گربه: {e}")
                return False

    # -- schedulers -----------------------------------------------------------------
    async def run_meow_toggle_scheduler(self) -> None:
        """Alternates the text auto-meow sends between AUTO_MEOW_TEXT_A and
        AUTO_MEOW_TEXT_B on its own timer (independent of the send interval).
        Recovered functionality — see AUDIT.md."""
        text_a = str(self._cfg("AUTO_MEOW_TEXT_A"))
        self._current_meow_text = text_a
        lo = int(self._cfg("MEOW_TOGGLE_INTERVAL_MIN"))
        hi = int(self._cfg("MEOW_TOGGLE_INTERVAL_MAX"))
        logger.info(f"زمان‌بند تعویض متن میو شروع شد ({lo}-{hi} ثانیه).")
        using_a = True
        while True:
            try:
                await asyncio.sleep(random.randint(lo, hi))
                using_a = not using_a
                text_a = str(self._cfg("AUTO_MEOW_TEXT_A"))
                text_b = str(self._cfg("AUTO_MEOW_TEXT_B"))
                self._current_meow_text = text_a if using_a else text_b
                logger.info(f"متن میوی خودکار تغییر کرد به: {self._current_meow_text}")
            except asyncio.CancelledError:
                logger.info("زمان‌بند تعویض متن میو متوقف شد.")
                break
            except Exception as e:
                logger.error(f"خطا در زمان‌بند تعویض متن میو: {e}")
                await asyncio.sleep(5)

    async def run_auto_meow_scheduler(self) -> None:
        lo, hi = int(self._cfg("MEOW_INTERVAL_MIN")), int(self._cfg("MEOW_INTERVAL_MAX"))
        logger.info(f"زمان‌بند میو خودکار شروع شد ({lo}-{hi} ثانیه).")
        while True:
            try:
                await asyncio.sleep(random.randint(lo, hi))
                if not self._is_connected:
                    await asyncio.sleep(5)
                    continue
                await self.send_auto_meow()
            except asyncio.CancelledError:
                logger.info("زمان‌بند میو متوقف شد.")
                break
            except Exception as e:
                logger.error(f"خطا در زمان‌بند میو: {e}")
                await asyncio.sleep(5)

    async def run_cat_scheduler(self) -> None:
        lo, hi = int(self._cfg("CAT_INTERVAL_MIN")), int(self._cfg("CAT_INTERVAL_MAX"))
        logger.info(f"زمان‌بند گربه شروع شد ({lo}-{hi} ثانیه).")
        while True:
            try:
                await asyncio.sleep(random.randint(lo, hi))
                if not self._is_connected:
                    await asyncio.sleep(5)
                    continue
                await self.collect_cat_and_deposit_to_bank()
            except asyncio.CancelledError:
                logger.info("زمان‌بند گربه متوقف شد.")
                break
            except Exception as e:
                logger.error(f"خطا در زمان‌بند گربه: {e}")
                await asyncio.sleep(5)

    async def run_fish_scheduler(self) -> None:
        lo, hi = int(self._cfg("FISH_INTERVAL_MIN")), int(self._cfg("FISH_INTERVAL_MAX"))
        logger.info(f"زمان‌بند ماهی شروع شد ({lo}-{hi} ثانیه).")
        while True:
            try:
                await asyncio.sleep(random.randint(lo, hi))
                if not self._is_connected:
                    await asyncio.sleep(5)
                    continue
                await self.do_fish_feed()
            except asyncio.CancelledError:
                logger.info("زمان‌بند ماهی متوقف شد.")
                break
            except Exception as e:
                logger.error(f"خطا در زمان‌بند ماهی: {e}")
                await asyncio.sleep(5)
