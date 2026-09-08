from typing import Tuple
from dotenv import load_dotenv
import requests
import os
import re
import emoji
import subprocess
import time
import soundfile as sf


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

    def synthesize(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        """Synthesize text into a WAV audio file via GPT-SoVITS.

        Args:
            text: Text content to speak.
            output_wav_path: Destination path for the saved WAV file.

        Returns:
            Tuple of (output_wav_path, audio_duration_in_seconds).
        """
        text_cleaned = clean_llm_output(text)
        if not text_cleaned:
            return ("", 0.0)

        # Validate reference audio existence
        if not os.path.exists(self.ref_audio_path):
            print(f"[SovitsTTS.synthesize] Reference audio file missing: {self.ref_audio_path}")
            return ("", 0.0)

        payload = {
            "text": text_cleaned,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "speed_factor": self.speed_factor
        }

        out_dir = os.path.dirname(output_wav_path)
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                print(f"[SovitsTTS.synthesize] Failed to create output directory {out_dir}: {e}")
                return ("", 0.0)

        url = f"{self.base_url.rstrip('/')}/tts"
        try:
            response = requests.post(url, json=payload, timeout=30)
        except requests.exceptions.Timeout:
            print(f"[SovitsTTS.synthesize] Request to {url} timed out (30s).")
            return ("", 0.0)
        except requests.exceptions.ConnectionError:
            print(f"[SovitsTTS.synthesize] Could not connect to GPT-SoVITS server at {url}. Is it running?")
            return ("", 0.0)
        except requests.exceptions.RequestException as e:
            print(f"[SovitsTTS.synthesize] Network request failed for {url}: {e}")
            return ("", 0.0)

        if response.status_code != 200 or not response.content:
            err_detail = response.text[:200] if response.text else "empty response"
            print(f"[SovitsTTS.synthesize] GPT-SoVITS returned HTTP {response.status_code}: {err_detail}")
            return ("", 0.0)

        # Validate WAV payload format
        if len(response.content) < 44 or not response.content.startswith(b"RIFF"):
            print("[SovitsTTS.synthesize] Received invalid audio format (missing RIFF WAV header).")
            return ("", 0.0)
        
        try:
            with open(output_wav_path, "wb") as f:
                f.write(response.content)
            duration: float = sf.info(output_wav_path).duration
            return output_wav_path, duration
        except Exception as e:
            print(f"[SovitsTTS.synthesize] Failed to write or parse audio file: {e}")
            return ("", 0.0)


def _start_sovits(
    sovits_dir: str = r"C:\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604",
    base_url: str = "http://127.0.0.1:9880",
    max_retries: int = 20,
    wait_time: int = 2
) -> bool:
    """Automatically verify and launch GPT-SoVITS server if not running."""
    
    # 1. Check if server is already running
    try:
        res = requests.get(f"{base_url}/control", timeout=2)
        if res.status_code in {200, 400}:
            print("GPT-SoVITS server is running!")
            return True
    except Exception:
        pass

    # 2. Launch batch script in SoVITS directory
    if not os.path.isdir(sovits_dir):
        print(f"[SovitsTTS] Directory not found: {sovits_dir}")
        return False

    bat_path = os.path.join(sovits_dir, "go-api.bat")
    if not os.path.exists(bat_path):
        print(f"[SovitsTTS] Cannot find startup script: {bat_path}")
        return False

    print("Starting GPT-SoVITS in a new window...")
    try:
        subprocess.Popen(
            f'cmd.exe /c start "" "{bat_path}"',
            cwd=sovits_dir,
            shell=True
        )
    except Exception as e:
        print(f"[SovitsTTS] Failed to spawn GPT-SoVITS process: {e}")
        return False
    
    # 3. Wait for server to load model and open port
    print("Waiting for server to load model", end="", flush=True)
    for _ in range(max_retries):
        time.sleep(wait_time)
        try:
            res = requests.get(f"{base_url}/control", timeout=2)
            if res.status_code in {200, 400}:
                print("\nGPT-SoVITS Server is ready!")
                return True
        except Exception:
            print(".", end="", flush=True)
    print("\nStartup Failed (Timeout).")
    return False




# if __name__ == "__main__":
#     _start_sovits() # Automatically check or start server

#     tts = SovitsTTS(
#         base_url="http://127.0.0.1:9880",
#         ref_audio_path=os.path.abspath(r"kimiko/assets/character_files/main_sample.wav"),
#         prompt_text="", 
#         prompt_lang="en",
#         text_lang="en",
#     )

#     path, duration = tts.synthesize("""Another wander in the night
#                     Let me paint the view
#                     Color a town with my light
#                     For every moment shared with you
#                     Not out in the day
#                     But never fully gone
#                     Going to be back again
#                     Until the coming of a dawn
#                     """, "test_tts.wav")
#     print("✅ Generated file:", path, "- Duration:", duration)
