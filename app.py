"""
Entry point for the Telegram Meow Bot desktop application.

Run with:  python app.py

Architecture note: qasync lets the Telethon/aiogram asyncio code and the
Qt GUI share a single event loop in a single thread. There is no
subprocess, no separate worker thread, and no polling — button clicks
schedule real coroutines on the same loop that runs the backend.

License Protection: The application checks for a valid license on startup.
Users must activate a license before accessing the main application.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Make backend/ importable as top-level modules (config, database, user_client,
# bot_core, handlers.*) exactly as the original project expected, while core/
# and gui/ stay as proper packages.
sys.path.insert(0, str(Path(__file__).parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

import qasync
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from core.config_manager import get_config
from core.license_client import LicenseClient
from gui.main_window import MainWindow
from gui.pages.license_activation_page import LicenseActivationDialog

logger = logging.getLogger(__name__)


def _load_persian_font(app: QApplication) -> None:
    """Bundle Vazirmatn (OFL-licensed) under gui/resources/fonts if present;
    otherwise fall back to the OS's default Persian-capable font."""
    fonts_dir = Path(__file__).parent / "gui" / "resources" / "fonts"
    if fonts_dir.exists():
        for f in fonts_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(f))


def _get_license_config():
    """Get license server configuration from environment"""
    server_url = os.environ.get('LICENSE_SERVER_URL', 'http://localhost:8765')
    secret_key = os.environ.get('LICENSE_SERVER_SECRET_KEY', '')
    
    if not secret_key:
        logger.warning("LICENSE_SERVER_SECRET_KEY not set, using default (NOT SECURE)")
        secret_key = 'default_secret_key_CHANGE_ME'
    
    validation_interval = int(os.environ.get('LICENSE_VALIDATION_INTERVAL', '300'))  # 5 minutes
    grace_period = int(os.environ.get('LICENSE_GRACE_PERIOD', '1800'))  # 30 minutes
    
    return {
        'server_url': server_url,
        'secret_key': secret_key,
        'validation_interval': validation_interval,
        'grace_period': grace_period
    }


async def check_and_activate_license(
    app: QApplication,
    license_client: LicenseClient
) -> bool:
    """
    Check for valid license and show activation dialog if needed.
    
    Returns True if license is valid, False if user cancelled.
    """
    # Initialize license client
    await license_client.initialize()
    
    # Check if valid license already exists
    result = await license_client.validate_license()
    
    if result.get('valid'):
        logger.info("Valid license found, proceeding to main application")
        return True
    
    # No valid license - show activation dialog
    logger.info("No valid license found, showing activation dialog")
    
    activation_dialog = LicenseActivationDialog(license_client)
    
    # Check for existing license in activation dialog
    has_valid_license = await activation_dialog.initialize()
    
    if has_valid_license:
        logger.info("Valid license verified, proceeding to main application")
        return True
    
    # Show activation dialog
    activation_dialog.show()
    
    # Wait for activation
    license_activated = False
    
    def on_license_activated():
        nonlocal license_activated
        license_activated = True
        activation_dialog.close()
    
    activation_dialog.license_activated.connect(on_license_activated)
    
    # Wait for the dialog to close
    while activation_dialog.isVisible():
        await asyncio.sleep(0.1)
        app.processEvents()
    
    if license_activated:
        logger.info("License activated successfully")
        return True
    else:
        logger.warning("License activation cancelled or failed")
        return False


def main() -> int:
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("TelegramMeowGUI")
    _load_persian_font(app)

    icon_path = Path(__file__).parent / "gui" / "resources" / "icons" / "app.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    qss_path = Path(__file__).parent / "gui" / "styles" / "app.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Get license configuration
    license_config = _get_license_config()
    
    # Create license client
    license_client = LicenseClient(
        server_url=license_config['server_url'],
        secret_key=license_config['secret_key'],
        validation_interval=license_config['validation_interval'],
        grace_period=license_config['grace_period']
    )
    
    # Set up license invalid callback
    def on_license_invalid(status: str, message: str):
        logger.error(f"License became invalid: {status} - {message}")
        
        # Show error dialog
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("License Invalid")
        msg.setText("Your license is no longer valid.")
        msg.setInformativeText(f"{status}: {message}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
        
        # Exit application
        app.quit()
    
    license_client.on_license_invalid = on_license_invalid
    
    async def startup_sequence():
        """Async startup sequence with license check"""
        try:
            # Check and activate license
            license_valid = await check_and_activate_license(app, license_client)
            
            if not license_valid:
                logger.error("License validation failed, exiting")
                app.quit()
                return
            
            # Start periodic validation
            await license_client.start_periodic_validation()
            
            # Create and show main window
            config = get_config()
            window = MainWindow(config)
            window.license_client = license_client  # Attach license client
            window.show()
            
            logger.info("Application started successfully")
            
        except Exception as e:
            logger.error(f"Startup error: {e}", exc_info=True)
            
            # Show error dialog
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Startup Error")
            msg.setText("Failed to start the application.")
            msg.setInformativeText(str(e))
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            
            app.quit()
    
    # Schedule startup sequence
    asyncio.ensure_future(startup_sequence())
    
    # Run event loop
    with loop:
        exit_code = loop.run_forever()
    
    # Cleanup
    try:
        loop.run_until_complete(license_client.stop_periodic_validation())
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
