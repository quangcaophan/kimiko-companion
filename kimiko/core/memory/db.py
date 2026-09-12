import sqlite3
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from kimiko.core.logger import get_logger

logger = get_logger("memory.db")


class MemoryDB:
    """SQLite-based persistent database for conversations, facts, sessions, and click actions."""

    def __init__(self, db_path: str = 'kimiko/core/memory/memory.db') -> None:
        if not os.path.isabs(db_path):
            if not os.path.exists(db_path):
                alt = Path(__file__).resolve().parent / os.path.basename(db_path)
                if alt.parent.exists():
                    db_path = str(alt)
        self.db_path = db_path

        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create database directory {db_dir}: {e}")


        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Return a SQLite connection configured with WAL mode and a 10-second busy timeout."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    @contextmanager
    def _conn(self):
        """Context manager guaranteeing transaction commit, rollback on error, and connection closing."""
        conn = self.get_connection()
        try:
            with conn:
                yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database tables idempotently."""
        with self._conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""CREATE TABLE IF NOT EXISTS turns(
                id INTEGER PRIMARY KEY,
                ts REAL,
                role TEXT,
                content TEXT,
                embedded INTEGER DEFAULT 0);
            """)
            cursor.execute("""CREATE TABLE IF NOT EXISTS profile(
                id INTEGER PRIMARY KEY,
                summary TEXT,
                updated_at REAL);
            """)
            cursor.execute("""CREATE TABLE IF NOT EXISTS pending_actions(
                id INTEGER PRIMARY KEY,
                region TEXT,
                bone TEXT,
                ts REAL,
                consumed INTEGER DEFAULT 0);
            """)
            cursor.execute("""CREATE TABLE IF NOT EXISTS memory_facts(
                id INTEGER PRIMARY KEY,
                content TEXT,
                ts REAL,
                session_id INTEGER,
                vector_json TEXT);
            """)
            cursor.execute("""CREATE TABLE IF NOT EXISTS sessions(
                id INTEGER PRIMARY KEY,
                started_at REAL,
                ended_at REAL);
            """)

    #--------------------
    # --- turns table ---
    #--------------------
    def insert_turn(self, role: str, content: str, ts: float) -> int:
        """Insert a new conversation turn and return created id."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO turns (ts, role, content) VALUES (?, ?, ?)",
                (ts, role, content)
            )
            return cursor.lastrowid

    def get_recent_turns(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch the most recent turns, returned in chronological order (oldest to newest)."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, ts, role, content, embedded FROM turns ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            
            result = [dict(row) for row in rows]
            result.reverse()  # Reverse so conversation flows chronologically
            return result

    def get_turns_to_embed(self, window_size: int) -> List[Dict[str, Any]]:
        """Retrieve turns outside the recent active window that have not yet been embedded."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM turns ORDER BY id DESC LIMIT 1 OFFSET ?", (window_size - 1,)
            )
            boundary_row = cursor.fetchone()
            if boundary_row is None:
                return []   # Not enough turns to fall outside the window
            boundary_id = boundary_row["id"]

            cursor.execute(
                "SELECT id, ts, role, content FROM turns WHERE embedded = 0 AND id < ? ORDER BY id ASC",
                (boundary_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def mark_turns_embedded(self, turn_ids: List[int]) -> None:
        """Mark specific turns as embedded in vector store."""
        if not turn_ids:
            return
        with self._conn() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(turn_ids))
            cursor.execute(f"UPDATE turns SET embedded = 1 WHERE id IN ({placeholders})", turn_ids)

    #---------------------------
    # --- memory_facts table ---
    #---------------------------
    def insert_memory_fact(self, content: str, ts: float, session_id: int, vector_json: str) -> int:
        """Store a memory fact with JSON vector representation, returning its id."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO memory_facts (content, ts, session_id, vector_json) VALUES (?, ?, ?, ?)",
                (content, ts, session_id, vector_json)
            )
            return cursor.lastrowid

    def get_all_memory_facts(self) -> List[sqlite3.Row]:
        """Retrieve all memory facts as sqlite3.Row objects ordered by timestamp."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_facts ORDER BY ts ASC")
            return cursor.fetchall()

    #-----------------------
    # --- sessions table ---
    #-----------------------
    def get_or_create_session(self) -> int:
        """Find an unended session (ended_at IS NULL) or create a new one, returning its id."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                return row['id']
            
            current_ts = time.time()
            cursor.execute("INSERT INTO sessions (started_at, ended_at) VALUES (?, NULL)", (current_ts,))
            return cursor.lastrowid

    def close_session(self, session_id: int) -> None:
        """Update ended_at timestamp for a session."""
        with self._conn() as conn:
            cursor = conn.cursor()
            current_ts = time.time()
            cursor.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (current_ts, session_id)
            )

    #----------------------
    # --- profile table ---
    #----------------------
    def get_profile_summary(self) -> str:
        """Retrieve the latest profile summary, or empty string if none exists."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT summary FROM profile ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row['summary'] if row else ""

    def set_profile_summary(self, summary: str) -> None:
        """Append a new profile summary entry."""
        with self._conn() as conn:
            cursor = conn.cursor()
            current_ts = time.time()

            cursor.execute(
                "INSERT INTO profile (summary, updated_at) VALUES (?, ?)",
                (summary, current_ts)
            )

    #------------------------------
    # --- pending_actions table --- 
    #------------------------------
    def insert_pending_action(self, region: str, bone: str, ts: float) -> None:
        """Insert a pending click action."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pending_actions (region, bone, ts, consumed) VALUES (?, ?, ?, 0)",
                (region, bone, ts)
            )

    def pop_pending_actions(self) -> List[Dict[str, Any]]:
        """Atomically fetch unconsumed actions (consumed=0) and mark them as consumed (=1)."""
        with self._conn() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, region, bone, ts FROM pending_actions WHERE consumed = 0")
            rows = cursor.fetchall()
            
            if not rows:
                return []
            
            actions = [dict(row) for row in rows]
            
            ids = [action['id'] for action in actions]
            placeholders = ",".join(["?"] * len(ids)) 
            
            cursor.execute(
                f"UPDATE pending_actions SET consumed = 1 WHERE id IN ({placeholders})",
                ids
            )
            
            return actions


    
    