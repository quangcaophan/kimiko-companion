import time
import queue
import threading
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any, Optional, Dict

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

    def start(self) -> None:
        """Start the background playback processing thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop playback loop and wait for worker thread to exit."""
        self._running = False
        self.queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
    
    def join(self) -> None:
        """Wait for all enqueued items to finish playback."""
        self.queue.join()

    def enqueue_audio(self, audio_path: str, text: str, duration: float, expression: str = "neutral") -> None:
        """Enqueue an audio line with subtitles and facial expression."""
        payload = {
            "type": "start_animation",
            "audio_path": audio_path,
            "expression": expression,
            "audio_text": text,
            "audio_duraction": duration,
        }
        self.queue.put(PlaybackItem(item_type=ItemType.AUDIO, payload=payload, duration=duration))

    def enqueue_action(self, action_payload: Dict[str, Any], duration: float = 0.0) -> None:
        """Enqueue a physical animation action (e.g. Mixamo FBX or VRMA)."""
        self.queue.put(PlaybackItem(item_type=ItemType.ACTION, payload=action_payload, duration=duration))

    def interrupt(self) -> None:
        """Clear all pending playback items and reset avatar to idle state."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except (queue.Empty, ValueError):
                break
        self.is_playing = False
        try:
            self.broadcast_fn({"type": "set_state", "state": "idle"})
        except Exception as e:
            print(f"[PlaybackWorker.interrupt] Broadcast idle state failed: {e}")

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
                try:
                    self.broadcast_fn(item.payload)
                except Exception as e:
                    print(f"[PlaybackWorker] Broadcast callback error: {e}")

                if item.duration > 0 and self._running:
                    time.sleep(item.duration + self.pad_seconds)
            except Exception as e:
                print(f"[PlaybackWorker] Worker item error: {e}")
            finally:
                self.queue.task_done()

            if self.queue.empty():
                self.is_playing = False
                try:
                    self.broadcast_fn({"type": "set_state", "state": "idle"})
                except Exception:
                    pass



# if __name__ == "__main__":
#     def broadcast_mock(msg):
#         print("BROADCAST:", msg)

#     worker = PlaybackWorker(
#         broadcast_fn=broadcast_mock
#     )
#     worker.start()
#     worker.enqueue_audio(audio_path="audio1.wav",text="hi", duration=1.5)
#     worker.enqueue_action(action_payload={"type": "wave"}, duration=1.0)
#     worker.enqueue_audio(audio_path="audio2.wav",text="hello", duration=2.0)
#     worker.join()
#     worker.stop()  
