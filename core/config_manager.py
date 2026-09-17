"""
Centralized configuration system for Telegram Meow GUI.

This replaces the old hard-coded config.py. Every configurable value
discovered during the project audit lives in SCHEMA below, grouped into
sections that map directly to the Settings pages in the GUI.

The backend NEVER reads a static config.py anymore. It receives a
ConfigManager instance (or plain dict via .as_dict()) at runtime.

Persistence: a single JSON file in the user's per-app data directory
(e.g. %APPDATA%\\TelegramMeowGUI\\config.json on Windows). No secret is
ever written into source code.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def app_data_dir() -> Path:
    """Return a per-user, per-app writable directory (Windows/macOS/Linux)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / "TelegramMeowGUI"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = app_data_dir() / "config.json"
SESSION_DIR = app_data_dir() / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class FieldDef:
    key: str
    section: str            # "account" | "api" | "bots" | "messages" | "keywords" | "timing" | "advanced"
    label_fa: str
    type: str                # "str" | "int" | "secret"
    default: Any = ""
    required: bool = False
    help_fa: str = ""
    min_value: Optional[int] = None  # for "int" fields: reject values below this, independent of `required`


# Every configurable value found in the original config.py, with NO defaults
# that could pass for real credentials. Empty/zero means "not configured yet".
SCHEMA: list[FieldDef] = [
    # --- Account / Telethon session ---
    FieldDef("USER_SESSION", "account", "نام نشست (Session)", "str", "meow_account", True,
             "نام فایل نشست تلگرام (بدون پسوند .session)."),
    FieldDef("PHONE_NUMBER", "account", "شماره تلفن حساب کاربری", "str", "", False,
             "برای ورود اولیه استفاده می‌شود؛ در ورودهای بعدی از نشست ذخیره‌شده استفاده می‌شود."),

    # --- API credentials (Telegram + Bot) ---
    FieldDef("API_ID", "api", "API ID", "int", 0, True, "از my.telegram.org دریافت می‌شود.", min_value=1),
    FieldDef("API_HASH", "api", "API Hash", "secret", "", True, "از my.telegram.org دریافت می‌شود."),
    FieldDef("BOT_TOKEN", "api", "توکن ربات ادمین", "secret", "", True, "از @BotFather دریافت می‌شود."),

    # --- Bots / IDs ---
    FieldDef("ADMIN_ID", "bots", "شناسه ادمین", "int", 0, True, "آیدی عددی تلگرام شما.", min_value=1),
    FieldDef("GROUP_ID", "bots", "شناسه گروه", "int", 0, True, "آیدی عددی گروه هدف (منفی)."),
    FieldDef("REPLY_MESSAGE_ID", "bots", "شناسه پیام برای ریپلای انتقال", "int", 0, False, "", min_value=0),
    FieldDef("GAME_BOT_USERNAME", "bots", "یوزرنیم ربات بازی", "str", "", False,
             "برای جلوگیری از کلیک اشتباه، فقط پیام‌های همین ربات پردازش می‌شود."),

    # --- Messages (editable text sent to the group) ---
    FieldDef("CAT_COMMAND_TEXT", "messages", "متن دستور گربه", "str", "گربه", False, ""),
    FieldDef("FISH_COMMAND_TEXT", "messages", "متن دستور ماهی", "str", "ماهی", False, ""),
    FieldDef("BANK_COMMAND_TEXT", "messages", "متن دستور بانک", "str", "بانک میویی", False, ""),
    FieldDef("TRANSFER_TEMPLATE", "messages", "الگوی پیام انتقال", "str", "انتقال میویی {number}", False,
             "از {number} برای جایگذاری عدد انتقال استفاده کنید."),
    FieldDef("AUTO_MEOW_TEXT_A", "messages", "متن میوی خودکار (حالت اول)", "str", "میو", False,
             "هر بار طبق زمان‌بندی زیر، بین حالت اول و دوم جابه‌جا می‌شود."),
    FieldDef("AUTO_MEOW_TEXT_B", "messages", "متن میوی خودکار (حالت دوم)", "str", "مع", False, ""),

    # --- Keywords (button-text matching, also editable) ---
    FieldDef("CAT_COLLECT_BUTTON_TEXT", "keywords", "متن دکمه برداشت گربه", "str", "برداشت", False, ""),
    FieldDef("FISH_FEED_BUTTON_TEXT", "keywords", "متن دکمه غذا دادن", "str", "بده پیشی", False, ""),
    FieldDef("BANK_DEPOSIT_BUTTON_CONTAINS", "keywords", "متن دکمه واریز بانک", "str", "واریز", False, ""),

    # --- Timing (all in seconds) ---
    FieldDef("MEOW_INTERVAL_MIN", "timing", "حداقل فاصله ارسال میو (ثانیه)", "int", 300, False, "5 دقیقه", min_value=0),
    FieldDef("MEOW_INTERVAL_MAX", "timing", "حداکثر فاصله ارسال میو (ثانیه)", "int", 450, False, "7.5 دقیقه", min_value=0),
    FieldDef("MEOW_TOGGLE_INTERVAL_MIN", "timing", "حداقل فاصله تعویض متن میو (ثانیه)", "int", 3600, False, "60 دقیقه", min_value=0),
    FieldDef("MEOW_TOGGLE_INTERVAL_MAX", "timing", "حداکثر فاصله تعویض متن میو (ثانیه)", "int", 4500, False, "75 دقیقه", min_value=0),
    FieldDef("CAT_INTERVAL_MIN", "timing", "حداقل فاصله چرخه گربه (ثانیه)", "int", 600, False, "10 دقیقه", min_value=0),
    FieldDef("CAT_INTERVAL_MAX", "timing", "حداکثر فاصله چرخه گربه (ثانیه)", "int", 720, False, "12 دقیقه", min_value=0),
    FieldDef("CAT_RESPONSE_TIMEOUT", "timing", "مهلت پاسخ پنل گربه (ثانیه)", "int", 20, False, "", min_value=0),
    FieldDef("FISH_INTERVAL_MIN", "timing", "حداقل فاصله چرخه ماهی (ثانیه)", "int", 3600, False, "60 دقیقه", min_value=0),
    FieldDef("FISH_INTERVAL_MAX", "timing", "حداکثر فاصله چرخه ماهی (ثانیه)", "int", 3900, False, "65 دقیقه", min_value=0),
    FieldDef("FISH_CLICK_DELAY", "timing", "تاخیر قبل از کلیک غذا (ثانیه)", "int", 10, False, "", min_value=0),
    FieldDef("BANK_DEPOSIT_PROMPT_TIMEOUT", "timing", "مهلت پنل واریز (ثانیه)", "int", 20, False, "", min_value=0),
    FieldDef("BANK_CONFIRM_TIMEOUT", "timing", "مهلت پنل تایید (ثانیه)", "int", 20, False, "", min_value=0),
]

