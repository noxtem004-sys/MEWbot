# AUDIT.md — Final Pre-Release Verification Pass

## UI/UX UPGRADE PASS (added after the verification pass below)

Purely cosmetic — no backend/logic files touched. Re-ran the full backend
regression suite (retry logic, config validation) afterward to confirm.

- New color palette/QSS: indigo accent (#6C5CE7), card-based panels with
  rounded corners, refined button hierarchy (primary/danger/ghost),
  pill-style status badge, redesigned tabs, better input focus states
- Generated a simple app icon (paw-print mark, `gui/resources/icons/app.ico`
  + `.png`) with Pillow — no copyrighted/third-party art — wired into the
  window icon, sidebar header, and `packaging/build.spec`
- Redesigned `DashboardPage`: status pill + uptime moved into a header
  card, icon-labeled Start/Stop buttons, log panel restyled as its own
  card with a header row
- Redesigned sidebar: app logo/name header, icon-prefixed nav items,
  version footer
- Redesigned `SettingsPage`: icon-prefixed tabs, each tab wrapped in a
  scrollable card, primary-styled Save button
- Redesigned `LoginDialog`: icon + title/subtitle header per step,
  primary/ghost buttons
- **Found and fixed one real bug while doing this**: the login dialog's
  field *labels* stayed visible for all three login steps at once — only
  the input widgets themselves were being hidden/shown, not their
  QFormLayout labels. Fixed with `QFormLayout.setRowVisible()`; verified
  with `isHidden()` checks (an `isVisible()`-based test gave a false
  negative here since the dialog itself isn't shown in headless tests —
  documented so a future pass doesn't get confused by the same artifact).

Verified headlessly: full `MainWindow` construction with the new
stylesheet applied, status pill rendering for all 5 states, a real log
line flowing through the (previously-broken, now-fixed) signal path with
the new styling, login dialog step-switching with correct label
visibility, and settings tab icons present on all 6 tabs.

**Not verified**: actual visual appearance/spacing on a real screen —
this sandbox can construct and query widget state but not render pixels
for a human to judge. Recommend a quick visual pass on Windows before
considering this final.

---


Architecture unchanged: PySide6 + qasync, single process/thread/event loop.
No threads or subprocesses were introduced. This pass found and fixed 5
real bugs, all confirmed by a failing test first, then fixed, then
re-confirmed passing — nothing here is claimed without having actually
been run in this session.

---

## PASS — actually tested and passed in this session

**Code audit**
- No `input()`, `time.sleep()`, or other blocking calls anywhere in the
  runtime path (grepped whole project)
- No `subprocess`/`threading.Thread`/`QThread` usage anywhere (grepped)
- `sys.exit()` appears exactly once, in `app.py`'s standard `if __name__
  == "__main__": sys.exit(main())` entry-point idiom — not a mid-run exit
- Only one `TelegramClient` instance is ever created per `MeowUserClient`
  (lazily, reused across reconnects) — verified by code inspection of
  `build_client()`
- Zero remaining `self._cfg(key) or <hardcoded default>` patterns except
  two intentional ones (documented in code comments): a `None`-guard
  before the meow-toggle scheduler's first tick, and `REPLY_MESSAGE_ID`'s
  `0 → None` "no reply target" business rule

**Lifecycle testing**
- Start → Stop → Start again → Stop: clean, symmetric teardown each time
- **Stop while Start is still retrying a transient connection failure**:
  previously hung forever (see BUG 1 below) — now returns cleanly and
  reaches STOPPED, verified with a 5-second `timeout` guard so a
  regression can't hang the test run again
- **GUI close while running**: previously accepted the close event
  immediately while `stop()` was merely scheduled, not awaited (see BUG 4)
  — now verified the close event is ignored, the window disables itself,
  and `QApplication.quit()` is only called after `stop()` fully completes
- **Duplicate auto-recovery**: two rapid unexpected-polling-failure
  signals no longer stack two recovery tasks — verified `_auto_recover_task`
  identity is reused, not duplicated
- **Stale auto-recovery vs. a fresh restart**: an auto-recovery task from
  an old crash, made stale by a subsequent legitimate restart, is proven
  to no-op instead of tearing down the new session (generation-counter test)
- Full Start→Stop→Restart→shutdown sequence re-run against a **genuinely
  clean virtual environment** installed only from `requirements.txt`
  (`/tmp/clean_venv`), with the real Qt log-signal path exercised end to
  end (not bypassed by calling widget methods directly)

**Telethon login flow (mocked — no real Telegram)**
- phone → code → success sequencing (asyncio futures resolve in order)
- Non-transient failures (invalid code path, missing login UI) do not
  trigger blind retries
- Transient failures (network-ish) retry with a 5s backoff, confirmed
  exactly 3 attempts before success in a controlled test
- Cancellation: an in-flight login/connect attempt is now provably
  cancellable by Stop (see BUG 1 fix) — confirmed with a real `asyncio`
  cancellation, not just a cooperative flag

**ConfigManager (all fields)**
- Missing config file → schema defaults loaded, no crash
- Malformed JSON on disk → falls back to defaults, no crash
- Partial/old config file (missing keys) → missing keys filled from
  schema defaults, no `KeyError`
- Save → fresh `ConfigManager` instance (simulating app restart) loads
  the same values back, **including a saved `0`**
- `reload()`/`load()` picks up an externally-changed file
- Secret redaction: `redacted_dict()` masks `API_HASH`/`BOT_TOKEN`-type
  fields; the real stored value is untouched
- Empty config → exactly 5 Persian required-field errors (not 6 —
  `USER_SESSION` has a valid non-empty default, correctly not flagged)
- **Negative `API_ID`/`ADMIN_ID`** → now correctly rejected (BUG 5)
- **Negative `GROUP_ID`** (a real, valid supergroup ID shape) → correctly
  NOT rejected — confirmed the fix didn't overcorrect
- **Inverted MIN > MAX** on any of the 4 timing pairs → now correctly
  rejected (BUG 5)
- **Negative timing/delay values** → now correctly rejected (BUG 5)
- A fully valid config, including an intentional `0` timing value, still
  produces zero validation problems (regression check)
- Config changes while runtime is active: non-critical field → no
  restart; critical field (`API_ID`/`API_HASH`/`BOT_TOKEN`/`USER_SESSION`)
  → exactly one soft-restart

**Scheduler verification**
- All 4 schedulers (meow, meow-toggle, cat, fish) read every timing/text
  value through `ConfigManager` — zero hardcoded fallbacks remain
- Meow-text alternation confirmed strictly correct (میو → مع → میو → ...)
  with a 0-second interval, which is exactly the case that caught BUG 2
  in the previous pass
- No duplicate scheduler tasks created across a Stop/Start cycle
  (`_tasks` list is rebuilt fresh each `start()`, fully drained on `stop()`)
- Transfer template renders custom templates correctly and falls back
  safely on a malformed one

**GUI integration**
- Full `MainWindow` construction is headless-testable and succeeds; all
  30 schema fields render as live Settings widgets
- **Real log signal path** (`logger.info(...)` → `QtLogHandler` →
  `record_emitted` Qt signal → `MainWindow._on_log_record` →
  `DashboardPage.append_log`) verified end-to-end in the clean venv —
  this exact path was silently broken until this pass (BUG 3)
- Secret-redaction markers survive the logging-bridge rewrite (re-tested
  after BUG 3's fix)
- RTL/Persian UI strings re-swept — unchanged from the previous pass,
  still intact (only the product name is English, an intentional brand
  name)

**Dependencies**
- Every third-party import used anywhere in the project (`PySide6`,
  `aiogram`, `aiosqlite`, `qasync`, `telethon`) is pinned in
  `requirements.txt`
- Clean `pip install -r requirements.txt` into a brand-new venv succeeded
  with no errors

---

## FAIL (found and fixed during this pass) — root cause, fix, re-test

**BUG 1 — `stop()` could leave an unkillable infinite retry loop.**
Root cause: `_connect_with_retry()`'s backoff loop only checked the
cooperative `self._stopping` flag *after* waking from `asyncio.sleep(5)`.
`stop()` set that flag, ran its own (fast) teardown, then reset the flag
back to `False` — often *before* the sleeping retry loop ever woke up to
see it. That loop then kept retrying forever, immune to Stop, because it
had no live scheduler/polling task for `stop()` to actually cancel.
Fix: `stop()`/`_stop_internal()` now directly cancels the tracked
`self._start_task` (the in-flight `start()` coroutine) via
`asyncio.Task.cancel()`, which interrupts `asyncio.sleep()` immediately —
no longer relies solely on a flag that can race. Confirmed with a 5s
`timeout`-guarded test that previously hung and now completes cleanly.

**BUG 2 — auto-recovery used the wrong intermediate status, silently
no-opping the restart.**
Root cause: `_auto_recover()` called `_stop_internal(final_status=
Status.STARTING)` before calling `self.start()` again — but `start()`'s
own guard (`if self.status in (STARTING, RUNNING): return True`) then
saw status already STARTING and returned immediately without actually
reconnecting anything, silently leaving the app "recovered" in name only.
Fix: pass `Status.STOPPED` as the intermediate status instead (matching
what `soft_restart()`/`stop()` already correctly do), so the subsequent
`start()` call isn't blocked by its own re-entrancy guard. Also added:
a generation counter so a stale, superseded auto-recovery can't act on a
newer session, and de-duplication so two failures in quick succession
don't stack two recovery tasks.

**BUG 3 — the entire live-log-streaming feature was silently non-functional.**
Root cause: `QtLogHandler` mixed `QObject` and `logging.Handler`, and
also defined a method literally named `emit` (required, since
`logging.Handler.handle()` calls `self.emit(record)` by that exact name).
Empirically, once any method named `emit` exists on the class, PySide6's
signal machinery resolves `self.record_emitted.emit(...)` back through
that method instead of the Signal's own bound emit — raising `TypeError:
QtLogHandler.emit() takes 2 positional arguments but N were given` on
*every single log call*. This reproduced identically regardless of base
class order (tried both). It went undetected in the previous pass because
those tests called `DashboardPage.append_log()` directly, never actually
exercising the real `logger → QtLogHandler → Signal → GUI` path.
Fix: moved the `Signal` onto a separate, unrelated `QObject` subclass
(`_LogSignalCarrier`), held as an attribute of `QtLogHandler`, with a
`record_emitted` property forwarding to it so calling code
(`main_window.py`) needed no changes. Verified with an end-to-end test:
a real `logging.getLogger().info(...)` call now correctly reaches a
connected Qt slot, in both the original dev environment and the clean venv.

**BUG 4 — closing the window while running could leak the live connection.**
Root cause: `closeEvent()` called `asyncio.ensure_future(self.runtime.stop())`
(merely *scheduling* the coroutine) and then immediately `event.accept()`,
which lets Qt tear the application down. There's no guarantee the
scheduled `stop()` — which needs several more event-loop turns to
disconnect Telethon, cancel tasks, and close the bot's HTTP session —
ever gets to run before the app actually exits.
Fix: `closeEvent()` now ignores the close event, disables the window, and
awaits the real shutdown in `_shutdown_and_quit()`, calling
`QApplication.quit()` only in that coroutine's `finally` block — i.e.
only after `stop()` has genuinely finished. Verified with a mocked `stop()`
that records ordering: `quit()` fires strictly after `stop()` completes,
never before.

**BUG 5 — `ConfigManager.validate()` didn't catch negative IDs, inverted
MIN>MAX pairs, or negative timing values.**
Root cause: the only integer check was `if not val`, which catches `0`
but not negative numbers, and there was no cross-field MIN/MAX check at
all. A user could type `-5` into API ID or set a toggle interval's MIN
above its MAX, pass validation, and only find out from a confusing
Telethon-level error at connect time instead of a clear Persian message
upfront — this is exactly what the audit item "negative values where
invalid" and "min/max intervals" asked to check.
Fix: added a `min_value` bound to `FieldDef` (1 for `API_ID`/`ADMIN_ID`,
0 for every timing/delay/`REPLY_MESSAGE_ID` field, left unset for
`GROUP_ID` since real supergroup IDs are legitimately large negative
numbers), plus an explicit MIN≤MAX check for all 4 interval pairs.
Verified: negative `API_ID`/`ADMIN_ID` now rejected; negative `GROUP_ID`
correctly still accepted; inverted MIN>MAX rejected; negative timing
value rejected; a fully valid config (including an intentional `0`) still
passes with zero problems.

No other failing tests were found in this pass.

---

## UNTESTED — requires real Telegram servers and/or real Windows

**Requires real Telegram (cannot be done in this sandbox without live
credentials, which won't be routed through here):**
- Actual phone/code/2FA login against Telegram's real servers
- Reuse of a real, previously-authorized session file
- Real `FloodWaitError` timing/behavior under genuine rate-limiting
- Real reconnect behavior after an actual network drop (the retry-loop
  *mechanism* is tested with mocks; Telethon's own behavior when
  `client.connect()`/`disconnect()` are invoked concurrently mid-handshake,
  as could happen if Stop lands exactly during a live TLS negotiation, is
  not something a mock can fully exercise)
- Real button-click responses and point-extraction from the actual game
  bot's current message format

**Requires Windows:**
- Building the actual `.exe` via `pyinstaller packaging/build.spec`
  (PyInstaller doesn't cross-compile from Linux)
- Visual confirmation of Persian font rendering / RTL layout on Windows's
  font rasterizer
- Confirming no OS-level orphaned process/socket remains after Stop on
  the real target OS (this sandbox can prove the asyncio task graph is
  clean, not the OS process table)

---

## RISKS — remaining, known, not fixed in this pass

1. **Concurrent cancellation of a live Telethon handshake.** BUG 1's fix
   cancels the `start()` task directly, which could in principle interrupt
   `client.connect()`/`sign_in()` mid-flight. Telethon's async methods are
   generally built to tolerate `asyncio.CancelledError`, but this hasn't
   been (and can't be, here) confirmed against Telegram's real servers.
   If a Windows tester sees a stuck or oddly-stated client after a
   rapid Start-then-immediately-Stop, this is the first place to look.
2. **Message-classification heuristics remain hardcoded**, as documented
   and deliberately scoped in the previous pass — unchanged in this pass.
3. **No installer** — a simple app icon is now bundled and wired into the
   build, but there's still only a portable PyInstaller folder build, no
   Inno Setup/NSIS installer;
   `packaging/build.spec` still needs a `.ico` path filled in.
4. **`_stop_internal`'s `except Exception: pass` around `dp.stop_polling()`**
   swallows any error from that specific call silently. Reviewed and
   judged low-risk (it's immediately followed by an unconditional
   task-cancel that achieves the same end state either way), but it is a
   silent catch, worth knowing about.
5. **Font bundling is optional** and falls back to the OS default —
   Persian rendering quality on a Windows box without Vazirmatn installed
   hasn't been visually confirmed (can't render pixels in this sandbox).

---

## CHANGES made during this final pass

- `backend/bot_core.py`: added `_start_task` tracking + direct cancellation
  in `stop()`/`_stop_internal()` (BUG 1); fixed `_auto_recover()`'s
  intermediate status and added generation-counter + duplicate-task guard
  (BUG 2); wrapped `start()`'s body in a try/except so any unexpected
  exception (e.g. `TokenValidationError` from a malformed bot token) is
  caught, logged in Persian, and turns into `Status.ERROR` instead of an
  unhandled exception leaving the app stuck at STARTING (found during
  this pass's audit, not carried over from before).
- `core/logging_bridge.py`: moved the `Signal` off `QtLogHandler` onto a
  separate `_LogSignalCarrier(QObject)`, fixing the PySide6/`emit`-name
  collision that silently broke all live log streaming (BUG 3).
- `core/config_manager.py`: added `FieldDef.min_value`, per-field minimum
  checks, and the 4 MIN≤MAX interval-pair checks in `validate()` (BUG 5).
- `gui/main_window.py`: rewrote `closeEvent()` to ignore-then-await-then-
  quit instead of accept-then-hope (BUG 4); added `self._closing` guard
  against double-triggering.

No architecture changes. No files were rewritten wholesale — every change
above is a targeted patch to the specific function(s) responsible for the
bug it fixes, per the fix policy.

---

## Remaining tests that MUST be run on a real Windows machine with real
## Telegram credentials before this is considered production-ready

1. First-run login: phone → code → (if enabled) 2FA password, end to end
2. Restart the app and confirm the existing session is reused without
   re-prompting
3. Let it run for at least one full meow-toggle interval and confirm the
   message text actually alternates in the real group
4. Trigger a real network drop (e.g. disable Wi-Fi briefly) while running
   and confirm it reconnects on its own within the retry backoff
5. Deliberately enter a wrong verification code, then a correct one, and
   confirm the second attempt succeeds without needing an app restart
6. Press Stop while a connection attempt is genuinely in-flight (not
   mocked) and confirm the app doesn't hang and Task Manager shows no
   leftover python/telegram network activity afterward
7. Change a critical setting (e.g. the bot token) while running and
   confirm the soft-restart actually reconnects with the new value
8. Close the window while running and confirm (via Task Manager / network
   monitor) the Telegram connection is actually torn down, not left open
9. Build the `.exe` via `pyinstaller packaging/build.spec` and confirm it
   launches, renders Persian/RTL correctly, and behaves identically to
   running from source
10. Full 15-item test plan from the original project brief, using the
    real game bot in the real target group
