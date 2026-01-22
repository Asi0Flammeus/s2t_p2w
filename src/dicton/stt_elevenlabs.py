"""ElevenLabs Scribe STT Provider for Dicton

Provides batch transcription using ElevenLabs' Scribe model.
High-accuracy transcription with word-level timestamps.

Key features:
- Batch-only (no streaming)
- Word-level timestamps
- Auto language detection
"""

import io
import logging
import wave
from collections.abc import Callable, Iterator

from .stt_provider import (
    STTCapability,
    STTProvider,
    STTProviderConfig,
    TranscriptionResult,
    WordInfo,
)

logger = logging.getLogger(__name__)

# ElevenLabs SDK - lazily imported to avoid hard dependency
_elevenlabs_client = None


def _get_elevenlabs_client(api_key: str, timeout: float = 120.0):
    """Lazily initialize ElevenLabs client.

    Args:
        api_key: ElevenLabs API key.
        timeout: Request timeout in seconds.

    Returns:
        ElevenLabs client instance or None if unavailable.
    """
    global _elevenlabs_client
    if _elevenlabs_client is not None:
        return _elevenlabs_client

    try:
        from elevenlabs.client import ElevenLabs

        _elevenlabs_client = ElevenLabs(api_key=api_key, timeout=timeout)
        return _elevenlabs_client
    except ImportError:
        logger.warning("elevenlabs package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize ElevenLabs client: {e}")
        return None


class ElevenLabsSTTProvider(STTProvider):
    """ElevenLabs Scribe batch transcription provider.

    Features:
    - Batch transcription via REST API
    - Word-level timestamps
    - Auto language detection
    - High accuracy for multiple languages
    """

    DEFAULT_MODEL = "scribe_v1"

    def __init__(self, config: STTProviderConfig | None = None):
        """Initialize ElevenLabs provider.

        Args:
            config: Provider configuration. If None, uses environment defaults.
        """
        super().__init__(config)
        self._client = None
        self._available_checked = False
        self._is_available = False

        # Use config model or fall back to environment/default
        if not self._config.model:
            import os

            self._config.model = os.getenv("ELEVENLABS_MODEL", self.DEFAULT_MODEL)

        # Get API key from config or environment
        if not self._config.api_key:
            import os

            self._config.api_key = os.getenv("ELEVENLABS_API_KEY", "")

        # Get timeout from config or environment
        if self._config.timeout == 30.0:  # Default value
            import os

            self._config.timeout = float(os.getenv("STT_TIMEOUT", "120"))

    @property
    def name(self) -> str:
        return "ElevenLabs Scribe"

    @property
    def capabilities(self) -> set[STTCapability]:
        return {STTCapability.BATCH, STTCapability.WORD_TIMESTAMPS}

    def is_available(self) -> bool:
        """Check if ElevenLabs is available and configured.

        Returns:
            True if API key is set and client can be initialized.
        """
        if self._available_checked:
            return self._is_available

        self._available_checked = True

        if not self._config.api_key:
            logger.debug("ElevenLabs API key not configured")
            self._is_available = False
            return False

        # Try to initialize client
        client = _get_elevenlabs_client(self._config.api_key, self._config.timeout)
        if client is None:
            self._is_available = False
            return False

        self._client = client
        self._is_available = True
        return True

    def _ensure_client(self) -> bool:
        """Ensure client is initialized.

        Returns:
            True if client is ready.
        """
        if self._client is not None:
            return True

        if not self.is_available():
            return False

        return self._client is not None

    def _convert_to_wav(self, audio_data: bytes) -> io.BytesIO | None:
        """Convert audio data to WAV format if needed.

        Assumes input is either:
        - Raw PCM int16 samples at configured sample rate
        - Already a WAV file

        Args:
            audio_data: Audio data as bytes.

        Returns:
            BytesIO containing WAV data, or None on error.
        """
        # Check if already WAV format (starts with RIFF header)
        if audio_data[:4] == b"RIFF":
            return io.BytesIO(audio_data)

        # Assume raw PCM int16, convert to WAV
        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self._config.sample_rate)
                wav_file.writeframes(audio_data)
            wav_buffer.seek(0)
            return wav_buffer
        except Exception as e:
            logger.error(f"Failed to convert audio to WAV: {e}")
            return None

    def transcribe(self, audio_data: bytes) -> TranscriptionResult | None:
        """Transcribe audio data using ElevenLabs Scribe.

        Args:
            audio_data: Audio data as bytes (WAV or raw PCM int16).

        Returns:
            TranscriptionResult on success, None on failure.
        """
        if not audio_data:
            return None

        if not self._ensure_client():
            logger.error("ElevenLabs client not available")
            return None

        # Convert to WAV format
        wav_buffer = self._convert_to_wav(audio_data)
        if wav_buffer is None:
            return None

        try:
            # Call ElevenLabs STT API (language_code=None for auto-detect)
            result = self._client.speech_to_text.convert(
                file=wav_buffer,
                model_id=self._config.model,
            )

            if not result or not hasattr(result, "text"):
                logger.warning("ElevenLabs returned no text")
                return None

            # Build result
            transcription = TranscriptionResult(
                text=result.text or "",
                language=getattr(result, "language_code", "") or "",
                is_final=True,
            )

            # Extract word timestamps if available
            if hasattr(result, "words") and result.words:
                transcription.words = [
                    WordInfo(
                        word=w.text if hasattr(w, "text") else str(w),
                        start=getattr(w, "start", 0.0),
                        end=getattr(w, "end", 0.0),
                        confidence=getattr(w, "confidence", 1.0),
                    )
                    for w in result.words
                ]

            # Calculate duration from audio
            wav_buffer.seek(0)
            try:
                with wave.open(wav_buffer, "rb") as wav:
                    frames = wav.getnframes()
                    rate = wav.getframerate()
                    transcription.duration = frames / rate
            except Exception:
                pass  # Duration is optional

            return transcription

        except Exception as e:
            logger.error(f"ElevenLabs transcription failed: {e}")
            return None

    def stream_transcribe(
        self,
        audio_generator: Iterator[bytes],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Transcribe audio stream (falls back to batch mode).

        ElevenLabs Scribe doesn't support streaming, so we collect all chunks
        and transcribe in batch.

        Args:
            audio_generator: Iterator yielding audio chunks.
            on_partial: Optional callback (not used for ElevenLabs).

        Returns:
            Final TranscriptionResult on success, None on failure.
        """
        # Collect all audio chunks
        chunks = list(audio_generator)
        if not chunks:
            return None

        audio_data = b"".join(chunks)
        return self.transcribe(audio_data)

    def translate(
        self, audio_data: bytes, target_language: str = "en"
    ) -> TranscriptionResult | None:
        """Translate audio (not supported by ElevenLabs Scribe).

        ElevenLabs Scribe doesn't have native translation.

        Args:
            audio_data: Audio data as bytes.
            target_language: Target language code.

        Returns:
            None (translation not supported).
        """
        # ElevenLabs Scribe doesn't support native translation
        return None
