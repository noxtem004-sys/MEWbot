"""
Production configuration for Telegram Meow GUI Client
This file contains hardcoded configuration for distribution
"""

# Application Info
APP_NAME = "Telegram Meow GUI"
APP_VERSION = "1.0.0"
APP_AUTHOR = "noxtem004-sys"

# License Server Configuration (HARDCODED for production)
LICENSE_SERVER_URL = "https://mewbot-production-c860.up.railway.app"
LICENSE_SERVER_SECRET_KEY = "eye74hyhwhi892746hqdno8yrhwi9y080r3y"

# Client Settings
LICENSE_VALIDATION_INTERVAL = 300  # 5 minutes
LICENSE_GRACE_PERIOD = 1800  # 30 minutes

# Feature Flags
REQUIRE_LICENSE = True  # Set to False to disable license check for testing
ALLOW_OFFLINE_MODE = False  # Set to True to allow unlimited offline operation
