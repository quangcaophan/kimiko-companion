import time
from typing import Optional, Any, List, Dict, Tuple
from kimiko.core.logger import get_logger
from kimiko.core.memory.db import MemoryDB
from kimiko.core.memory.vector_store import PersistentHybridStore

logger = get_logger("memory.service")


class MemoryService:
    """High-level memory orchestrator combining SQLite turns/profiles and hybrid vector search."""

    def __init__(
        self,
        db: MemoryDB,
        store: PersistentHybridStore,
        window_size: int = 20,
        top_k: int = 5
    ) -> None:
        self.db = db
        self.store = store
        self.window_size = window_size
        self.top_k = top_k
        logger.debug(f"Initialized MemoryService: window_size={window_size}, top_k={top_k}")
    
    def get_context(self, user_text: str) -> Dict[str, Any]:
        """Retrieve relevant context for a user query: profile, semantic facts, and recent conversation turns."""
        logger.debug(f"Fetching context for query: {user_text!r}")
        profile_summary = self.db.get_profile_summary()
        search_results = self.store.search(user_text, self.top_k)
        facts = [doc for doc, score in search_results]
        recent_turns = self.db.get_recent_turns(limit=self.window_size)

        logger.debug(
            f"Context built: profile_present={bool(profile_summary)}, "
            f"facts_found={len(facts)}, recent_turns={len(recent_turns)}"
        )

        return {
            "profile": profile_summary,
            "facts": facts,
            "recent_turns": recent_turns
        }
    
    def record_turn(self, role: str, content: str, session_id: int) -> None:
        """Record a conversation turn and flush aging turns outside the active window to vector memory."""
        logger.debug(f"Inserting turn ({role}, session={session_id}): {content[:60]!r}...")
        self.db.insert_turn(role=role, content=content, ts=time.time())
        self._flush_aging_turns(session_id=session_id)

    def _flush_aging_turns(self, session_id: int) -> None:
        """Check for turns that have aged out of the active window and embed them into persistent hybrid store."""
        aging_turns = self.db.get_turns_to_embed(window_size=self.window_size)
        
        if not aging_turns:
            return
        
        logger.info(f"Flushing {len(aging_turns)} aged turn(s) out of sliding window to vector memory...")
        for turn in aging_turns:
            format_text = f"{turn['role']}: {turn['content']}"
            self.store.add_fact(content=format_text, session_id=session_id, ts=turn['ts'])
        
        turn_ids = [turn['id'] for turn in aging_turns]
        self.db.mark_turns_embedded(turn_ids)
        logger.info(f"Successfully embedded and marked turn IDs: {turn_ids}")
    
    def build_system_prompt(self, persona: str, context: Dict[str, Any]) -> str:
        """Compose the full system instruction prompt with profile, retrieved facts, recent turns, and subtitle instructions."""
        if context.get("facts"):
            fact_lines = [f"- {f['content'] if isinstance(f, dict) else f}" for f in context["facts"]]
            fact_block = "\n".join(fact_lines)
        else:
            fact_block = "(no relevant memories yet)"

        profile_block = context.get("profile") or "(no user profile info yet)"

        if context.get("recent_turns"):
            recent_block = "\n".join(f"{t['role']}: {t['content']}" for t in context["recent_turns"])
        else:
            recent_block = "(none)"

        return (
            f"{persona}\n\n"
            f"User Profile:\n{profile_block}\n\n"
            f"[Relevant Memories — NOT current messages]:\n{fact_block}\n\n"
            f"Recent Conversation:\n{recent_block}\n\n"
            f"Subtitle Instruction:\n"
            f"You speak English. For your response, format your speech with Vietnamese subtitles using this exact structure:\n"
            f"[EN] <Spoken English response>\n"
            f"[VI] <Vietnamese subtitle translation>"
        )

    def maybe_summarize(self, session_id: int) -> None:
        pass