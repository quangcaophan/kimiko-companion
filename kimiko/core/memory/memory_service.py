import time
from typing import Optional, Any, List, Dict, Tuple
from kimiko.core.memory.db import MemoryDB
from kimiko.core.memory.vector_store import PersistentHybridStore


class MemoryService:
    def __init__(self, db:MemoryDB, store:PersistentHybridStore, window_size:int = 20, top_k: int = 5):
        self.db = db
        self.store = store
        self.window_size = window_size
        self.top_k = top_k
    
    def get_context(self, user_text:str):
        profile_summary = self.db.get_profile_summary()
        search_results = self.store.search(user_text, self.top_k)
        facts = [doc for doc, score in search_results]
        recent_turns = self.db.get_recent_turns(limit=self.window_size)

        return {
            "profile":profile_summary,
            "facts":facts,
            "recent_turns":recent_turns
        }
    
    def record_turn(self, role:str, content:str, session_id:int):
        self.db.insert_turn(role = role, content=content, ts=time.time())
        self._flush_aging_turns(session_id=session_id)

    def _flush_aging_turns(self, session_id: int):
        aging_turns = self.db.get_turns_to_embed(window_size= self.window_size)
        
        if not aging_turns:
            return
        
        for turn in aging_turns:
            format_text = f"{turn['role']}: {turn['content']}"
            self.store.add_fact(content = format_text, session_id = session_id, ts=turn['ts'])
        
        turn_ids = [turn['id'] for turn in aging_turns]
        self.db.mark_turns_embedded(turn_ids)
    
    def build_system_prompt(self, persona: str, context: Dict[str, Any]) -> str:
        if context.get("facts"):
            fact_lines = [f"- {f['content'] if isinstance(f, dict) else f}" for f in context["facts"]]
            fact_block = "\n".join(fact_lines)
        else:
            fact_block = "(chưa có ký ức nào liên quan)"

        profile_block = context.get("profile") or "(chưa có thông tin về người dùng)"

        if context.get("recent_turns"):
            recent_block = "\n".join(f"{t['role']}: {t['content']}" for t in context["recent_turns"])
        else:
            recent_block = "(chưa có)"

        return (
            f"{persona}\n\n"
            f"Thông tin về User:\n{profile_block}\n\n"
            f"[Ký ức liên quan — KHÔNG phải tin nhắn hiện tại]:\n{fact_block}\n\n"
            f"Hội thoại gần đây:\n{recent_block}"
        )

    def maybe_summarize(self, session_id: int) -> None:
        pass  # TODO: quyết định trigger — xem plan.md mục 7