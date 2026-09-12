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

# Ensure project root (parent of 'kimiko') is in sys.path when invoked directly as a script
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv
import uvicorn

from kimiko.core.logger import configure_logging, get_logger

# Configure central logging system (console + file logging)
configure_logging()
logger = get_logger("orchestrator")

from kimiko.config import load_config, KimikoConfig
from kimiko.core.memory.db import MemoryDB
from kimiko.core.memory.embedder import LMStudioEmbedder
from kimiko.core.memory.vector_store import PersistentHybridStore
from kimiko.core.memory.memory_service import MemoryService
from kimiko.core.memory.lifecycle import start_llm
from kimiko.core.gemini.adapter import GeminiAdapter
from kimiko.core.gemini.tools import ACTION_TOOLS
from kimiko.core.audio.tts import SovitsTTS, _start_sovits
from kimiko.core.audio.asr import GroqASR
from kimiko.core.avatar import actions
from kimiko.core.avatar.playback_worker import PlaybackWorker
from kimiko.core.server.app import app, ws_manager, set_db, register_chat_handler, register_voice_handler
from kimiko.turn_engine import run_turn

load_dotenv()


class KimikoCompanion:
    """Kimiko 3D VTuber AI Companion & Butler Runtime Orchestrator."""

    def __init__(self, config: Optional[KimikoConfig] = None) -> None:
        self.config = config or load_config()

        logger.info("=" * 65)
        logger.info("  INITIALIZING KIMIKO AI COMPANION SYSTEM")
        logger.info("=" * 65)

        # 1. Database & Memory
        logger.info("--> [1/7] Initializing Memory Database...")
        db_file = _project_root / "kimiko" / "core" / "memory" / "memory.db"
        self.db = MemoryDB(str(db_file))
        self.session_id = self.db.get_or_create_session()
        set_db(self.db)  # Inject shared DB instance into FastAPI server module
        logger.debug(f"MemoryDB attached at: {db_file} (Active Session #{self.session_id})")

        # 2. LM Studio Embedding Server
        logger.info("--> [2/7] Ensuring LM Studio embedding server is running...")
        start_llm(base_url=self.config.embedding_url)

        # 3. Embedding & Vector Store
        logger.info("--> [3/7] Connecting to LM Studio Embedder & Hybrid Store...")
        self.embedder = LMStudioEmbedder(
            base_url=self.config.embedding_url,
            model=self.config.embedding_model
        )
        self.store = PersistentHybridStore(db=self.db, embedder=self.embedder)
        self.memory_service = MemoryService(
            db=self.db,
            store=self.store,
            window_size=self.config.memory_window_size,
            top_k=self.config.memory_top_k
        )

        # 4. Gemini LLM Adapter
        logger.info("--> [4/7] Initializing Gemini Interactions Adapter...")
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            logger.warning("GEMINI_API_KEY not found in environment!")
        self.gemini = GeminiAdapter(model=self.config.gemini_model, api_key=gemini_key)

        # 5. Audio Services (ASR & TTS)
        logger.info("--> [5/7] Initializing Audio Pipeline (Groq ASR & GPT-SoVITS TTS)...")
        self.asr = GroqASR(
            api_key=os.getenv("GROQ_API_KEY"),
            context_prompt="Conversation between Kimiko and developer Quang."
        )

        ref_wav = (_project_root / "kimiko" / "assets" / self.config.sovits_ref_audio_path).resolve()
        sovits_url = self.config.sovits_url
        self.tts = SovitsTTS(
            base_url=sovits_url,
            ref_audio_path=str(ref_wav),
            prompt_text="",
            prompt_lang="en",
            text_lang="en",
            speed_factor=self.config.sovits_speed_factor
        )

        # Check or launch GPT-SoVITS server
        _start_sovits(base_url=sovits_url)

        # 6. Playback Worker
        logger.info("--> [6/7] Initializing Avatar Playback Queue Worker...")
        self.worker = PlaybackWorker(broadcast_fn=ws_manager.broadcast_sync, pad_seconds=0.2)
        self.worker.start()

        # 7. Audio Cache Directory
        logger.info("--> [7/7] Verifying Audio Cache Storage...")
        self.audio_cache_dir = _project_root / "kimiko" / "assets" / "client" / "audio" / "temp"
        self.audio_cache_dir.mkdir(parents=True, exist_ok=True)
        self.speech_counter = 0

        self.persona = self.config.persona

        # Register Web UI event handlers with FastAPI server
        register_chat_handler(self.chat_turn)
        register_voice_handler(self.handle_web_audio)

        logger.info("=" * 65)
        logger.info("  ALL KIMIKO SUBSYSTEMS READY!")
        logger.info("=" * 65)

    def _play_local_audio(self, wav_path: str) -> None:
        """Play synthesized audio directly through system speakers/headphones in background."""
        def _play():
            try:
                import soundfile as sf
                import sounddevice as sd
                data, fs = sf.read(wav_path, dtype='float32')
                sd.play(data, fs)
                sd.wait()
            except Exception as e:
                logger.debug(f"Local audio playback skipped: {e}")
        threading.Thread(target=_play, daemon=True).start()

    def test_voice(self) -> None:
        """Quick sanity check for TTS generation and playback."""
        logger.info("Running TTS voice test...")
        self._on_sentence_callback(
            speech_en="Hello! I am Kimiko. I am ready to talk with you!",
            sub_vi="Xin chào! Mình là Kimiko. Mình đã sẵn sàng trò chuyện cùng bạn rồi nè!"
        )

    def _on_sentence_callback(self, speech_en: str, sub_vi: str) -> None:
        """Called by turn engine as each bilingual sentence completes."""
        logger.info(f"[Kimiko Spoken EN]: {speech_en}")
        logger.info(f"[Subtitle VI]:     {sub_vi}")

        self.speech_counter += 1
        wav_file_name = f"speech_{int(time.time())}_{self.speech_counter}.wav"
        wav_full_path = str(self.audio_cache_dir / wav_file_name)
        # Web client path relative to client root
        wav_web_path = f"audio/temp/{wav_file_name}"

        # Synthesize via GPT-SoVITS
        saved_path, duration = self.tts.synthesize(text=speech_en, output_wav_path=wav_full_path)

        if saved_path and duration > 0:
            logger.info(f"Enqueuing speech audio to worker: {wav_web_path} (duration: {duration:.2f}s)")
            self.worker.enqueue_audio(
                audio_path=wav_web_path,
                text=sub_vi,
                duration=duration,
                expression="relaxed"
            )
            # Prevent duplicate voice playback:
            # When a browser client is connected, the browser plays audio with synchronized 3D lip-sync.
            # Only play locally via sounddevice when no browser is connected (e.g. terminal CLI mode).
            local_mode = os.getenv("LOCAL_AUDIO_PLAYBACK", "auto").lower()
            should_play_local = (
                local_mode == "always"
                or (local_mode == "auto" and not ws_manager.has_active_clients)
            )
            if should_play_local:
                logger.info(f"Playing locally via system speakers (no active browser): {wav_full_path}")
                self._play_local_audio(wav_full_path)
            else:
                logger.debug("Active browser client detected — delegating audio playback to web client.")
        else:
            # Fallback: display subtitle directly even if TTS server is offline
            fallback_dur = max(2.0, len(speech_en) * 0.08)
            logger.warning(f"TTS offline fallback: broadcasting subtitle directly (dur={fallback_dur:.2f}s)")
            ws_manager.broadcast_sync({
                "type": "start_animation",
                "audio_path": "",
                "audio_text": sub_vi,
                "audio_duration": fallback_dur,
                "audio_duraction": fallback_dur,
                "expression": "relaxed"
            })

    def _on_action_callback(self, action_name: str, args: dict) -> dict:
        """Called by turn engine when LLM triggers a tool action."""
        logger.info(f"[Action Invocation]: '{action_name}' | Args: {args}")
        resolved_action = args.get("action", action_name)
        payload = actions.execute(resolved_action)

        duration = 3.0 if resolved_action in {"backflip", "flyingkick"} else 2.0
        self.worker.enqueue_action(action_payload=payload, duration=duration)
        logger.info(f"Action '{resolved_action}' enqueued to PlaybackWorker (duration: {duration}s)")
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
            logger.info(f"Appended physical interaction context to prompt: {regions}")

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

        logger.info("Beginning voice capture from microphone...")
        success = self.asr.record(output_file=record_wav, silence_duration=1.2)
        if not success:
            logger.warning("Voice capture produced no speech audio.")
            ws_manager.broadcast_sync({"type": "set_state", "state": "idle"})
            return

        text = self.asr.transcribe(record_wav)
        if not text:
            logger.warning("Voice transcription returned empty result.")
            ws_manager.broadcast_sync({"type": "set_state", "state": "idle"})
            return

        logger.info(f"[You (Voice)]: {text}")
        self.chat_turn(text)

    def handle_web_audio(self, audio_path: str) -> None:
        """Process an audio file uploaded directly from the Web UI microphone."""
        logger.info(f"Processing uploaded web audio: {audio_path}")
        ws_manager.broadcast_sync({"type": "set_state", "state": "thinking"})
        text = self.asr.transcribe(audio_path)
        if text:
            logger.info(f"[Web Audio Transcribed]: {text}")
            ws_manager.broadcast_sync({"type": "transcription_result", "text": text})
            self.chat_turn(text)
        else:
            logger.warning("Web audio transcription returned empty result.")
            ws_manager.broadcast_sync({"type": "set_state", "state": "idle"})

    def shutdown(self) -> None:
        """Gracefully release all resources."""
        logger.info("Shutting down Kimiko Companion subsystems...")
        try:
            self.worker.interrupt()
            self.worker.stop()
        except Exception as e:
            logger.warning(f"Worker shutdown warning: {e}")

        try:
            self.db.close_session(self.session_id)
        except Exception as e:
            logger.warning(f"Database session close warning: {e}")

        logger.info("Shutdown complete. Goodbye!")


