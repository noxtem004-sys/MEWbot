"""
License Activation Page

Professional license input and validation UI.
This is the first screen users see - they must activate a valid license
before accessing the main application.

Features:
- License key input with formatting
- Real-time validation feedback
- Connection status display
- Error handling
- Activation progress indication
"""

import asyncio
import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QProgressBar, QTextEdit
)

from core.license_client import LicenseClient, LicenseStatus

logger = logging.getLogger(__name__)


class LicenseKeyInput(QLineEdit):
    """
    Custom line edit for license key input with automatic formatting.
    
    Automatically adds dashes after every 4 characters: XXXX-XXXX-XXXX-XXXX
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxLength(19)  # 16 chars + 3 dashes
        self.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.textChanged.connect(self._format_input)
        
        # Style
        self.setStyleSheet("""
            QLineEdit {
                font-size: 18px;
                font-family: monospace;
                padding: 12px;
                border: 2px solid #4a4d57;
                border-radius: 6px;
                background-color: #2b2d35;
                color: #e0e0e0;
                letter-spacing: 2px;
            }
            QLineEdit:focus {
                border-color: #5865f2;
            }
            QLineEdit[error="true"] {
                border-color: #ed4245;
            }
        """)
    
    def _format_input(self, text: str):
        """Auto-format license key with dashes"""
        # Remove all non-alphanumeric characters
        clean = ''.join(c for c in text.upper() if c.isalnum())
        
        # Add dashes every 4 characters
        formatted_parts = []
        for i in range(0, len(clean), 4):
            formatted_parts.append(clean[i:i+4])
        
        formatted = '-'.join(formatted_parts)
        
        # Update text without triggering textChanged again
        if formatted != text:
            cursor_pos = self.cursorPosition()
            self.blockSignals(True)
            self.setText(formatted)
            self.setCursorPosition(min(cursor_pos + 1, len(formatted)))
            self.blockSignals(False)
    
    def get_clean_key(self) -> str:
        """Get license key without dashes"""
        return self.text().replace('-', '').strip()
    
    def set_error_state(self, is_error: bool):
        """Set visual error state"""
        self.setProperty("error", str(is_error).lower())
        self.style().unpolish(self)
        self.style().polish(self)


class LicenseActivationPage(QWidget):
    """
    License activation page - first screen before main application.
    
    Signals:
        license_activated: Emitted when license is successfully activated
        activation_cancelled: Emitted when user cancels (if allow_cancel=True)
    """
    
    license_activated = Signal()
    activation_cancelled = Signal()
    
    def __init__(self, license_client: LicenseClient, allow_cancel: bool = False):
        super().__init__()
        self.license_client = license_client
        self.allow_cancel = allow_cancel
        self._activating = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Center container
        center_widget = QWidget()
        center_widget.setObjectName("licenseActivationCenter")
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(20)
        
        # Card frame
        card = QFrame()
        card.setObjectName("licenseActivationCard")
        card.setMinimumWidth(500)
        card.setMaximumWidth(600)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)
        
        # Logo/Title area
        title_container = QVBoxLayout()
        title_container.setSpacing(8)
        title_container.setAlignment(Qt.AlignCenter)
        
        self.app_title = QLabel("🔐 License Activation")
        self.app_title.setObjectName("licenseTitle")
        self.app_title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        self.app_title.setFont(title_font)
        
        self.app_subtitle = QLabel("Telegram Meow Bot")
        self.app_subtitle.setObjectName("licenseSubtitle")
        self.app_subtitle.setAlignment(Qt.AlignCenter)
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        self.app_subtitle.setFont(subtitle_font)
        
        title_container.addWidget(self.app_title)
        title_container.addWidget(self.app_subtitle)
        card_layout.addLayout(title_container)
        
        # Instruction label
        self.instruction_label = QLabel(
            "Please enter your license key to activate the application."
        )
        self.instruction_label.setObjectName("licenseInstruction")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setWordWrap(True)
        card_layout.addWidget(self.instruction_label)
        
        # License key input
        input_container = QVBoxLayout()
        input_container.setSpacing(8)
        
        input_label = QLabel("License Key:")
        input_label.setObjectName("licenseInputLabel")
        
        self.license_input = LicenseKeyInput()
        self.license_input.returnPressed.connect(self._on_activate_clicked)
        
        input_container.addWidget(input_label)
        input_container.addWidget(self.license_input)
        card_layout.addLayout(input_container)
        
        # Status display
        self.status_container = QFrame()
        self.status_container.setObjectName("licenseStatusContainer")
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)
        
        self.status_label = QLabel("Ready to activate")
        self.status_label.setObjectName("licenseStatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("licenseProgressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximum(0)  # Indeterminate
        self.progress_bar.hide()
        
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        
        card_layout.addWidget(self.status_container)
        
        # Error display
        self.error_container = QFrame()
        self.error_container.setObjectName("licenseErrorContainer")
        error_layout = QVBoxLayout(self.error_container)
        error_layout.setContentsMargins(12, 12, 12, 12)
        
        self.error_label = QLabel()
        self.error_label.setObjectName("licenseErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignCenter)
        
        error_layout.addWidget(self.error_label)
        self.error_container.hide()
        
        card_layout.addWidget(self.error_container)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        if self.allow_cancel:
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.setObjectName("licenseCancelButton")
            self.cancel_button.clicked.connect(self._on_cancel_clicked)
            button_layout.addWidget(self.cancel_button)
        
        button_layout.addStretch()
        
        self.activate_button = QPushButton("Activate License")
        self.activate_button.setObjectName("licenseActivateButton")
        self.activate_button.setMinimumHeight(44)
        self.activate_button.clicked.connect(self._on_activate_clicked)
        button_layout.addWidget(self.activate_button)
        
        card_layout.addLayout(button_layout)
        
        # Device info (small text at bottom)
        device_id = self.license_client.get_device_id()
        self.device_info_label = QLabel(f"Device ID: {device_id[:16]}...")
        self.device_info_label.setObjectName("licenseDeviceInfo")
        self.device_info_label.setAlignment(Qt.AlignCenter)
        device_font = QFont()
        device_font.setPointSize(8)
        self.device_info_label.setFont(device_font)
        card_layout.addWidget(self.device_info_label)
        
        # Add card to center layout
        center_layout.addWidget(card)
        
        # Add center widget to main layout
        layout.addWidget(center_widget)
        
        # Apply styles
        self._apply_styles()
    
    def _apply_styles(self):
        """Apply custom styles to the page"""
        self.setStyleSheet("""
            QWidget#licenseActivationCenter {
                background-color: #1e1f26;
            }
            
            QFrame#licenseActivationCard {
                background-color: #2b2d35;
                border-radius: 12px;
                border: 1px solid #3a3c45;
            }
            
            QLabel#licenseTitle {
                color: #ffffff;
            }
            
            QLabel#licenseSubtitle {
                color: #b0b3ba;
            }
            
            QLabel#licenseInstruction {
                color: #d0d3da;
                padding: 10px;
            }
            
            QLabel#licenseInputLabel {
                color: #e0e0e0;
                font-weight: bold;
            }
            
            QFrame#licenseStatusContainer {
                background-color: #35373f;
                border-radius: 6px;
                border: 1px solid #4a4d57;
            }
            
            QLabel#licenseStatusLabel {
                color: #b0b3ba;
                font-size: 13px;
            }
            
            QProgressBar#licenseProgressBar {
                border: none;
                background-color: #2b2d35;
                border-radius: 3px;
                height: 6px;
            }
            
            QProgressBar#licenseProgressBar::chunk {
                background-color: #5865f2;
                border-radius: 3px;
            }
            
            QFrame#licenseErrorContainer {
                background-color: #ed4245;
                border-radius: 6px;
                padding: 4px;
            }
            
            QLabel#licenseErrorLabel {
                color: #ffffff;
                font-weight: bold;
            }
            
            QPushButton#licenseActivateButton {
                background-color: #5865f2;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 12px 32px;
                font-size: 14px;
                font-weight: bold;
            }
            
            QPushButton#licenseActivateButton:hover {
                background-color: #4752c4;
            }
            
            QPushButton#licenseActivateButton:pressed {
                background-color: #3c45a5;
            }
            
            QPushButton#licenseActivateButton:disabled {
                background-color: #4a4d57;
                color: #72767d;
            }
            
            QPushButton#licenseCancelButton {
                background-color: #4a4d57;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
            }
            
            QPushButton#licenseCancelButton:hover {
                background-color: #5a5d67;
            }
            
            QLabel#licenseDeviceInfo {
                color: #72767d;
            }
        """)
    
    def _set_status(self, message: str, show_progress: bool = False):
        """Update status message"""
        self.status_label.setText(message)
        if show_progress:
            self.progress_bar.show()
        else:
            self.progress_bar.hide()
    
    def _show_error(self, message: str):
        """Show error message"""
        self.error_label.setText(f"❌ {message}")
        self.error_container.show()
        self.license_input.set_error_state(True)
    
    def _clear_error(self):
        """Clear error message"""
        self.error_container.hide()
        self.license_input.set_error_state(False)
    
    def _on_activate_clicked(self):
        """Handle activate button click"""
        if self._activating:
            return
        
        license_key = self.license_input.text().strip()
        
        if not license_key:
            self._show_error("Please enter a license key")
            return
        
        # Basic format validation
        clean_key = self.license_input.get_clean_key()
        if len(clean_key) != 16:
            self._show_error("Invalid license key format (expected 16 characters)")
            return
        
        # Clear previous errors
        self._clear_error()
        
        # Start activation
        asyncio.ensure_future(self._activate_license(license_key))
    
    async def _activate_license(self, license_key: str):
        """Perform license activation"""
        self._activating = True
        self.activate_button.setEnabled(False)
        self.license_input.setEnabled(False)
        
        self._set_status("Connecting to license server...", show_progress=True)
        
        try:
            # Perform activation
            result = await self.license_client.activate_license(license_key)
            
            if result.get('success'):
                # Success!
                self._set_status("✅ License activated successfully!", show_progress=False)
                
                # Show expiration info
                expires_at = result.get('expires_at', 'N/A')
                self.instruction_label.setText(
                    f"License activated successfully!\n"
                    f"Expires: {expires_at}"
                )
                
                # Wait a moment then emit signal
                await asyncio.sleep(1)
                self.license_activated.emit()
            else:
                # Activation failed
                error_message = result.get('message', 'Unknown error')
                self._show_error(error_message)
                self._set_status("Activation failed", show_progress=False)
                
                # Re-enable input
                self.license_input.setEnabled(True)
                self.activate_button.setEnabled(True)
                self._activating = False
        
        except Exception as e:
            logger.error(f"License activation error: {e}", exc_info=True)
            self._show_error(f"Activation error: {str(e)}")
            self._set_status("Activation failed", show_progress=False)
            
            # Re-enable input
            self.license_input.setEnabled(True)
            self.activate_button.setEnabled(True)
            self._activating = False
    
    def _on_cancel_clicked(self):
        """Handle cancel button click"""
        if self._activating:
            return
        
        self.activation_cancelled.emit()
    
    async def check_existing_license(self) -> bool:
        """
        Check if there's an existing valid license.
        
        Returns True if valid license exists, False otherwise.
        """
        self._set_status("Checking for existing license...", show_progress=True)
        
        try:
            # Try to validate existing license
            result = await self.license_client.validate_license()
            
            if result.get('valid'):
                # Valid license found
                status = result.get('status', '')
                
                if status == LicenseStatus.GRACE_PERIOD:
                    # In grace period (server unreachable)
                    grace_remaining = result.get('grace_period_remaining', 0)
                    self._set_status(
                        f"⚠️ License valid (offline mode, {grace_remaining}s grace period)",
                        show_progress=False
                    )
                else:
                    # Fully valid
                    expires_at = result.get('expires_at_utc', 0)
                    if expires_at:
                        remaining = result.get('remaining_seconds', 0)
                        days = remaining // 86400
                        hours = (remaining % 86400) // 3600
                        
                        time_str = f"{days}d {hours}h" if days > 0 else f"{hours}h"
                        self._set_status(
                            f"✅ License valid ({time_str} remaining)",
                            show_progress=False
                        )
                
                # Wait a moment then proceed
                await asyncio.sleep(1)
                return True
            else:
                # No valid license
                self._set_status("Ready to activate", show_progress=False)
                return False
        
        except Exception as e:
            logger.error(f"Error checking existing license: {e}")
            self._set_status("Ready to activate", show_progress=False)
            return False


class LicenseActivationDialog(QWidget):
    """
    Standalone license activation dialog/window.
    
    Can be used as the main window when the application starts.
    """
    
    license_activated = Signal()
    
    def __init__(self, license_client: LicenseClient):
        super().__init__()
        self.license_client = license_client
        
        self.setWindowTitle("License Activation - Telegram Meow Bot")
        self.setMinimumSize(700, 500)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # License activation page
        self.activation_page = LicenseActivationPage(license_client, allow_cancel=False)
        self.activation_page.license_activated.connect(self._on_license_activated)
        
        layout.addWidget(self.activation_page)
        
        # Set window flags to prevent closing without activation
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.CustomizeWindowHint
        )
    
    def _on_license_activated(self):
        """Handle successful license activation"""
        self.license_activated.emit()
    
    async def initialize(self) -> bool:
        """
        Initialize and check for existing license.
        
        Returns True if valid license exists, False if activation needed.
        """
        return await self.activation_page.check_existing_license()
