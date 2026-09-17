from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from core.config_manager import SCHEMA, SECTION_LABELS_FA

SECTION_ICONS_FA = {
    "account": "👤",
    "api": "🔑",
    "bots": "🤖",
    "messages": "💬",
    "keywords": "🏷",
    "timing": "⏱",
    "advanced": "🛠",
}


class SecretField(QWidget):
    """A password-style field with a show/hide eye button, per spec §10."""

    def __init__(self, initial: str = ""):
        super().__init__()
        self.edit = QLineEdit(initial)
        self.edit.setEchoMode(QLineEdit.Password)
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("👁")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._toggle)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit)
        row.addWidget(self.toggle_btn)

    def _toggle(self, checked: bool) -> None:
        self.edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


class SettingsPage(QWidget):
    settings_saved = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.config = config
        self._widgets: dict[str, QWidget] = {}

        self.tabs = QTabWidget()
        sections = list(dict.fromkeys(f.section for f in SCHEMA))
        for section in sections:
            icon = SECTION_ICONS_FA.get(section, "")
            self.tabs.addTab(self._build_section_tab(section), f"{icon}  {SECTION_LABELS_FA.get(section, section)}")

        self.save_btn = QPushButton("💾  ذخیره تنظیمات")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.clicked.connect(self._on_save)
        note = QLabel(
            "توجه: تغییر شناسه نشست، API و توکن ربات پس از «توقف» و «شروع» دوباره اعمال می‌شود."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")

        footer = QHBoxLayout()
        footer.addWidget(note, 1)
        footer.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(footer)

    def _build_section_tab(self, section: str) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(16)
        for f in SCHEMA:
            if f.section != section:
                continue
            current = self.config.get(f.key)
            if f.type == "secret":
                widget = SecretField(str(current or ""))
            elif f.type == "int":
                widget = QSpinBox()
                widget.setRange(-2_147_483_648, 2_147_483_647)
                widget.setValue(int(current or 0))
            else:
                widget = QLineEdit(str(current or ""))
            self._widgets[f.key] = widget
            label = f.label_fa + (" *" if f.required else "")
            row_label = QLabel(label)
            row_label.setStyleSheet("color: #c9cad0;")
            if f.help_fa:
                row_label.setToolTip(f.help_fa)
            form.addRow(row_label, widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 4, 0, 4)
        wrapper_layout.addWidget(card)
        wrapper_layout.addStretch(1)
        scroll.setWidget(wrapper)
        return scroll

    def _collect_values(self) -> dict:
        values = {}
        for f in SCHEMA:
            widget = self._widgets[f.key]
            if f.type == "int":
                values[f.key] = widget.value()
            elif f.type == "secret":
                values[f.key] = widget.text()
            else:
                values[f.key] = widget.text()
        return values

    def _on_save(self) -> None:
        self.config.set_many(self._collect_values())
        problems = self.config.validate()
        if problems:
            QMessageBox.warning(
                self,
                "تنظیمات ناقص",
                "امکان اجرای برنامه وجود ندارد.\n\nموارد ناقص:\n" + "\n".join(f"• {p}" for p in problems),
            )
        else:
            QMessageBox.information(self, "ذخیره شد", "تنظیمات با موفقیت ذخیره شد.")
        self.settings_saved.emit()

    def refresh_from_config(self) -> None:
        for f in SCHEMA:
            widget = self._widgets[f.key]
            current = self.config.get(f.key)
            if f.type == "int":
                widget.setValue(int(current or 0))
            else:
                widget.setText(str(current or ""))
