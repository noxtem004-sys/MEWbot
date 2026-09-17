import asyncio
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from bot_core import MeowBotRuntime, Status
from core.logging_bridge import QtLogHandler, install_gui_logging
from gui.pages.dashboard_page import DashboardPage
from gui.pages.login_dialog import LoginDialog
from gui.pages.settings_page import SettingsPage

logger = logging.getLogger(__name__)

NAV_ITEMS = [
    ("dashboard", "🏠   داشبورد"),
    ("settings", "⚙   تنظیمات"),
    ("about", "ℹ   درباره برنامه"),
]

ICON_PATH = Path(__file__).parent / "resources" / "icons" / "app.png"


def _about_page() -> QWidget:
    w = QWidget()
    outer = QVBoxLayout(w)
    outer.setAlignment(Qt.AlignTop)

    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(10)

    title = QLabel("🐾  Telegram Meow Bot")
    title.setObjectName("cardTitle")
    title.setStyleSheet("font-size: 18px;")
    version = QLabel("نسخه ۱.۰")
    version.setObjectName("cardHint")
    body = QLabel(
        "برنامه دسکتاپ فارسی برای کنترل ربات میو (aiogram + Telethon).\n"
        "این پنجره فقط رابط کاربری است؛ تمام منطق واقعی در بک‌اند پایتون اجرا می‌شود."
    )
    body.setWordWrap(True)
    body.setStyleSheet("color: #c9cad0; line-height: 150%;")

    layout.addWidget(title)
    layout.addWidget(version)
    layout.addSpacing(6)
    layout.addWidget(body)
    outer.addWidget(card)
    return w


