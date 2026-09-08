from typing import Optional, Union
from groq import Groq
from dotenv import load_dotenv
import os
import sounddevice as sd
import soundfile as sf
import numpy as np

load_dotenv()


class GroqASR:
    """Speech recognition client utilizing Groq's Whisper Large v3 model."""

    def __init__(self, api_key: Optional[str] = None, context_prompt: str = "") -> None:
        self.api_key: str = api_key or os.getenv("GROQ_API_KEY", "")
        self.context_prompt: str = context_prompt
        self.client: Optional[Groq] = self.get_groq_client()
        
    def get_groq_client(self) -> Optional[Groq]:
        if not self.api_key:
            print("[GroqASR] Warning: GROQ_API_KEY not set. Voice transcription will be disabled.")
            return None
        try:
            return Groq(api_key=self.api_key)
        except Exception as e:
            print(f"[GroqASR] Failed to initialize Groq client: {e}")
            return None

    def record(
        self,
        output_file: str,
        samplerate: int = 44100,
        channels: int = 1,
        silence_threshold: float = 0.02,
        silence_duration: float = 1.0,
        device: Optional[Union[int, str]] = None
    ) -> bool:
        """Record audio from microphone with automated Voice Activity Detection (VAD).

        Args:
            output_file: Path to save the recorded WAV.
            samplerate: Sample rate in Hz.
            channels: Audio channels (1 = mono).
            silence_threshold: RMS amplitude threshold considered speech.
            silence_duration: Consecutive seconds of silence to stop recording.
            device: Audio input device index or name.

        Returns:
            True if recording succeeded and speech was captured, False otherwise.
        """
        # Pre-check audio input devices
        try:
            devices = sd.query_devices()
            input_devs = [d for d in devices if isinstance(d, dict) and d.get("max_input_channels", 0) > 0]
            if not input_devs:
                print("[GroqASR.record] No microphone or audio input hardware detected.")
                return False
        except Exception as e:
            print(f"[GroqASR.record] Failed to query audio devices: {e}")
            return False

        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                print(f"[GroqASR.record] Failed to create output directory {output_dir}: {e}")
                return False

        try:
            chunk_duration = 0.1
            block_size = int(samplerate * chunk_duration)

            recored_frames = []
            has_spoken = False
            silence_frames = 0.0
            wait_time = 0.0
            max_wait_timeout = 15.0

            with sd.InputStream(samplerate=samplerate, channels=channels, blocksize=block_size,
                                device=device, dtype="float32") as stream:
                print("Listening... Speak now (press Ctrl+C to cancel)...")

                while True:
                    data, overflowed = stream.read(block_size)
                    if overflowed:
                        print("⚠️ Audio input overflow, possible dropped frames")

                    if data is None or len(data) == 0:
                        continue

                    mean_sq = float(np.mean(data**2))
                    volume = float(np.sqrt(max(0.0, mean_sq)))
                    
                    if not has_spoken:
                        if volume > silence_threshold:
                            has_spoken = True
                            print("Voice detected, recording...")
                            recored_frames.append(data)
                        else:
                            wait_time += chunk_duration
                            if wait_time >= max_wait_timeout:
                                print("No speech detected within timeout (15s)")
                                break
                    else:
                        recored_frames.append(data)
                        if volume < silence_threshold:
                            silence_frames += chunk_duration
                            if silence_frames >= silence_duration:
                                print("Silence detected, stopping recording")
                                break
                        else:
                            silence_frames = 0.0
            
            if not recored_frames or not has_spoken:
                return False
            
            audio_data = np.concatenate(recored_frames, axis=0)
            sf.write(output_file, audio_data, samplerate)
            return True

        except KeyboardInterrupt:
            print("\nRecording canceled by user.")
            return False
        except sd.PortAudioError as e:
            print(f"[GroqASR.record] Audio hardware error (device={device}): {e}")
            return False
        except Exception as e:
            print(f"[GroqASR.record] Unexpected recording error: {e}")
            return False

    def transcribe(self, aud_path: str) -> str:
        """Transcribe a WAV via Groq Whisper-large-v3. Returns the spoken text or empty string on error."""
        if not self.client:
            print("[GroqASR.transcribe] Groq client not configured or GROQ_API_KEY missing.")
            return ""

        if not aud_path:
            print("[GroqASR.transcribe] No audio path provided.")
            return ""

        if not os.path.isfile(aud_path):
            print(f"[GroqASR.transcribe] Audio file not found: {aud_path}")
            return ""

        try:
            if os.path.getsize(aud_path) == 0:
                print(f"[GroqASR.transcribe] Audio file is empty (0 bytes): {aud_path}")
                return ""
        except OSError as e:
            print(f"[GroqASR.transcribe] Failed to inspect audio file: {e}")
            return ""

        try:
            with open(aud_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(aud_path), file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    prompt=self.context_prompt
                )
            text = (transcription.text or "").strip()
            print(f"[GroqASR.transcribe] Recognized: {text!r}")
            return text
        except Exception as e:
            # Catch groq-specific errors if available, fallback to general Exception
            err_name = type(e).__name__
            print(f"[GroqASR.transcribe] API transcription failed [{err_name}]: {e}")
            return ""



# if __name__ == "__main__":
#     asr = GroqASR(api_key=os.getenv("GROQ_API_KEY"), context_prompt="Conversation between Kimiko and the user")

#     ok = asr.record("test_delay.wav", silence_duration=1.5, device=2)
#     if ok:
#         duration = sf.info("test_delay.wav").duration
#         print("Duration:", duration)
#         text = asr.transcribe("test_delay.wav")
#         print("Spoken text:", text)
#     else:
#         print("Recording failed (no speech detected or mic unavailable)")
