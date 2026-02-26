"""Database connection and initialization."""
import os
import sqlite3
from englearn.config import DB_PATH, DATA_DIR, SCHEMA_PATH


def get_connection() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    with open(SCHEMA_PATH, 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    # Run migrations for existing DBs
    _migrate(conn)
    conn.close()


def _migrate(conn):
    """Add columns/tables that may be missing in older DBs."""
    # Add example_sentence and collocation to flashcards
    cols = {r[1] for r in conn.execute("PRAGMA table_info(flashcards)").fetchall()}
    if 'example_sentence' not in cols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN example_sentence TEXT")
    if 'collocation' not in cols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN collocation TEXT")

    # Add chat_messages table if missing
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if 'chat_messages' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            corrections TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages(role_id)")

    conn.commit()


def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
