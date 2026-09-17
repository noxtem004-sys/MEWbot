from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget,
)

STATUS_FA = {
    "stopped": ("متوقف", "#9aa0a6", "#2a2d35"),
    "starting": ("در حال شروع", "#0f1114", "#f4b400"),
    "need_login": ("نیاز به ورود", "#0f1114", "#f4b400"),
    "running": ("در حال اجرا", "#0f1114", "#34c759"),
    "error": ("خطا", "#ffffff", "#e2574c"),
}

LEVEL_COLORS = {
    "DEBUG": "#7d818c",
    "INFO": "#c9cad0",
    "SUCCESS": "#34c759",
    "WARNING": "#f4b400",
    "ERROR": "#ff6b61",
}


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


class DashboardPage(QWidget):
    start_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self._uptime_seconds = 0

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(0, 0, 0, 0)

        # ---------- top card: status + uptime + controls ----------
        top_card = _card()
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(20, 18, 20, 18)
        top_layout.setSpacing(16)

        header_row = QHBoxLayout()
        title = QLabel("داشبورد اجرا")
        title.setObjectName("cardTitle")
        title.setStyleSheet("font-size: 16px;")
        self.status_pill = QLabel("متوقف")
        self.status_pill.setObjectName("statusPill")
        self.uptime_caption = QLabel("مدت زمان اجرا")
        self.uptime_caption.setObjectName("cardHint")
        self.uptime_value = QLabel("00:00:00")
        self.uptime_value.setObjectName("uptimeValue")
        uptime_box = QVBoxLayout()
        uptime_box.setSpacing(2)
        uptime_box.addWidget(self.uptime_caption, 0, Qt.AlignLeft)
        uptime_box.addWidget(self.uptime_value, 0, Qt.AlignLeft)

        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addLayout(uptime_box)
        header_row.addSpacerItem(QSpacerItem(24, 1, QSizePolicy.Fixed))
        header_row.addWidget(self.status_pill)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)
        self.start_btn = QPushButton("▶  شروع")
        self.start_btn.setObjectName("primaryBtn")
        self.stop_btn = QPushButton("■  توقف")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setEnabled(False)
        controls_row.addWidget(self.start_btn)
        controls_row.addWidget(self.stop_btn)
        controls_row.addStretch(1)

        top_layout.addLayout(header_row)
        top_layout.addLayout(controls_row)

        # ---------- log card ----------
        log_card = _card()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 14, 16, 16)
        log_layout.setSpacing(10)

        log_header = QHBoxLayout()
        log_title = QLabel("لاگ‌ها / ترمینال")
        log_title.setObjectName("cardTitle")
        self.autoscroll_chk = QCheckBox("پیمایش خودکار")
        self.autoscroll_chk.setChecked(True)
        self.clear_btn = QPushButton("پاک کردن")
        self.clear_btn.setObjectName("ghostBtn")
        self.copy_btn = QPushButton("کپی")
        self.copy_btn.setObjectName("ghostBtn")
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        log_header.addWidget(self.autoscroll_chk)
        log_header.addWidget(self.clear_btn)
        log_header.addWidget(self.copy_btn)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("terminal")
        self.log_view.setLayoutDirection(Qt.LeftToRight)

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_view, 1)

        root.addWidget(top_card)
        root.addWidget(log_card, 1)

        self.start_btn.clicked.connect(self.start_clicked.emit)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        self.clear_btn.clicked.connect(self.log_view.clear)
        self.copy_btn.clicked.connect(self._copy_logs)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_uptime)

    # -- status / lifecycle -------------------------------------------------
    def set_status(self, status_key: str) -> None:
        label, fg, bg = STATUS_FA.get(status_key, (status_key, "#e9e9ee", "#2a2d35"))
        self.status_pill.setText(label)
        self.status_pill.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 13px; "
            f"padding: 6px 16px; font-weight: 700; font-size: 13px;"
        )
        running = status_key == "running"
        starting = status_key == "starting"
        self.start_btn.setEnabled(not running and not starting)
        self.stop_btn.setEnabled(running or starting or status_key == "need_login")
        if running and not self._timer.isActive():
            self._uptime_seconds = 0
            self._timer.start()
        elif not running and self._timer.isActive():
            self._timer.stop()

    def _tick_uptime(self) -> None:
        self._uptime_seconds += 1
        h, rem = divmod(self._uptime_seconds, 3600)
        m, s = divmod(rem, 60)
        self.uptime_value.setText(f"{h:02d}:{m:02d}:{s:02d}")

    # -- logs -----------------------------------------------------------------
    def append_log(self, timestamp: str, level: str, message: str) -> None:
        color = LEVEL_COLORS.get(level, "#c9cad0")
        line = f'<span style="color:#5c606b">[{timestamp}]</span> ' \
               f'<span style="color:{color}; font-weight:600">[{level}]</span> ' \
               f'<span style="color:#e2e2e6">{_escape(message)}</span>'
        self.log_view.appendHtml(line)
        if self.autoscroll_chk.isChecked():
            self.log_view.moveCursor(QTextCursor.End)

    def _copy_logs(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log_view.toPlainText())


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
