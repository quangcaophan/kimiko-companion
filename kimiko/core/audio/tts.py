from dotenv import load_dotenv
import requests
import os
import re
import emoji
import subprocess
import time

import soundfile as sf

def clean_llm_output(text: str) -> str:
    if not isinstance(text, str):
        return ""
    
    text = re.sub(r"\*.*?\*", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[#`>~]", "", text)
    text = emoji.replace_emoji(text, replace="")
    text = " ".join(text.split())
    return text




class SovitsTTS:
    def __init__(self, base_url: str, ref_audio_path: str, prompt_text: str,
                 prompt_lang: str, text_lang: str, speed_factor: float = 1.3) -> None:
        # tất cả tham số đọc từ persona.yaml["sovits_ping_config"], KHÔNG tự load yaml bên trong class
        self.base_url = base_url
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.prompt_lang = prompt_lang
        self.text_lang = text_lang
        self.speed_factor = speed_factor


    def synthesize(self, text: str, output_wav_path: str) -> tuple[str, float]:
        text_cleaned = clean_llm_output(text)
        if not text_cleaned:
            return ("", 0.0)

        payload = {
            "text": text_cleaned,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "speed_factor": self.speed_factor
        }

        url = f"{self.base_url.rstrip('/')}/tts"
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code !=200 or not response.content:
            raise RuntimeError(f"GPT-SoVITS lỗi: {response.status_code} - {response.text}")
        
        
        with open(output_wav_path, "wb") as f:
            f.write(response.content)
        
        duration = sf.info(output_wav_path).duration

        return output_wav_path, duration


def _start_sovits(
    sovits_dir: str = r"C:\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604",
    base_url: str = "http://127.0.0.1:9880",
    max_retries: int = 20,
    wait_time: int = 2
) -> bool:
    """Tự động kiểm tra và khởi động GPT-SoVITS nếu chưa bật."""
    
    # 1. Kiểm tra xem server đã mở sẵn chưa
    try:
        requests.get(f"{base_url}/control", timeout=2)
        print("GPT-SoVITS server is running!")
        return True
    except Exception:
        pass # Chưa mở thì tiếp tục bật bên dưới
    # 2. Kích hoạt file bat trong thư mục SoVITS
    bat_path = os.path.join(sovits_dir, "go-api.bat")
    if not os.path.exists(bat_path):
        print(f"Cannot find file: {bat_path}")
        return False
    print("Starting GPT-SoVITS in a new window...")
    subprocess.Popen(
        [bat_path],
        cwd=sovits_dir,                               # <- Thư mục làm việc chuẩn
        creationflags=subprocess.CREATE_NEW_CONSOLE   # <- Cửa sổ CMD riêng
    )
    # 3. Chờ server khởi động xong cổng 9880
    print("Waiting for server to load model", end="", flush=True)
    for _ in range(max_retries):
        time.sleep(wait_time)
        try:
            requests.get(f"{base_url}/control", timeout=2)
            print("\nGPT-SoVITS Server is ready!")
            return True
        except Exception:
            print(".", end="", flush=True)
    print("\nStartup Fails (Timeout).")
    return False





if __name__ == "__main__":
    _start_sovits() # Tự check hoặc bật server

    tts = SovitsTTS(
        base_url="http://127.0.0.1:9880",
        ref_audio_path=os.path.abspath(r"kimiko/assets/character_files/main_sample.wav"),
        prompt_text="...", # Có thể để "" hoặc text mẫu của bạn
        prompt_lang="vi",
        text_lang="vi",
    )

    path, duration = tts.synthesize("hi", "test_tts.wav")
    print("✅ Đã tạo file:", path, "- Thời lượng:", duration)