def start_server_thread(host: str = "0.0.0.0", port: int = 8001):
    """Run the FastAPI application in a background daemon thread."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def main():
    cfg = load_config()

    # 1. Start Web & WebSocket Server
    server, srv_thread = start_server_thread(host=cfg.server_host, port=cfg.server_port)
    time.sleep(1.0)  # Brief wait for uvicorn port binding

    # 2. Start Kimiko Orchestrator
    try:
        kimiko = KimikoCompanion(config=cfg)
    except Exception as e:
        logger.critical(f"FATAL: Failed to initialize Kimiko Companion: {e}", exc_info=True)
        return

    print("\n" + "=" * 65)
    print("  KIMIKO INTERACTIVE CONSOLE")
    print("  - Type your message and press Enter to chat.")
    print("  - Type '/voice' or '/v' to speak via microphone.")
    print("  - Type '/test' or '/t' to test voice & audio playback.")
    print("  - Type 'exit' or press Ctrl+C to quit.")
    print(f"  - Open 3D Avatar in browser: http://localhost:{cfg.server_port}")
    print("  - Detailed log file: kimiko/logs/kimiko.log")
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

            if user_input.lower() in {"/t", "/test"}:
                kimiko.test_voice()
            elif user_input.lower() in {"/v", "/voice", "/mic"}:
                kimiko.voice_turn()
            else:
                kimiko.chat_turn(user_input)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected.")
    finally:
        kimiko.shutdown()


if __name__ == "__main__":
    main()
