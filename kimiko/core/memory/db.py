import sqlite3
import os
import time

class MemoryDB:
    def __init__(self, db_path: str = 'kimiko/core/memory/memory.db'):
        self.db_path = db_path

        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Thêm IF NOT EXISTS vào tất cả các câu lệnh CREATE TABLE
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
        """Chèn một lượt hội thoại mới và trả về id vừa tạo"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO turns (ts, role, content) VALUES (?, ?, ?)",
                (ts, role, content)
            )
            # Trả về id của bản ghi vừa chèn
            return cursor.lastrowid

    def get_recent_turns(self, limit: int) -> list[dict]:
        """Lấy các lượt hội thoại gần nhất, trả về danh sách dict"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Sắp xếp giảm dần theo id hoặc ts để lấy mới nhất, nhưng đảo ngược lại để đúng thứ tự thời gian
            cursor.execute(
                "SELECT id, ts, role, content, embedded FROM turns ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            
            # Chuyển đổi các sqlite3.Row thành dict để dễ xử lý ở tầng trên
            result = [dict(row) for row in rows]
            result.reverse() # Đảo lại để hội thoại đi từ cũ đến mới
            return result

    def get_turns_to_embed(self, window_size: int) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Tìm id của turn đứng ở vị trí thứ window_size tính từ mới nhất
            cursor.execute(
                "SELECT id FROM turns ORDER BY id DESC LIMIT 1 OFFSET ?", (window_size - 1,)
            )
            boundary_row = cursor.fetchone()
            if boundary_row is None:
                return []   # chưa đủ turns để có gì "già" ra khỏi cửa sổ
            boundary_id = boundary_row["id"]

            cursor.execute(
                "SELECT id, ts, role, content FROM turns WHERE embedded = 0 AND id < ? ORDER BY id ASC",
                (boundary_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def mark_turns_embedded(self, turn_ids: list[int]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(turn_ids))
            cursor.execute(f"UPDATE turns SET embedded = 1 WHERE id IN ({placeholders})", turn_ids)


    #---------------------------
    # --- memory_facts table ---
    #---------------------------
    def insert_memory_fact(self, content: str, ts: float, session_id: int, vector_json: str) -> int:
        """Lưu một sự kiện bộ nhớ kèm vector định dạng JSON, trả về id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO memory_facts (content, ts, session_id, vector_json) VALUES (?, ?, ?, ?)",
                (content, ts, session_id, vector_json)
            )
            return cursor.lastrowid

    def get_all_memory_facts(self) -> list[sqlite3.Row]:
        """Lấy toàn bộ sự kiện bộ nhớ, trả về danh sách sqlite3.Row nguyên bản"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_facts ORDER BY ts ASC")
            # row_factory = sqlite3.Row đã cấu hình ở get_connection nên fetchall sẽ trả về list[sqlite3.Row]
            return cursor.fetchall()

    #-----------------------
    # --- sessions table ---
    #-----------------------
    def get_or_create_session(self) -> int:
        """Tìm session chưa kết thúc (ended_at IS NULL), nếu không có thì tạo mới và trả về id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 1. Tìm session hiện tại chưa đóng
            cursor.execute("SELECT id FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                return row['id']
            
            # 2. Nếu không có, tiến hành tạo mới
            current_ts = time.time()
            cursor.execute("INSERT INTO sessions (started_at, ended_at) VALUES (?, NULL)", (current_ts,))
            return cursor.lastrowid

    def close_session(self, session_id: int):
        """Cập nhật thời gian kết thúc cho một session"""
        with self.get_connection() as conn:
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
        """Lấy thông tin tóm tắt profile mới nhất, nếu trống trả về chuỗi rỗng"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT summary FROM profile ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row['summary'] if row else ""

    def set_profile_summary(self, summary: str):
        """Cập nhật hoặc thêm mới tóm tắt profile"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_ts = time.time()

            cursor.execute(
                "INSERT INTO profile (summary, updated_at) VALUES (?, ?)",
                (summary, current_ts)
            )


    #------------------------------
    # --- pending_actions table --- 
    #------------------------------
    def insert_pending_action(self, region: str, bone: str, ts: float):
        """Chèn một hành động đang chờ xử lý"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pending_actions (region, bone, ts, consumed) VALUES (?, ?, ?, 0)",
                (region, bone, ts)
            )

    def pop_pending_actions(self) -> list[dict]:
        """Lấy các hành động chưa xử lý (consumed=0), đánh dấu chúng thành đã xử lý (=1) rồi trả về dữ liệu"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. SELECT các hành động chưa tiêu thụ
            cursor.execute("SELECT id, region, bone, ts FROM pending_actions WHERE consumed = 0")
            rows = cursor.fetchall()
            
            if not rows:
                return []
            
            # Chuyển đổi dữ liệu sang dict trước khi update để tránh mất dấu dữ liệu
            actions = [dict(row) for row in rows]
            
            # 2. Gom các ID lại để UPDATE một lượt (Tối ưu hóa performance)
            ids = [action['id'] for action in actions]
            # Tạo chuỗi ?,?,? tương ứng với số lượng ID
            placeholders = ",".join(["?"] * len(ids)) 
            
            cursor.execute(
                f"UPDATE pending_actions SET consumed = 1 WHERE id IN ({placeholders})",
                ids
            )
            
            return actions

    
    