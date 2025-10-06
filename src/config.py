"""Configuration management for Push-to-Write"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration"""

    # Paths
    BASE_DIR = Path(__file__).parent.parent
    MODELS_DIR = BASE_DIR / "models"

    # Language settings
    DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "auto")
    SUPPORTED_LANGUAGES = ["en", "fr", "auto"]

    # Speech recognition engine (whisper for offline, google for online)
    SPEECH_ENGINE = os.getenv("SPEECH_ENGINE", "whisper")

    # Whisper settings (for offline mode)
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    WHISPER_DEVICE = "cuda" if os.getenv("USE_CUDA", "false").lower() == "true" else "cpu"

    # Keyboard shortcut
    HOTKEY_MODIFIER = os.getenv("HOTKEY_MODIFIER", "alt")
    HOTKEY_KEY = os.getenv("HOTKEY_KEY", "t")

    # Audio settings
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
    AUDIO_TIMEOUT = int(os.getenv("AUDIO_TIMEOUT", "10"))
    SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "500"))
    SILENCE_DURATION = float(os.getenv("SILENCE_DURATION", "1.0"))  # Stop after 1 second of silence

    # UI settings
    SHOW_TRAY_ICON = os.getenv("SHOW_TRAY_ICON", "true").lower() == "true"
    SHOW_NOTIFICATIONS = os.getenv("SHOW_NOTIFICATIONS", "true").lower() == "true"

    # Debug mode
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def create_dirs(cls):
        """Create necessary directories"""
        cls.MODELS_DIR.mkdir(exist_ok=True)

config = Config()