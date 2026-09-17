# Telegram Meow Bot — Desktop (Persian RTL GUI)

A real desktop wrapper around the original aiogram+Telethon backend. The
Python backend is unchanged in behavior — only refactored so it has no
hard-coded config and no blocking `input()` calls. Nothing here is a mock;
Start/Stop, login, logs, and settings all talk to the live backend.

## What changed vs. the original project (audit → implementation)

| Area | Before | Now |
|---|---|---|
| Config | Blank constants in `config.py`, edited by hand | One JSON file managed by `core/config_manager.py`, editable from the Settings tab, validated before Start |
| Login | `input()` in the terminal | `LoginDialog` in the GUI, backed by asyncio futures (`core/bot_core.py`) |
| Logs | `print`/console only | `QtLogHandler` streams every log record into the Dashboard's terminal panel live |
| Lifecycle | Script run top-to-bottom, `sys.exit()` on failure | `MeowBotRuntime.start()/stop()` — restart as many times as you like without restarting the app |
| GUI↔backend link | N/A | Same process, same thread, same asyncio event loop via `qasync` — no subprocess, no polling |

## Run from source

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python app.py
```

First launch: open **تنظیمات** (Settings) and fill in at least the
required (`*`) fields — API ID/Hash from my.telegram.org, bot token from
@BotFather, your admin ID, and the target group ID. Save, then go to
**داشبورد** (Dashboard) and press **شروع** (Start). If no session exists
yet you'll be prompted for phone → code → (if enabled) 2FA password right
in the app.

## Build the Windows executable

This has to be run **on Windows** (PyInstaller does not cross-compile):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pyinstaller packaging\build.spec
```

Result: `dist\TelegramMeowBot\TelegramMeowBot.exe` — a portable folder you
can zip and hand to someone, or wrap with Inno Setup / NSIS for a proper
installer if you want one later.

An app icon (a simple indigo paw-print mark) is already bundled at
`gui/resources/icons/app.ico`/`app.png` and wired into both the window
icon and `packaging/build.spec` — replace those files with your own art
if you want different branding; no rebuild step needed beyond re-running
PyInstaller.

## Persian font

Drop `Vazirmatn-*.ttf` files (OFL-licensed, https://github.com/rastikerdar/vazirmatn)
into `gui/resources/fonts/`. `app.py` auto-loads any `.ttf` found there. If
the folder stays empty, the app falls back to the OS's default font, which
still renders Persian but less consistently across Windows versions.

## Where each requirement from the brief landed

- Centralized config, no hard-coded secrets → `core/config_manager.py` (`SCHEMA`)
- Real Start/Stop, no orphan processes → `backend/bot_core.py` (`MeowBotRuntime`), single process/thread
- Live terminal logs with levels → `core/logging_bridge.py` + `gui/pages/dashboard_page.py`
- Login/2FA UI → `gui/pages/login_dialog.py`, driven by `MeowBotRuntime._ask_phone/_ask_code/_ask_password`
- Settings, masked secrets → `gui/pages/settings_page.py` (`SecretField`)
- Validation before start → `ConfigManager.validate()`, called from both the Settings save button and `MeowBotRuntime.start()`
- Status indicator + uptime → `gui/pages/dashboard_page.py`

## What I could **not** verify in this environment, and why

I built this in a Linux sandbox with no access to Telegram's servers and
no real API credentials — using real ones here would mean handling your
live session/API secrets outside your machine, which I won't do. So:

- I verified: every file compiles, the full GUI constructs and runs
  headlessly, the config schema/validation round-trips correctly, and the
  login future/callback wiring (phone → code → password sequencing)
  behaves correctly under a simulated flow.
- I could **not** run the actual 15-item test plan from the brief (real
  login, real flood-wait handling, real button-clicking against the game
  bot) — that needs your real credentials and Telegram's live servers, so
  it has to happen on your machine. The architecture is built so each of
  those tests maps directly onto something in `backend/` you can exercise
  by pressing Start/Stop and watching the log panel.
- I could not produce an actual built `.exe` — PyInstaller has to run on
  Windows. `packaging/build.spec` plus the steps above are ready to go.

## A note on what this bot does

Worth being upfront: this automates a real Telegram user account to send
scheduled group messages and click through another bot's UI on your
behalf. That's fine for a private group you and the bot's owner control,
but keep in mind it sits outside what a normal Telegram client does, so
it's worth checking it's okay with your group/game's rules before running
it continuously.
