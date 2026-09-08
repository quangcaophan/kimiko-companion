import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

# Prevent Windows CP1252 emoji crash in console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root (parent of 'kimiko') is in sys.path regardless of execution CWD
_current_file = Path(__file__).resolve()
_project_root = _current_file.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


from dotenv import load_dotenv
import uvicorn

from kimiko.core.memory.db import MemoryDB
from kimiko.core.memory.embedder import LMStudioEmbedder
from kimiko.core.memory.vector_store import PersistentHybridStore
from kimiko.core.memory.memory_service import MemoryService
from kimiko.core.gemini.adapter import GeminiAdapter
from kimiko.core.gemini.tools import ACTION_TOOLS
from kimiko.core.audio.tts import SovitsTTS
from kimiko.core.audio.asr import GroqASR
from kimiko.core.avatar import actions
from kimiko.core.avatar.playback_worker import PlaybackWorker
from kimiko.core.server.app import app, ws_manager
from kimiko.turn_engine import run_turn

load_dotenv()


class KimikoCompanion:
    """Kimiko 3D VTuber AI Companion & Butler Runtime Orchestrator."""

    def __init__(self) -> None:
        print("\n" + "=" * 65)
        print("  INITIALIZING KIMIKO AI COMPANION SYSTEM")
        print("=" * 65)

        # 1. Database & Memory
        print("--> [1/6] Initializing Memory Database...")
        db_file = _project_root / "kimiko" / "core" / "memory" / "memory.db"
        self.db = MemoryDB(str(db_file))
        self.session_id = self.db.get_or_create_session()

        # 2. Embedding & Vector Store
        print("--> [2/6] Connecting to LM Studio Embedder & Hybrid Store...")
        self.embedder = LMStudioEmbedder(
            base_url=os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1"),
            model="text-embedding-bge-m3"
        )
        self.store = PersistentHybridStore(db=self.db, embedder=self.embedder)
        self.memory_service = MemoryService(db=self.db, store=self.store, window_size=20, top_k=5)

        # 3. Gemini LLM Adapter
        print("--> [3/6] Initializing Gemini Interactions Adapter...")
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("[Warning] GEMINI_API_KEY not found in environment!")
        self.gemini = GeminiAdapter(model="gemini-2.5-flash", api_key=gemini_key)

        # 4. Audio Services (ASR & TTS)
        print("--> [4/6] Initializing Audio Pipeline (Groq ASR & GPT-SoVITS TTS)...")
        self.asr = GroqASR(
            api_key=os.getenv("GROQ_API_KEY"),
            context_prompt="Conversation between Kimiko and developer Quang."
        )

        ref_wav = (_project_root / "kimiko" / "assets" / "character_files" / "main_sample.wav").resolve()
        sovits_url = os.getenv("SOVITS_URL", "http://127.0.0.1:9880")
        self.tts = SovitsTTS(
            base_url=sovits_url,
            ref_audio_path=str(ref_wav),
            prompt_text="",
            prompt_lang="en",
            text_lang="en",
            speed_factor=1.2
        )

        from kimiko.core.audio.tts import _start_sovits
        _start_sovits(base_url=sovits_url)


        # 5. Playback Worker
        print("--> [5/6] Initializing Avatar Playback Queue Worker...")
        self.worker = PlaybackWorker(broadcast_fn=ws_manager.broadcast_sync, pad_seconds=0.2)
        self.worker.start()

        # 6. Audio Cache Directory
        self.audio_cache_dir = _project_root / "kimiko" / "assets" / "client" / "audio" / "temp"
        self.audio_cache_dir.mkdir(parents=True, exist_ok=True)
        self.speech_counter = 0


        self.persona = (
            "You are Kimiko, a cute, playful, intelligent anime VTuber AI companion.\n"
            "You live inside a 3D VRM space and interact with your master, Quang.\n"
            "Keep responses concise (1-3 sentences).\n"
            "You can execute actions like wave, walk, backflip, kiss, flyingkick using the provided tools.\n"
            "Always follow the bilingual format: English speech followed by Vietnamese subtitles:\n"
            "[EN] <English speech>\n"
            "[VI] <Vietnamese subtitle translation>"
        )

        print("=" * 65)
        print("  ALL SUBSYSTEMS READY!")
        print("=" * 65 + "\n")

    def _on_sentence_callback(self, speech_en: str, sub_vi: str) -> None:
        """Called by turn engine as each bilingual sentence completes."""
        print(f"\n[Kimiko Voice EN]: {speech_en}")
        print(f"[Subtitle VI]:     {sub_vi}")

        self.speech_counter += 1
        wav_file_name = f"speech_{int(time.time())}_{self.speech_counter}.wav"
        wav_full_path = str(self.audio_cache_dir / wav_file_name)
        # Web client path relative to client root
        wav_web_path = f"audio/temp/{wav_file_name}"

        # Synthesize via GPT-SoVITS
        saved_path, duration = self.tts.synthesize(text=speech_en, output_wav_path=wav_full_path)

        if saved_path and duration > 0:
            self.worker.enqueue_audio(
                audio_path=wav_web_path,
                text=sub_vi,
                duration=duration,
                expression="relaxed"
            )
        else:
            # Fallback: display subtitle directly even if TTS server is offline
            print("[Audio] Fallback: broadcasting subtitles without voice audio.")
            ws_manager.broadcast_sync({
                "type": "start_animation",
                "audio_path": "",
                "audio_text": sub_vi,
                "audio_duraction": max(2.0, len(speech_en) * 0.08),
                "expression": "relaxed"
            })

    def _on_action_callback(self, action_name: str, args: dict) -> dict:
        """Called by turn engine when LLM triggers a tool action."""
        print(f"\n[Action Triggered]: {action_name} | Args: {args}")
        resolved_action = args.get("action", action_name)
        payload = actions.execute(resolved_action)

        duration = 3.0 if resolved_action in {"backflip", "flyingkick"} else 2.0
        self.worker.enqueue_action(action_payload=payload, duration=duration)
        return {"status": "success", "executed_action": resolved_action}

    def chat_turn(self, user_text: str) -> str:
        """Process one conversational turn."""
        if not user_text or not user_text.strip():
            return ""

        # Check for any pending click interactions to incorporate
        pending = self.db.pop_pending_actions()
        if pending:
            regions = [p["region"] for p in pending]
            user_text += f" (Note: User just touched your {', '.join(regions)})"

        # Signal thinking state to 3D avatar
        ws_manager.broadcast_sync({"type": "set_state", "state": "thinking"})

        response = run_turn(
            user_text=user_text,
            session_id=self.session_id,
            persona=self.persona,
            memory=self.memory_service,
            gemini=self.gemini,
            tools=ACTION_TOOLS,
            on_sentence=self._on_sentence_callback,
            on_action=self._on_action_callback
        )
        return response

    def voice_turn(self) -> None:
        """Record from microphone with VAD and process transcribed speech."""
        record_wav = str(self.audio_cache_dir / "user_input.wav")
        ws_manager.broadcast_sync({"type": "set_state", "state": "listening"})

        success = self.asr.record(output_file=record_wav, silence_duration=1.2)
        if not success:
            print("[Voice] No speech captured.")
            ws_manager.broadcast_sync({"type": "set_state", "state": "idle"})
            return

        text = self.asr.transcribe(record_wav)
        if not text:
            print("[Voice] Transcription returned empty text.")
            ws_manager.broadcast_sync({"type": "set_state", "state": "idle"})
            return

        print(f"\n[You (Voice)]: {text}")
        self.chat_turn(text)

    def shutdown(self) -> None:
        """Gracefully release all resources."""
        print("\nShutting down Kimiko Companion...")
        try:
            self.worker.interrupt()
            self.worker.stop()
        except Exception as e:
            print(f"Worker shutdown warning: {e}")

        try:
            self.db.close_session(self.session_id)
        except Exception as e:
            print(f"Database session close warning: {e}")

        print("Goodbye! See you next time.")


