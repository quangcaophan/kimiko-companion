import os
import time
import queue
import threading
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any, Optional, Dict

from kimiko.core.logger import get_logger

logger = get_logger("avatar.worker")


class ItemType(Enum):
    AUDIO = "audio"
    ACTION = "action"
    CUSTOM = "custom"


@dataclass
class PlaybackItem:
    item_type: ItemType
    payload: Dict[str, Any]
    duration: float = 0.0


class PlaybackWorker:
    """Thread-safe sequential FIFO queue manager for audio lines and avatar actions."""

    def __init__(self, broadcast_fn: Callable[[Dict[str, Any]], None], pad_seconds: float = 0.15) -> None:
        self.broadcast_fn = broadcast_fn
        self.pad_seconds = pad_seconds
        self.queue: queue.Queue[Optional[PlaybackItem]] = queue.Queue()
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self.is_playing: bool = False
        logger.debug(f"Initialized PlaybackWorker (pad_seconds={pad_seconds})")

    def start(self) -> None:
        """Start the background playback processing thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()
            logger.info("Avatar PlaybackWorker background thread started.")

    def stop(self) -> None:
        """Stop playback loop and wait for worker thread to exit."""
        logger.info("Stopping avatar PlaybackWorker thread...")
        self._running = False
        self.queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Avatar PlaybackWorker stopped.")
    
    def join(self) -> None:
        """Wait for all enqueued items to finish playback."""
        logger.debug("Waiting for PlaybackWorker queue to drain...")
        self.queue.join()
        logger.debug("PlaybackWorker queue drained.")

    def enqueue_audio(self, audio_path: str, text: str, duration: float, expression: str = "neutral") -> None:
        """Enqueue an audio line with subtitles and facial expression."""
        payload = {
            "type": "start_animation",
            "audio_path": audio_path,
            "expression": expression,
            "audio_text": text,
            "audio_duration": duration,
            "audio_duraction": duration,  # Backward compatibility
        }
        item = PlaybackItem(item_type=ItemType.AUDIO, payload=payload, duration=duration)
        self.queue.put(item)
        logger.info(
            f"Enqueued AUDIO playback item (duration={duration:.2f}s, queue_size={self.queue.qsize()}): {text[:60]!r}"
        )

    def enqueue_action(self, action_payload: Dict[str, Any], duration: float = 0.0) -> None:
        """Enqueue a physical animation action (e.g. Mixamo FBX or VRMA)."""
        item = PlaybackItem(item_type=ItemType.ACTION, payload=action_payload, duration=duration)
        self.queue.put(item)
        logger.info(
            f"Enqueued ACTION playback item (duration={duration:.2f}s, queue_size={self.queue.qsize()}): "
            f"type={action_payload.get('type')}, url={os.path.basename(action_payload.get('animation_url', ''))}"
        )

    def interrupt(self) -> None:
        """Clear all pending playback items and reset avatar to idle state."""
        cleared_count = 0
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                cleared_count += 1
            except (queue.Empty, ValueError):
                break
        self.is_playing = False
        logger.info(f"PlaybackWorker interrupted: purged {cleared_count} pending items.")
        try:
            self.broadcast_fn({"type": "set_state", "state": "idle"})
        except Exception as e:
            logger.error(f"Failed to broadcast idle state on interrupt: {e}")

    def _worker_loop(self) -> None:
        while self._running:
            try:
                item = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                self.queue.task_done()
                break

            try:
                self.is_playing = True
                logger.debug(
                    f"Playing {item.item_type.value} item (expected duration: {item.duration:.2f}s + {self.pad_seconds:.2f}s pad)..."
                )
                try:
                    self.broadcast_fn(item.payload)
                except Exception as e:
                    logger.error(f"PlaybackWorker broadcast callback error: {e}", exc_info=True)

                if item.duration > 0 and self._running:
                    time.sleep(item.duration + self.pad_seconds)
            except Exception as e:
                logger.error(f"PlaybackWorker error while processing item: {e}", exc_info=True)
            finally:
                self.queue.task_done()

            if self.queue.empty():
                self.is_playing = False
                logger.debug("Playback queue empty. Resetting avatar to idle state.")
                try:
                    self.broadcast_fn({"type": "set_state", "state": "idle"})
                except Exception:
                    pass
