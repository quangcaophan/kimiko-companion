"""LM Studio server lifecycle management.

Provides functions to start and stop the LM Studio server,
which hosts the local embedding model used by the memory system.
"""
import os
import time
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

from kimiko.core.logger import get_logger

logger = get_logger("memory.lifecycle")
load_dotenv()

LM_STUDIO_HOST = os.getenv("LM_STUDIO_HOST", "127.0.0.1")
LM_STUDIO_PORT = os.getenv("LM_STUDIO_PORT", "1234")
BASE_URL = f"http://{LM_STUDIO_HOST}:{LM_STUDIO_PORT}/v1"


def start_llm(base_url: str = BASE_URL, max_retries: int = 20, wait_time: int = 2) -> bool:
    """Verify and launch LM Studio server if not already running.

    Args:
        base_url: LM Studio API base URL.
        max_retries: Max polling attempts after launching.
        wait_time: Seconds between polling attempts.

    Returns:
        True if server is confirmed running, False on timeout.
    """
    logger.info(f"Checking LM Studio server status at {base_url}...")
    check_client = OpenAI(base_url=base_url, api_key="lm-studio", timeout=5.0)

    # 1. Check if server is already running
    try:
        check_client.models.list()
        logger.info("LM Studio server is already online and responsive.")
        return True
    except Exception as e:
        logger.debug(f"LM Studio probe failed ({e}). Will attempt to launch.")

    # 2. Launch LM Studio server
    try:
        subprocess.Popen(["lms", "server", "start"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Launched LM Studio server via 'lms server start'.")
    except FileNotFoundError:
        logger.warning("'lms' command not found in PATH. Please start LM Studio manually.")
        return False
    except Exception as e:
        logger.error(f"Failed to spawn LM Studio process: {e}")
        return False

    # 3. Wait for server to be ready
    logger.info(f"Waiting for LM Studio to load model (up to {max_retries * wait_time}s)...")
    for attempt in range(1, max_retries + 1):
        time.sleep(wait_time)
        try:
            check_client.models.list()
            logger.info(f"LM Studio server is ready! (attempt {attempt}/{max_retries})")
            return True
        except Exception:
            logger.debug(f"Waiting for LM Studio... (attempt {attempt}/{max_retries})")

    logger.error("LM Studio startup timed out after waiting.")
    return False


def end_llm() -> None:
    """Stop the LM Studio server."""
    logger.info("Stopping LM Studio Server...")
    try:
        subprocess.run(["lms", "server", "stop"], check=True)
        logger.info("LM Studio server stopped successfully.")
    except FileNotFoundError:
        logger.warning("'lms' command not found in PATH.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to stop LM Studio server: {e}")