from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)


class LoginDialog(QDialog):
    """Shown on demand when the backend reports it needs phone/code/2FA.

    submitted(kind, value) is emitted; MainWindow forwards the value to the
    runtime (runtime.submit_phone / submit_code / submit_password).
    """

    submitted = Signal(str, str)   # kind in {"phone","code","password"}, value
    cancelled = Signal()

    _STEP_META = {
        "phone": ("📱", "ورود به حساب", "شماره تلفن حساب تلگرام خود را وارد کنید."),
        "code": ("🔢", "کد تأیید", "کدی که تلگرام برایتان ارسال کرده را وارد کنید."),
        "password": ("🔒", "رمز دومرحله‌ای", "رمز عبور دومرحله‌ای حساب خود را وارد کنید."),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loginDialog")
        self.setWindowTitle("ورود به حساب")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setModal(True)
        self.setMinimumWidth(380)

        self._kind = None

        self.icon_label = QLabel("📱")
        self.icon_label.setStyleSheet("font-size: 30px;")
        self.title_label = QLabel("ورود به حساب")
        self.title_label.setObjectName("loginTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("loginSubtitle")
        self.subtitle_label.setWordWrap(True)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(self.title_label)
        header_text.addWidget(self.subtitle_label)
        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        header_row.addWidget(self.icon_label)
        header_row.addLayout(header_text, 1)

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("مثلاً 989121234567+")
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("کد ارسال‌شده در تلگرام")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("رمز عبور دومرحله‌ای")

        form = QFormLayout()
        form.setSpacing(10)
        self.phone_row = ("شماره تلفن:", self.phone_edit)
        self.code_row = ("کد تأیید:", self.code_edit)
        self.password_row = ("رمز دومرحله‌ای:", self.password_edit)
        for label, widget in (self.phone_row, self.code_row, self.password_row):
            form.addRow(QLabel(label), widget)
        self._form = form

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #ff6b61; font-size: 12px;")

        self.submit_btn = QPushButton("ورود")
        self.submit_btn.setObjectName("primaryBtn")
        self.cancel_btn = QPushButton("انصراف")
        self.cancel_btn.setObjectName("ghostBtn")
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.submit_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)
        layout.addLayout(header_row)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(btn_row)

        self.submit_btn.clicked.connect(self._on_submit)
        self.cancel_btn.clicked.connect(self._on_cancel)

        self._show_only("phone")

    def _show_only(self, kind: str) -> None:
        self._kind = kind
        self.phone_edit.setVisible(kind == "phone")
        self.code_edit.setVisible(kind == "code")
        self.password_edit.setVisible(kind == "password")
        # Hide the LABEL together with its field for the two inactive steps —
        # setRowVisible keeps the label from lingering on screen once the
        # field it describes is hidden (previously only the field itself
        # was hidden, leaving all three row labels visible at once).
        self._form.setRowVisible(self.phone_edit, kind == "phone")
        self._form.setRowVisible(self.code_edit, kind == "code")
        self._form.setRowVisible(self.password_edit, kind == "password")
        icon, title, subtitle = self._STEP_META[kind]
        self.icon_label.setText(icon)
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.setWindowTitle(title)

    def request(self, kind: str) -> None:
        """Called by MainWindow when the backend needs a new field."""
        self.status_label.setText("")
        self._show_only(kind)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        {"phone": self.phone_edit, "code": self.code_edit, "password": self.password_edit}[kind].setFocus()

    def set_error(self, message_fa: str) -> None:
        self.status_label.setText(message_fa)

    def _on_submit(self) -> None:
        value = {
            "phone": self.phone_edit.text(),
            "code": self.code_edit.text(),
            "password": self.password_edit.text(),
        }[self._kind]
        if not value.strip():
            self.status_label.setText("این فیلد الزامی است.")
            return
        self.submitted.emit(self._kind, value)

    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self.reject()
