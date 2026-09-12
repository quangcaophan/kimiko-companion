from typing import Tuple
import requests
import os
import re
import emoji
import subprocess
import time
import soundfile as sf

from kimiko.core.logger import get_logger

logger = get_logger("audio.tts")


def clean_llm_output(text: str) -> str:
    """Sanitize raw LLM text for speech synthesis by removing asterisks, emojis, and symbols."""
    if not isinstance(text, str):
        return ""
    
    text = re.sub(r"\*.*?\*", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[#`>~]", "", text)
    text = emoji.replace_emoji(text, replace="")
    text = " ".join(text.split())
    return text


class SovitsTTS:
    """Client for local GPT-SoVITS Text-To-Speech inference server."""

    def __init__(
        self,
        base_url: str,
        ref_audio_path: str,
        prompt_text: str,
        prompt_lang: str,
        text_lang: str,
        speed_factor: float = 1.3
    ) -> None:
        self.base_url: str = base_url
        self.ref_audio_path: str = ref_audio_path
        self.prompt_text: str = prompt_text
        self.prompt_lang: str = prompt_lang
        self.text_lang: str = text_lang
        self.speed_factor: float = speed_factor
        logger.debug(
            f"Initialized SovitsTTS: base_url={self.base_url}, "
            f"ref_audio={os.path.basename(self.ref_audio_path)}, speed={self.speed_factor}"
        )

    def synthesize(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        """Synthesize text into a WAV audio file via GPT-SoVITS.

        Args:
            text: Text content to speak.
            output_wav_path: Destination path for the saved WAV file.

        Returns:
            Tuple of (output_wav_path, audio_duration_in_seconds).
        """
        logger.debug(f"Synthesis requested for: {text!r}")
        text_cleaned = clean_llm_output(text)
        if not text_cleaned:
            logger.warning("Synthesis skipped: input text cleaned to empty string.")
            return ("", 0.0)

        # Validate reference audio existence (convert to absolute path for external server)
        abs_ref = os.path.abspath(self.ref_audio_path)
        if not os.path.exists(abs_ref):
            logger.error(f"Reference audio file missing on disk: {abs_ref}")
            return ("", 0.0)

        payload = {
            "text": text_cleaned,
            "text_lang": self.text_lang,
            "ref_audio_path": abs_ref,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "speed_factor": self.speed_factor
        }

        out_dir = os.path.dirname(output_wav_path)
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create output directory {out_dir}: {e}")
                return ("", 0.0)

        url = f"{self.base_url.rstrip('/')}/tts"
        logger.info(f"Sending synthesis request to GPT-SoVITS ({url}): {text_cleaned[:50]!r}...")
        t_start = time.time()
        try:
            response = requests.post(url, json=payload, timeout=30)
        except requests.exceptions.Timeout:
            logger.error(f"Request to GPT-SoVITS at {url} timed out after 30 seconds.")
            return ("", 0.0)
        except requests.exceptions.ConnectionError:
            logger.error(f"Could not connect to GPT-SoVITS server at {url}. Ensure server is running on port 9880.")
            return ("", 0.0)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network request failed for {url}: {e}")
            return ("", 0.0)

        elapsed = time.time() - t_start

        if response.status_code != 200 or not response.content:
            err_detail = response.text[:200] if response.text else "empty response"
            logger.error(f"GPT-SoVITS returned HTTP {response.status_code} in {elapsed:.2f}s: {err_detail}")
            return ("", 0.0)

        # Validate WAV payload format
        if len(response.content) < 44 or not response.content.startswith(b"RIFF"):
            logger.error(
                f"Received invalid audio format ({len(response.content)} bytes, missing 'RIFF' header)."
            )
            return ("", 0.0)
        
        try:
            with open(output_wav_path, "wb") as f:
                f.write(response.content)
            duration: float = sf.info(output_wav_path).duration
            logger.info(
                f"Audio synthesized successfully in {elapsed:.2f}s: {output_wav_path} "
                f"({len(response.content)} bytes, duration: {duration:.2f}s)"
            )
            return output_wav_path, duration
        except Exception as e:
            logger.error(f"Failed to write or inspect audio file {output_wav_path}: {e}")
            return ("", 0.0)


def _start_sovits(
    sovits_dir: str = "",
    base_url: str = "http://127.0.0.1:9880",
    max_retries: int = 20,
    wait_time: int = 2
) -> bool:
    """Automatically verify and launch GPT-SoVITS server if not running."""
    if not sovits_dir:
        sovits_dir = os.getenv("SOVITS_DIR", r"C:\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604")
    logger.info(f"Checking GPT-SoVITS server status at {base_url}...")
    
    # 1. Check if server is already running
    try:
        res = requests.get(f"{base_url}/control", timeout=2)
        if res.status_code in {200, 400}:
            logger.info("GPT-SoVITS server is already online and responsive.")
            return True
    except Exception as e:
        logger.debug(f"GPT-SoVITS probe failed ({e}). Will attempt to launch.")

    # 2. Launch batch script in SoVITS directory
    if not os.path.isdir(sovits_dir):
        logger.warning(f"GPT-SoVITS directory not found on system: {sovits_dir}")
        return False

    bat_path = os.path.join(sovits_dir, "go-api.bat")
    if not os.path.exists(bat_path):
        logger.warning(f"Startup script not found: {bat_path}")
        return False

    logger.info(f"Launching GPT-SoVITS server via {bat_path}...")
    try:
        subprocess.Popen(
            f'cmd.exe /c start "" "{bat_path}"',
            cwd=sovits_dir,
            shell=True
        )
    except Exception as e:
        logger.error(f"Failed to spawn GPT-SoVITS process: {e}")
        return False
    
    # 3. Wait for server to load model and open port
    logger.info(f"Waiting for GPT-SoVITS to load PyTorch weights (up to {max_retries * wait_time}s)...")
    for attempt in range(1, max_retries + 1):
        time.sleep(wait_time)
        try:
            res = requests.get(f"{base_url}/control", timeout=2)
            if res.status_code in {200, 400}:
                logger.info(f"GPT-SoVITS server is ready! (attempt {attempt}/{max_retries})")
                return True
        except Exception:
            logger.debug(f"Waiting for GPT-SoVITS... (attempt {attempt}/{max_retries})")

    logger.error("GPT-SoVITS startup timed out after waiting.")
    return False