# (MIN key, MAX key, Persian label for error messages) — validate() checks
# that MIN <= MAX for each of these pairs.
_MIN_MAX_PAIRS = [
    ("MEOW_INTERVAL_MIN", "MEOW_INTERVAL_MAX", "فاصله ارسال میو"),
    ("MEOW_TOGGLE_INTERVAL_MIN", "MEOW_TOGGLE_INTERVAL_MAX", "فاصله تعویض متن میو"),
    ("CAT_INTERVAL_MIN", "CAT_INTERVAL_MAX", "فاصله چرخه گربه"),
    ("FISH_INTERVAL_MIN", "FISH_INTERVAL_MAX", "فاصله چرخه ماهی"),
]

SECTION_LABELS_FA = {
    "account": "حساب کاربری",
    "api": "API",
    "bots": "ربات‌ها / شناسه‌ها",
    "messages": "پیام‌ها",
    "keywords": "کلمات کلیدی",
    "timing": "زمان‌بندی",
    "advanced": "پیشرفته",
}

SECRET_KEYS = {f.key for f in SCHEMA if f.type == "secret"}
REQUIRED_KEYS = {f.key for f in SCHEMA if f.required}

# Recovered from an earlier prototype's settings_store.pyc (see AUDIT.md).
# Changing any of these while the bot is running invalidates the live
# Telethon/aiogram connection, so a soft-restart is required for the new
# value to take effect — everything else can be picked up live.
CRITICAL_KEYS_RESTART = {"BOT_TOKEN", "API_ID", "API_HASH", "USER_SESSION"}


