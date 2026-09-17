"""
Database module for the Telegram bot.
Provides async SQLite support for logging bot operations.
"""

import aiosqlite
import logging
from datetime import datetime
from typing import Optional

from core.config_manager import app_data_dir

DB_PATH: str = str(app_data_dir() / "bot.db")


async def init_db() -> None:
    """Initialize the SQLite database and create necessary tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    logging.info("Database initialized successfully")


async def log_action(user_id: Optional[int], action: str, details: str = "") -> None:
    """Log an action to both console and SQLite database."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_message = f"[{timestamp}] User: {user_id or 'SYSTEM'} | {action}"
    if details:
        log_message += f" | {details}"
    logging.info(log_message)

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO logs (timestamp, user_id, action, details) VALUES (?, ?, ?, ?)",
                (timestamp, user_id, action, details)
            )
            await db.commit()
    except Exception as e:
        logging.error(f"Failed to write log to database: {e}")


async def get_recent_logs(limit: int = 10) -> list:
    """Retrieve recent logs from the database."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT timestamp, user_id, action, details FROM logs ORDER BY id DESC LIMIT ?",
                (limit,)
            ) as cursor:
                return await cursor.fetchall()
    except Exception as e:
        logging.error(f"Failed to fetch logs: {e}")
        return []