def _build_sidebar_panel() -> tuple[QFrame, QListWidget]:
    panel = QFrame()
    panel.setObjectName("sidebarPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 18, 14, 14)
    layout.setSpacing(4)

    header = QHBoxLayout()
    header.setSpacing(8)
    logo = QLabel()
    if ICON_PATH.exists():
        logo.setPixmap(QIcon(str(ICON_PATH)).pixmap(30, 30))
    title_box = QVBoxLayout()
    title_box.setSpacing(0)
    app_title = QLabel("میو بات")
    app_title.setObjectName("appTitle")
    app_subtitle = QLabel("Telegram Meow Bot")
    app_subtitle.setObjectName("appSubtitle")
    title_box.addWidget(app_title)
    title_box.addWidget(app_subtitle)
    header.addWidget(logo)
    header.addLayout(title_box)
    header.addStretch(1)

    sidebar = QListWidget()
    sidebar.setObjectName("sidebar")

    layout.addLayout(header)
    layout.addSpacing(10)
    layout.addWidget(sidebar, 1)
    version_label = QLabel("نسخه ۱.۰")
    version_label.setObjectName("versionLabel")
    version_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(version_label)

    return panel, sidebar


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("Telegram Meow Bot")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1040, 680)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._closing = False

        self.config = config
        self.license_client = None  # Will be set by app.py after license validation
        
        self.runtime = MeowBotRuntime(config)
        self.runtime.on_status_changed = self._on_status_changed
        self.runtime.on_login_required = self._on_login_required

        self.log_handler = QtLogHandler()
        install_gui_logging(self.log_handler)
        self.log_handler.record_emitted.connect(self._on_log_record)

        self.login_dialog = LoginDialog(self)
        self.login_dialog.submitted.connect(self._on_login_submitted)
        self.login_dialog.cancelled.connect(self._on_login_cancelled)

        self.sidebar_panel, self.sidebar = _build_sidebar_panel()
        for key, label_fa in NAV_ITEMS:
            item = QListWidgetItem(label_fa)
            item.setData(Qt.UserRole, key)
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)

        self.dashboard_page = DashboardPage()
        self.dashboard_page.start_clicked.connect(self._on_start_clicked)
        self.dashboard_page.stop_clicked.connect(self._on_stop_clicked)

        self.settings_page = SettingsPage(config)
        self.settings_page.settings_saved.connect(self._on_settings_saved)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.dashboard_page)   # index 0
        self.stack.addWidget(self.settings_page)    # index 1
        self.stack.addWidget(_about_page())          # index 2

        central = QWidget()
        central.setObjectName("body")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        
        # Add license status bar at the top
        self.license_status_bar = self._create_license_status_bar()
        root.addWidget(self.license_status_bar)
        
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(14, 14, 14, 14)
        body_layout.setSpacing(14)
        body_layout.addWidget(self.stack, 1)
        body_layout.addWidget(self.sidebar_panel)  # RTL: sidebar visually on the right
        root.addWidget(body)
        self.setCentralWidget(central)

        self.sidebar.setCurrentRow(0)
        self.dashboard_page.set_status(Status.STOPPED.value)
        
        # Update license status periodically
        self._update_license_status_timer = asyncio.ensure_future(self._update_license_status_loop())

    # -- navigation -------------------------------------------------------------
    def _on_nav_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
    
    # -- license status ---------------------------------------------------------
    def _create_license_status_bar(self) -> QWidget:
        """Create license status bar widget"""
        status_bar = QFrame()
        status_bar.setObjectName("licenseStatusBar")
        status_bar.setMaximumHeight(40)
        status_bar.setStyleSheet("""
            QFrame#licenseStatusBar {
                background-color: #2b2d35;
                border-bottom: 1px solid #3a3c45;
            }
            QLabel#licenseStatusLabel {
                color: #b0b3ba;
                padding: 8px 16px;
            }
        """)
        
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(16, 4, 16, 4)
        
        self.license_status_label = QLabel("License: Checking...")
        self.license_status_label.setObjectName("licenseStatusLabel")
        
        layout.addWidget(self.license_status_label)
        layout.addStretch()
        
        return status_bar
    
    async def _update_license_status_loop(self):
        """Periodically update license status display"""
        while True:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                self._update_license_status_display()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating license status: {e}")
    
    def _update_license_status_display(self):
        """Update the license status bar display"""
        if not self.license_client:
            self.license_status_label.setText("License: Unknown")
            return
        
        license_info = self.license_client.get_cached_license_info()
        
        if not license_info:
            self.license_status_label.setText("🔒 License: Not Activated")
            return
        
        # Get remaining time
        remaining_seconds = self.license_client.get_time_remaining()
        
        if remaining_seconds <= 0:
            self.license_status_label.setText("⏰ License: Expired")
            self.license_status_label.setStyleSheet("color: #ed4245; font-weight: bold;")
        elif remaining_seconds < 86400:  # Less than 1 day
            hours = remaining_seconds // 3600
            self.license_status_label.setText(f"⚠️ License: Expires in {hours}h")
            self.license_status_label.setStyleSheet("color: #faa61a; font-weight: bold;")
        elif remaining_seconds < 604800:  # Less than 7 days
            days = remaining_seconds // 86400
            self.license_status_label.setText(f"✅ License: {days} days remaining")
            self.license_status_label.setStyleSheet("color: #57f287;")
        else:
            days = remaining_seconds // 86400
            self.license_status_label.setText(f"✅ License: Active ({days} days)")
            self.license_status_label.setStyleSheet("color: #57f287;")

    # -- start/stop ---------------------------------------------------------------
    def _on_start_clicked(self) -> None:
        asyncio.ensure_future(self._start_backend())

    async def _start_backend(self) -> None:
        await self.runtime.start()

    def _on_stop_clicked(self) -> None:
        asyncio.ensure_future(self._stop_backend())

    async def _stop_backend(self) -> None:
        await self.runtime.stop()
        self.login_dialog.hide()

    def _on_settings_saved(self) -> None:
        asyncio.ensure_future(self.runtime.apply_settings_change())

    # -- status / logs ------------------------------------------------------------
    def _on_status_changed(self, status: Status) -> None:
        self.dashboard_page.set_status(status.value)
        if status in (Status.RUNNING, Status.STOPPED, Status.ERROR):
            self.login_dialog.hide()

    def _on_log_record(self, ts: str, level: str, message: str) -> None:
        self.dashboard_page.append_log(ts, level, message)

    # -- login dialog wiring ---------------------------------------------------------
    def _on_login_required(self, kind: str) -> None:
        self.dashboard_page.set_status("need_login")
        self.login_dialog.request(kind)

    def _on_login_submitted(self, kind: str, value: str) -> None:
        if kind == "phone":
            self.runtime.submit_phone(value)
        elif kind == "code":
            self.runtime.submit_code(value)
        elif kind == "password":
            self.runtime.submit_password(value)

    def _on_login_cancelled(self) -> None:
        asyncio.ensure_future(self._stop_backend())

    # -- shutdown -------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        # Closing the window must not just schedule stop() and let Qt tear
        # the app down immediately — asyncio.ensure_future() only queues
        # the coroutine; if the app quits before the loop gets to run it to
        # completion, the Telethon connection/aiogram polling/bot HTTP
        # session are never actually closed (a real resource leak). So:
        # ignore the close, run the real shutdown, THEN quit for real.
        if self.runtime.status == Status.STOPPED:
            event.accept()
            return
        event.ignore()
        if self._closing:
            return
        self._closing = True
        self.setEnabled(False)
        asyncio.ensure_future(self._shutdown_and_quit())

    async def _shutdown_and_quit(self) -> None:
        try:
            await self.runtime.stop()
        finally:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()
