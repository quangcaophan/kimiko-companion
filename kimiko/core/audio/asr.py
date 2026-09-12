from typing import Optional, Union
import os
import time
from groq import Groq
import sounddevice as sd
import soundfile as sf
import numpy as np

from kimiko.core.logger import get_logger

logger = get_logger("audio.asr")


class GroqASR:
    """Speech recognition client utilizing Groq's Whisper Large v3 model."""

    def __init__(self, api_key: Optional[str] = None, context_prompt: str = "") -> None:
        self.api_key: str = api_key or os.getenv("GROQ_API_KEY", "")
        self.context_prompt: str = context_prompt
        self.client: Optional[Groq] = self.get_groq_client()
        
    def get_groq_client(self) -> Optional[Groq]:
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not set. Voice recording and transcription will be disabled.")
            return None
        try:
            client = Groq(api_key=self.api_key)
            logger.debug("Groq ASR client initialized successfully.")
            return client
        except Exception as e:
            logger.error(f"Failed to initialize Groq ASR client: {e}")
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
                logger.error("No microphone or audio input hardware detected by sounddevice.")
                return False
            logger.debug(f"Detected {len(input_devs)} audio input device(s): {[d.get('name') for d in input_devs]}")
        except Exception as e:
            logger.error(f"Failed to query audio input devices: {e}")
            return False

        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create audio output directory {output_dir}: {e}")
                return False

        try:
            chunk_duration = 0.1
            block_size = int(samplerate * chunk_duration)

            recorded_frames = []
            has_spoken = False
            silence_frames = 0.0
            wait_time = 0.0
            max_wait_timeout = 15.0

            logger.info("Listening for speech... Speak now (or wait 15s to timeout)...")

            with sd.InputStream(samplerate=samplerate, channels=channels, blocksize=block_size,
                                device=device, dtype="float32") as stream:

                while True:
                    data, overflowed = stream.read(block_size)
                    if overflowed:
                        logger.warning("Audio input buffer overflowed, possible dropped frames.")

                    if data is None or len(data) == 0:
                        continue

                    mean_sq = float(np.mean(data**2))
                    volume = float(np.sqrt(max(0.0, mean_sq)))
                    
                    if not has_spoken:
                        if volume > silence_threshold:
                            has_spoken = True
                            logger.info(f"Voice detected (RMS volume: {volume:.4f} > {silence_threshold}). Recording...")
                            recorded_frames.append(data)
                        else:
                            wait_time += chunk_duration
                            if wait_time >= max_wait_timeout:
                                logger.info("No speech detected within 15s timeout window.")
                                break
                    else:
                        recorded_frames.append(data)
                        if volume < silence_threshold:
                            silence_frames += chunk_duration
                            if silence_frames >= silence_duration:
                                logger.debug(f"Silence detected ({silence_frames:.1f}s >= {silence_duration}s). Finishing capture.")
                                break
                        else:
                            silence_frames = 0.0
            
            if not recorded_frames or not has_spoken:
                logger.debug("No recorded speech frames collected.")
                return False
            
            audio_data = np.concatenate(recorded_frames, axis=0)
            sf.write(output_file, audio_data, samplerate)
            dur = len(audio_data) / samplerate
            logger.info(f"Audio captured successfully: {output_file} ({dur:.2f}s, {len(audio_data)} samples)")
            return True

        except KeyboardInterrupt:
            logger.info("Recording canceled by user.")
            return False
        except sd.PortAudioError as e:
            logger.error(f"PortAudio hardware error (device={device}): {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected audio recording error: {e}")
            return False

    def transcribe(self, aud_path: str) -> str:
        """Transcribe a WAV via Groq Whisper-large-v3. Returns the spoken text or empty string on error."""
        if not self.client:
            logger.warning("Groq client not configured or GROQ_API_KEY missing. Cannot transcribe.")
            return ""

        if not aud_path:
            logger.warning("No audio path provided for transcription.")
            return ""

        if not os.path.isfile(aud_path):
            logger.error(f"Audio file not found on disk: {aud_path}")
            return ""

        try:
            size_bytes = os.path.getsize(aud_path)
            if size_bytes == 0:
                logger.error(f"Audio file is empty (0 bytes): {aud_path}")
                return ""
        except OSError as e:
            logger.error(f"Failed to inspect audio file {aud_path}: {e}")
            return ""

        logger.info(f"Transcribing {os.path.basename(aud_path)} ({size_bytes} bytes) via Groq Whisper Large v3...")
        t_start = time.time()
        try:
            with open(aud_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(aud_path), file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    prompt=self.context_prompt
                )
            text = (transcription.text or "").strip()
            elapsed = time.time() - t_start
            logger.info(f"Transcription finished in {elapsed:.2f}s: {text!r}")
            return text
        except Exception as e:
            err_name = type(e).__name__
            logger.error(f"Groq API transcription failed [{err_name}]: {e}")
            return ""
