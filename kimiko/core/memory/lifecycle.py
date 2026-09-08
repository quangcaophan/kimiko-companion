import os
import time
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

LM_STUDIO_HOST = os.getenv("LM_STUDIO_HOST", "127.0.0.1")
LM_STUDIO_PORT = os.getenv("LM_STUDIO_PORT", "1234")
BASE_URL = f"http://{LM_STUDIO_HOST}:{LM_STUDIO_PORT}/v1"


def start_llm(base_url: str, max_retries: int = 20, wait_time: int = 2) -> bool:
    check_client = OpenAI(base_url=base_url, api_key="lm-studio", timeout=5.0)
    subprocess.Popen(["lms", "server", "start"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Waiting for LM Studio server to be ready", end="")
    for _ in range(max_retries):
        try:
            check_client.models.list()
            print("\n✅ LM Studio Server is ready!")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(wait_time)
    print("\n❌ LM Studio startup failed (Timeout).")
    return False


def end_llm():
    print("\nStopping LM Studio Server...")
    subprocess.run(["lms", "server", "stop"])