import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
from config import DATABASE_PATH, COOLDOWN_MINUTES

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Connected to database: {self.db_path}")
    
    async def close(self):
        if self.db:
            await self.db.close()
            logger.info("Database connection closed")
    
    async def _create_tables(self):
        if self.db is None:
            raise RuntimeError("Database connection not established")
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tracked_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                item_id INTEGER,
                max_price INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(discord_id),
                UNIQUE(user_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS item_cache (
                item_id INTEGER PRIMARY KEY,
                name TEXT,
                type TEXT,
                average_price INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notification_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                item_id INTEGER,
                listing_price INTEGER,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(discord_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tracked_items_user ON tracked_items(user_id);
            CREATE INDEX IF NOT EXISTS idx_tracked_items_item ON tracked_items(item_id);
            CREATE INDEX IF NOT EXISTS idx_notification_history_user_item
            ON notification_history(user_id, item_id);
            CREATE INDEX IF NOT EXISTS idx_notification_history_time
                ON notification_history(notified_at);

            CREATE TABLE IF NOT EXISTS api_keys (
                discord_id TEXT PRIMARY KEY,
                api_key TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        if self.db is not None:
            await self.db.commit()
            logger.debug("Database tables created/verified")
    
    async def add_user(self, discord_id: str) -> bool:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        await self.db.execute(
            "INSERT OR IGNORE INTO users (discord_id) VALUES (?)",
            (discord_id,)
        )
        await self.db.commit()
        return True
    
    async def set_api_key(self, discord_id: str, api_key: str) -> bool:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        await self.add_user(discord_id)
        await self.db.execute(
            """INSERT OR REPLACE INTO api_keys (discord_id, api_key, last_updated)
               VALUES (?, ?, ?)""",
            (discord_id, api_key, datetime.now())
        )
        await self.db.commit()
        logger.info(f"API key set for user {discord_id}")
        return True

    async def get_api_key(self, discord_id: str) -> Optional[str]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            "SELECT api_key FROM api_keys WHERE discord_id = ?",
            (discord_id,)
        )
        row = await cursor.fetchone()
        return row["api_key"] if row else None

    async def delete_api_key(self, discord_id: str) -> bool:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            "DELETE FROM api_keys WHERE discord_id = ?",
            (discord_id,)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_all_users(self) -> List[str]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute("SELECT discord_id FROM users")
        rows = await cursor.fetchall()
        return [row["discord_id"] for row in rows]

    async def add_tracked_item(self, user_id: str, item_id: int, max_price: int) -> bool:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        await self.add_user(user_id)

        await self.db.execute(
            """INSERT OR REPLACE INTO tracked_items (user_id, item_id, max_price)
               VALUES (?, ?, ?)""",
            (user_id, item_id, max_price)
        )
        await self.db.commit()
        logger.info(f"User {user_id} tracking item {item_id} below {max_price}")
        return True

    async def remove_tracked_item(self, user_id: str, item_id: int) -> bool:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            "DELETE FROM tracked_items WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_user_tracked_items(self, user_id: str) -> List[Tuple[int, int]]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            "SELECT item_id, max_price FROM tracked_items WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [(row["item_id"], row["max_price"]) for row in rows]

    async def get_users_tracking_item(self, item_id: int) -> List[Tuple[str, int]]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            "SELECT user_id, max_price FROM tracked_items WHERE item_id = ?",
            (item_id,)
        )
        rows = await cursor.fetchall()
        return [(row["user_id"], row["max_price"]) for row in rows]

    async def get_all_tracked_item_ids(self) -> List[int]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute("SELECT DISTINCT item_id FROM tracked_items")
        rows = await cursor.fetchall()
        return [row["item_id"] for row in rows]

    async def get_all_tracked_items_with_users(self) -> Dict[int, List[Tuple[str, int]]]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            "SELECT item_id, user_id, max_price FROM tracked_items ORDER BY item_id"
        )
        rows = await cursor.fetchall()

        result = {}
        for row in rows:
            item_id = row["item_id"]
            if item_id not in result:
                result[item_id] = []
            result[item_id].append((row["user_id"], row["max_price"]))

        return result

    async def cache_item_info(self, item_id: int, name: str, item_type: str, average_price: int):
        if self.db is None:
            raise RuntimeError("Database connection not established")
        await self.db.execute(
            """INSERT OR REPLACE INTO item_cache (item_id, name, type, average_price, last_updated)
               VALUES (?, ?, ?, ?, ?)""",
            (item_id, name, item_type, average_price, datetime.now())
        )
        await self.db.commit()

    async def get_cached_item_info(self, item_id: int) -> Optional[Dict]:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cursor = await self.db.execute(
            """SELECT name, type, average_price, last_updated FROM item_cache
               WHERE item_id = ?""",
            (item_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        last_updated = datetime.fromisoformat(row["last_updated"])
        if datetime.now() - last_updated > timedelta(hours=24):
            return None

        return {
            "name": row["name"],
            "type": row["type"],
            "average_price": row["average_price"]
        }

    async def get_item_name(self, item_id: int) -> str:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cached = await self.get_cached_item_info(item_id)
        if cached:
            return cached["name"]
        return f"Item #{item_id}"

    async def record_notification(self, user_id: str, item_id: int, listing_price: int):
        if self.db is None:
            raise RuntimeError("Database connection not established")
        await self.db.execute(
            """INSERT INTO notification_history (user_id, item_id, listing_price, notified_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, item_id, listing_price, datetime.now())
        )
        await self.db.commit()

    async def should_notify(self, user_id: str, item_id: int) -> bool:
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cooldown_cutoff = datetime.now() - timedelta(minutes=COOLDOWN_MINUTES)

        cursor = await self.db.execute(
            """SELECT notified_at FROM notification_history
               WHERE user_id = ? AND item_id = ?
               AND datetime(notified_at) > datetime(?)
               ORDER BY notified_at DESC LIMIT 1""",
            (user_id, item_id, cooldown_cutoff.isoformat())
        )
        row = await cursor.fetchone()

        return row is None

    async def cleanup_old_notifications(self, days: int = 7):
        if self.db is None:
            raise RuntimeError("Database connection not established")
        cutoff = datetime.now() - timedelta(days=days)
        await self.db.execute(
            "DELETE FROM notification_history WHERE notified_at < ?",
            (cutoff.isoformat(),)
        )
        await self.db.commit()
        logger.info(f"Cleaned up notification history older than {days} days")