class ConfigManager:
    """Thread-safe load/save/validate for the single JSON config file."""

    def __init__(self, path: Path = CONFIG_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {f.key: f.default for f in SCHEMA}
        self.load()

    # -- persistence --------------------------------------------------
    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    on_disk = json.loads(self._path.read_text(encoding="utf-8"))
                    for f in SCHEMA:
                        if f.key in on_disk:
                            self._data[f.key] = on_disk[f.key]
                except (json.JSONDecodeError, OSError):
                    pass  # keep defaults; GUI will show validation errors

    def save(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)

    # -- access ---------------------------------------------------------
    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any, autosave: bool = True) -> None:
        with self._lock:
            self._data[key] = value
            if autosave:
                self.save()

    def set_many(self, values: dict[str, Any], autosave: bool = True) -> None:
        with self._lock:
            self._data.update(values)
            if autosave:
                self.save()

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def redacted_dict(self) -> dict[str, Any]:
        """Safe-for-logging copy: secrets replaced with a fixed mask."""
        d = self.as_dict()
        for k in SECRET_KEYS:
            if d.get(k):
                d[k] = "••••••••"
        return d

    # -- validation -------------------------------------------------------
    def validate(self) -> list[str]:
        """Return a list of Persian-language problems; empty = OK to start."""
        problems: list[str] = []
        by_key = {f.key: f for f in SCHEMA}

        for key in REQUIRED_KEYS:
            f = by_key[key]
            val = self._data.get(key)
            if f.type == "int":
                if not val:
                    problems.append(f"{f.label_fa} الزامی است.")
            else:
                if not str(val or "").strip():
                    problems.append(f"{f.label_fa} الزامی است.")

        # min_value applies to every int field regardless of `required` --
        # e.g. a 0-second FISH_CLICK_DELAY is fine (min_value=0), but a
        # negative one, or a negative/zero API_ID, is not. Skip a field
        # already reported empty/zero-and-required above to avoid a
        # confusing double error on the same field.
        for f in SCHEMA:
            if f.type != "int" or f.min_value is None:
                continue
            val = self._data.get(f.key)
            try:
                ival = int(val)
            except (TypeError, ValueError):
                problems.append(f"{f.label_fa} باید یک عدد صحیح باشد.")
                continue
            if f.required and not ival:
                continue  # already covered by the required-field pass above
            if ival < f.min_value:
                if f.min_value == 0:
                    problems.append(f"{f.label_fa} نمی‌تواند منفی باشد.")
                else:
                    problems.append(f"{f.label_fa} باید حداقل {f.min_value} باشد.")

        for lo_key, hi_key, label_fa in _MIN_MAX_PAIRS:
            try:
                lo, hi = int(self._data.get(lo_key)), int(self._data.get(hi_key))
            except (TypeError, ValueError):
                continue  # already reported as a non-integer above
            if lo > hi:
                problems.append(f"{label_fa}: مقدار حداقل نمی‌تواند بیشتر از حداکثر باشد.")

        return problems

    def snapshot_critical(self) -> dict[str, Any]:
        """Values of the CRITICAL_KEYS_RESTART fields right now, for later
        comparison — used to detect changes that require a soft-restart."""
        with self._lock:
            return {k: self._data.get(k) for k in CRITICAL_KEYS_RESTART}

    def critical_keys_changed(self, snapshot: dict[str, Any]) -> set[str]:
        """Which of CRITICAL_KEYS_RESTART differ from the given snapshot."""
        with self._lock:
            return {k for k in CRITICAL_KEYS_RESTART if self._data.get(k) != snapshot.get(k)}

    def session_path(self) -> str:
        """Full path (no extension) Telethon should use for the session file."""
        name = str(self._data.get("USER_SESSION") or "meow_account")
        return str(SESSION_DIR / name)


_singleton: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    global _singleton
    if _singleton is None:
        _singleton = ConfigManager()
    return _singleton
