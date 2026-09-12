import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Enable ANSI escape sequences on Windows console
if sys.platform == "win32":
    try:
        os.system("")
    except Exception:
        pass


class ColoredFormatter(logging.Formatter):
    """ANSI colored formatter for clean terminal debugging."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[41m\033[37m",  # White on Red
    }

    MODULE_COLOR = "\033[35m"  # Magenta
    TIME_COLOR = "\033[90m"    # Gray

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        time_str = f"{self.TIME_COLOR}{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}{self.RESET}"
        level_str = f"{color}[{record.levelname:<5}]{self.RESET}"
        module_str = f"{self.MODULE_COLOR}[{record.name}]{self.RESET}"
        message = record.getMessage()

        formatted = f"{time_str} {level_str} {module_str} {message}"
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


class PlainFormatter(logging.Formatter):
    """Plain text formatter for log files (no ANSI escape codes)."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)-5s] [%(name)s] [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


_is_configured = False


def configure_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    """Configure root logger for both console (colored) and persistent file output.

    Args:
        log_level: Desired log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
                   Defaults to LOG_LEVEL environment variable or 'DEBUG'.
        log_file: Destination file path for file logging.
                  Defaults to 'kimiko/logs/kimiko.log'.
    """
    global _is_configured
    if _is_configured:
        return

    level_str = log_level or os.getenv("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_str, logging.DEBUG)

    root = logging.getLogger("kimiko")
    root.setLevel(level)
    root.propagate = False

    # Clear existing handlers to prevent duplicate lines
    if root.hasHandlers():
        root.handlers.clear()

    # 1. Console Handler (Colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter())
    root.addHandler(console_handler)

    # 2. File Handler (Plain text with detailed location)
    if log_file is None:
        # Default: kimiko/logs/kimiko.log relative to workspace
        base_dir = Path(__file__).resolve().parent.parent
        log_dir = base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / "kimiko.log")
    else:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(PlainFormatter())
        root.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Failed to initialize file logger at {log_file}: {e}\n")

    _is_configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger under 'kimiko'.

    Example:
        logger = get_logger("gemini.adapter")  # produces logger named 'kimiko.gemini.adapter'
    """
    if not _is_configured:
        configure_logging()

    if name.startswith("kimiko."):
        full_name = name
    elif name == "kimiko":
        full_name = "kimiko"
    else:
        full_name = f"kimiko.{name}"

    return logging.getLogger(full_name)
