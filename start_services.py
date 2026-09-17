"""
Helper script to start both License Server and Bot together
Useful for Railway deployment
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def start_server():
    """Start license server"""
    from backend.license_server import main as server_main
    try:
        await server_main()
    except Exception as e:
        logger.error(f"Server error: {e}")


async def start_bot():
    """Start license bot"""
    from backend.license_bot import main as bot_main
    try:
        await bot_main()
    except Exception as e:
        logger.error(f"Bot error: {e}")


async def main():
    """Start both services"""
    # Check which service to run based on environment
    service = os.environ.get('SERVICE_TYPE', 'server').lower()
    
    if service == 'bot':
        logger.info("Starting License Bot...")
        await start_bot()
    elif service == 'server':
        logger.info("Starting License Server...")
        await start_server()
    else:
        # Run both (for local development only)
        logger.info("Starting both services...")
        await asyncio.gather(
            start_server(),
            start_bot()
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
