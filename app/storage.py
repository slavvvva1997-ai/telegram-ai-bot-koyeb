import json
import os
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - only used when PostgreSQL dependency is absent
    psycopg = None
    dict_row = None


MAX_CONTEXT_MESSAGES = 5


@dataclass
class ChatMemory:
    summary: str
    messages: list[dict[str, str]]


class RateLimiter:
    def __init__(self, max_requests: int = 5, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = monotonic()
        hits = self._hits[user_id]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True


class Storage:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.mode = "postgresql" if database_url.startswith("postgres") else "sqlite"
        self._conn: sqlite3.Connection | None = None
        self._pg_conn: Any | None = None

    def connect(self) -> None:
        if self.mode == "postgresql":
            if psycopg is None:
                raise RuntimeError("Для PostgreSQL установите зависимость psycopg[binary].")
            self._pg_conn = psycopg.connect(self.database_url, row_factory=dict_row)
            self._init_schema()
            return
        parsed = urlparse(self.database_url)
        db_path = parsed.path.lstrip("/") if parsed.scheme == "sqlite" else "bot.db"
        if db_path in ("", ":memory:"):
            db_path = ":memory:"
        elif os.getenv("VERCEL") and not Path(db_path).is_absolute():
            db_path = str(Path("/tmp") / Path(db_path).name)
        else:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        if self._pg_conn:
            self._pg_conn.close()
            self._pg_conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    @property
    def pg_conn(self) -> Any:
        if self._pg_conn is None:
            self.connect()
        return self._pg_conn

    def _init_schema(self) -> None:
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chats (
                        chat_id BIGINT PRIMARY KEY,
                        short_summary TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id_id ON messages(chat_id, id)")
            self.pg_conn.commit()
            return
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                short_summary TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat_id_id ON messages(chat_id, id);
            """
        )
        self.conn.commit()

    def save_user(self, user_id: int, username: str | None) -> None:
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users(user_id, username, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, updated_at=excluded.updated_at
                    """,
                    (user_id, username, self._now()),
                )
            self.pg_conn.commit()
            return
        self.conn.execute(
            """
            INSERT INTO users(user_id, username, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, updated_at=excluded.updated_at
            """,
            (user_id, username, self._now()),
        )
        self.conn.commit()

    def ensure_chat(self, chat_id: int) -> None:
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chats(chat_id, short_summary, updated_at)
                    VALUES (%s, '', %s)
                    ON CONFLICT(chat_id) DO NOTHING
                    """,
                    (chat_id, self._now()),
                )
            self.pg_conn.commit()
            return
        self.conn.execute(
            """
            INSERT INTO chats(chat_id, short_summary, updated_at)
            VALUES (?, '', ?)
            ON CONFLICT(chat_id) DO NOTHING
            """,
            (chat_id, self._now()),
        )
        self.conn.commit()

    def add_message(self, chat_id: int, user_id: int, role: str, content: str) -> None:
        self.ensure_chat(chat_id)
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages(chat_id, user_id, role, content, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (chat_id, user_id, role, content[:4000], self._now()),
                )
            self.pg_conn.commit()
            self._trim_messages(chat_id)
            return
        self.conn.execute(
            "INSERT INTO messages(chat_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, role, content[:4000], self._now()),
        )
        self.conn.commit()
        self._trim_messages(chat_id)

    def get_memory(self, chat_id: int) -> ChatMemory:
        self.ensure_chat(chat_id)
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT short_summary FROM chats WHERE chat_id = %s", (chat_id,))
                chat = cur.fetchone()
                cur.execute(
                    "SELECT role, content FROM messages WHERE chat_id = %s ORDER BY id DESC LIMIT %s",
                    (chat_id, MAX_CONTEXT_MESSAGES),
                )
                rows = cur.fetchall()
            messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
            return ChatMemory(summary=chat["short_summary"] if chat else "", messages=messages)
        chat = self.conn.execute("SELECT short_summary FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, MAX_CONTEXT_MESSAGES),
        ).fetchall()
        messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return ChatMemory(summary=chat["short_summary"] if chat else "", messages=messages)

    def update_summary(self, chat_id: int, summary: str) -> None:
        self.ensure_chat(chat_id)
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "UPDATE chats SET short_summary = %s, updated_at = %s WHERE chat_id = %s",
                    (summary[:2000], self._now(), chat_id),
                )
            self.pg_conn.commit()
            return
        self.conn.execute(
            "UPDATE chats SET short_summary = ?, updated_at = ? WHERE chat_id = ?",
            (summary[:2000], self._now(), chat_id),
        )
        self.conn.commit()

    def stats(self) -> dict[str, Any]:
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS count FROM messages")
                message_count = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) AS count FROM users")
                user_count = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) AS count FROM chats")
                chat_count = cur.fetchone()["count"]
            return {"messages": message_count, "users": user_count, "chats": chat_count, "mode": self.mode}
        message_count = self.conn.execute("SELECT COUNT(*) AS count FROM messages").fetchone()["count"]
        user_count = self.conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        chat_count = self.conn.execute("SELECT COUNT(*) AS count FROM chats").fetchone()["count"]
        return {"messages": message_count, "users": user_count, "chats": chat_count, "mode": self.mode}

    def _trim_messages(self, chat_id: int) -> None:
        if self.mode == "postgresql":
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM messages
                    WHERE chat_id = %s
                      AND id NOT IN (
                        SELECT id FROM messages WHERE chat_id = %s ORDER BY id DESC LIMIT %s
                      )
                    """,
                    (chat_id, chat_id, MAX_CONTEXT_MESSAGES),
                )
            self.pg_conn.commit()
            return
        self.conn.execute(
            """
            DELETE FROM messages
            WHERE chat_id = ?
              AND id NOT IN (
                SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?
              )
            """,
            (chat_id, chat_id, MAX_CONTEXT_MESSAGES),
        )
        self.conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


def compact_summary(previous_summary: str, user_text: str, assistant_text: str) -> str:
    payload = {
        "previous": previous_summary[-700:],
        "latest_user": user_text[:500],
        "latest_assistant": assistant_text[:500],
    }
    text = json.dumps(payload, ensure_ascii=False)
    return text[:1800]