def start_server_thread():
    """Run the FastAPI application in a background daemon thread."""
    config = uvicorn.Config(app, host="0.0.0.0", port=8001, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def main():
    # 1. Start Web & WebSocket Server
    server, srv_thread = start_server_thread()
    time.sleep(1.0)  # Brief wait for uvicorn port binding

    # 2. Start Kimiko Orchestrator
    try:
        kimiko = KimikoCompanion()
    except Exception as e:
        print(f"\n[FATAL] Failed to initialize Kimiko Companion: {e}")
        return

    print("=" * 65)
    print("  KIMIKO INTERACTIVE CONSOLE")
    print("  - Type your message and press Enter to chat.")
    print("  - Type '/voice' or '/v' to speak via microphone.")
    print("  - Type 'exit' or press Ctrl+C to quit.")
    print("  - Open 3D Avatar in browser: http://localhost:8001")
    print("=" * 65 + "\n")

    try:
        while True:
            try:
                user_input = input("\nYou > ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "/quit", "/exit"}:
                break

            if user_input.lower() in {"/v", "/voice", "/mic"}:
                kimiko.voice_turn()
            else:
                kimiko.chat_turn(user_input)

    except KeyboardInterrupt:
        print("\n[Ctrl+C detected]")
    finally:
        kimiko.shutdown()


if __name__ == "__main__":
    main()
