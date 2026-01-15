"""Speech recognition engine - Multi-provider STT with fallback support.

Supports multiple STT providers:
- Gladia: Primary provider with real-time streaming and native translation
- ElevenLabs: Fallback provider with batch transcription

The provider is selected via STT_PROVIDER config, with automatic fallback
if the primary provider is unavailable.

Streaming Architecture:
    The streaming implementation uses an AsyncAudioSource that captures audio
    in a background thread and yields chunks via an async iterator. This allows
    the asyncio event loop to handle both WebSocket send and receive concurrently.

    +------------------+    +------------------+    +------------------+
    | AUDIO THREAD     |    | ASYNC THREAD     |    | MAIN THREAD      |
    |                  |    |                  |    |                  |
    | sounddevice      |    | asyncio loop     |    | visualizer       |
    | (callback)       |    | (persistent)     |    | keyboard         |
    |     |            |    |                  |    |                  |
    |     v            |    |  WebSocket       |    |                  |
    |  Queue.put()     |--->|  send/recv       |    |                  |
    |                  |    |                  |    |                  |
    +------------------+    +------------------+    +------------------+
"""

import contextlib
import io
import os
import threading
import wave
from typing import Callable, Generator

import numpy as np

from .platform_utils import IS_LINUX, IS_WINDOWS


# Suppress audio system warnings (ALSA on Linux, etc.)
@contextlib.contextmanager
def suppress_stderr():
    """Suppress stderr to hide audio system warnings."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        try:
            os.dup2(devnull, 2)
            yield
        finally:
            os.dup2(old_stderr, 2)
            os.close(devnull)
            os.close(old_stderr)
    except Exception:
        # On some platforms this may fail, just yield without suppression
        yield


with suppress_stderr():
    import pyaudio

from .config import config
from .stt_factory import get_stt_provider_with_fallback, get_available_stt_providers
from .stt_provider import STTCapability, TranscriptionResult
from .text_processor import get_text_processor

# Import visualizer based on configured backend
if config.VISUALIZER_BACKEND == "gtk":
    try:
        from .visualizer_gtk import get_visualizer
    except ImportError as e:
        print(f"⚠ GTK not available ({e}), falling back to pygame")
        from .visualizer import get_visualizer
elif config.VISUALIZER_BACKEND == "vispy":
    try:
        from .visualizer_vispy import get_visualizer
    except ImportError:
        print("⚠ VisPy not available, falling back to pygame")
        from .visualizer import get_visualizer
else:
    from .visualizer import get_visualizer


class SpeechRecognizer:
    """Speech recognizer: record audio, then transcribe via configured STT provider.

    Uses the multi-provider abstraction layer with automatic fallback:
    - Primary provider selected via STT_PROVIDER config
    - Falls back to alternative if primary unavailable
    - Supports both batch and streaming transcription modes

    Attributes:
        use_elevenlabs: Backward compatibility - True if any STT provider is available
        recording: True while actively recording audio
    """

    def __init__(self):
        self.recording = False
        self._cancelled = False  # Flag for immediate cancel (discard audio)
        self.input_device = None

        # Get STT provider (with automatic fallback)
        self._stt_provider = get_stt_provider_with_fallback()

        with suppress_stderr():
            self.audio = pyaudio.PyAudio()

        self._find_input_device()

        # Log active provider
        if self._stt_provider.is_available():
            provider_name = self._stt_provider.name
            capabilities = []
            if self._stt_provider.supports_streaming():
                capabilities.append("streaming")
            if self._stt_provider.supports_translation():
                capabilities.append("translation")
            cap_str = f" ({', '.join(capabilities)})" if capabilities else ""
            print(f"✓ Using {provider_name} STT{cap_str}")
        else:
            print("⚠ No STT provider available")
            available = get_available_stt_providers()
            if not available:
                print("  → Set GLADIA_API_KEY or ELEVENLABS_API_KEY in .env")

    @property
    def use_elevenlabs(self) -> bool:
        """Backward compatibility: check if any STT provider is available.

        Returns:
            True if any STT provider (Gladia, ElevenLabs, etc.) is available
        """
        return self._stt_provider.is_available()

    @property
    def client(self):
        """Backward compatibility: return provider's internal client.

        Note: This is for backward compatibility only. New code should use
        the provider abstraction directly.
        """
        return getattr(self._stt_provider, "_client", None)

    def _find_input_device(self):
        """Find the best available input device - cross-platform."""
        self.device_sample_rate = config.SAMPLE_RATE

        try:
            if config.MIC_DEVICE != "auto":
                try:
                    self.input_device = int(config.MIC_DEVICE)
                    info = self.audio.get_device_info_by_index(self.input_device)
                    self.device_sample_rate = int(info["defaultSampleRate"])
                    print(f"✓ Mic: {info['name']} @ {self.device_sample_rate}Hz (forced)")
                    return
                except Exception:
                    print(f"⚠ Device {config.MIC_DEVICE} not found, auto-detecting...")

            default_info = self.audio.get_default_input_device_info()
            default_idx = default_info["index"]

            devices = []
            for i in range(self.audio.get_device_count()):
                try:
                    info = self.audio.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:
                        devices.append(
                            {
                                "index": i,
                                "name": info["name"],
                                "rate": int(info["defaultSampleRate"]),
                                "is_default": i == default_idx,
                            }
                        )
                except Exception:
                    continue

            if not devices:
                print("⚠ No input devices found")
                return

            # Platform-specific device selection
            selected = self._select_best_device(devices)

            self.input_device = selected["index"]
            self.device_sample_rate = selected["rate"]
            print(f"✓ Mic: {selected['name']}")

        except Exception as e:
            print(f"⚠ Could not detect mic: {e}")
            self.input_device = None
            self.device_sample_rate = config.SAMPLE_RATE

    def _select_best_device(self, devices: list) -> dict:
        """Select the best audio input device based on platform."""
        selected = None

        if IS_LINUX:
            # Linux: prefer PulseAudio, then default
            for d in devices:
                if d["name"].lower() == "pulse":
                    selected = d
                    break

        elif IS_WINDOWS:
            # Windows: prefer default device, or one with "microphone" in name
            for d in devices:
                if d["is_default"]:
                    selected = d
                    break
            if not selected:
                for d in devices:
                    if "microphone" in d["name"].lower():
                        selected = d
                        break

        # Fallback: use default device or first available
        if not selected:
            for d in devices:
                if d["is_default"]:
                    selected = d
                    break
        if not selected:
            selected = devices[0]

        return selected

    def record(self) -> np.ndarray | None:
        """Record audio until stopped, with visualizer feedback.

        Note: After recording stops, the visualizer switches to processing mode
        (pulsing animation) instead of stopping. The caller is responsible for
        calling viz.stop() after processing is complete.
        """
        if not self._stt_provider.is_available():
            print("⚠ No STT provider available")
            return None

        viz = get_visualizer()
        stream = None
        frames = []
        self._cancelled = False  # Reset cancel flag

        try:
            with suppress_stderr():
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=config.SAMPLE_RATE,
                    input=True,
                    input_device_index=self.input_device,
                    frames_per_buffer=config.CHUNK_SIZE,
                )

            self.recording = True
            viz.start()
            print("🎤 Recording...")

            while self.recording:
                try:
                    data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                    viz.update(data)
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠ Read error: {e}")
                    break

        except Exception as e:
            print(f"❌ Recording error: {e}")
            viz.stop()  # Stop visualizer on error
            return None

        finally:
            self.recording = False
            if stream:
                stream.stop_stream()
                stream.close()

        # Check if recording was cancelled (tap detected)
        if self._cancelled:
            viz.stop()  # Stop visualizer on cancel
            return None

        if not frames:
            viz.stop()  # Stop visualizer if no frames
            return None

        # Switch visualizer to processing mode (pulsing animation)
        # Caller will call viz.stop() after transcription/LLM processing completes
        viz.start_processing()

        # Convert to numpy array
        audio_data = b"".join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        return audio_array

    def record_and_stream_transcribe(
        self,
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Record audio with real-time streaming transcription.

        This method enables near-zero perceived latency by transcribing
        DURING recording rather than after. Only supported by Gladia.

        For providers that don't support streaming, this falls back to
        standard record + transcribe.

        Architecture:
            Uses AsyncAudioSource for non-blocking audio capture in a
            background thread. Audio chunks are fed to the WebSocket
            via async iteration, allowing concurrent send/receive.

        Args:
            on_partial: Optional callback for partial (interim) results

        Returns:
            Final TranscriptionResult when recording stops, or None on failure
        """
        if not self._stt_provider.is_available():
            print("** No STT provider available")
            return None

        # Check if provider supports streaming
        if not self._stt_provider.supports_streaming():
            if config.DEBUG:
                print(f"** {self._stt_provider.name} doesn't support streaming, using batch mode")
            # Fall back to batch mode
            audio = self.record()
            if audio is None:
                return None
            text = self.transcribe(audio)
            if text:
                return TranscriptionResult(text=text, is_final=True)
            return None

        # Check if provider has the new async streaming method
        if not hasattr(self._stt_provider, 'stream_transcribe_async'):
            if config.DEBUG:
                print(f"** {self._stt_provider.name} doesn't support async streaming, using legacy mode")
            return self._record_and_stream_transcribe_legacy(on_partial)

        # Use the new async streaming architecture
        return self._record_and_stream_transcribe_async(on_partial)

    def _record_and_stream_transcribe_async(
        self,
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Async implementation of streaming transcription.

        Uses AsyncAudioSource for proper non-blocking operation.
        Audio is streamed to the STT provider DURING recording for
        near-zero perceived latency.

        Architecture:
            1. Start audio capture (sounddevice callback -> queue)
            2. Submit streaming coroutine to async bridge
            3. Coroutine consumes from queue via async iteration
            4. Visualizer also consumes from queue (via separate peek)
            5. User stops recording -> audio source stops -> coroutine ends
            6. Final result is returned
        """
        from .streaming_audio import create_async_audio_source
        from .async_bridge import get_async_bridge
        from concurrent.futures import TimeoutError as FutureTimeoutError

        viz = get_visualizer()
        self._cancelled = False
        result_holder = [None]  # Use list to allow modification in nested function
        error_holder = [None]

        # Create async audio source
        audio_source = create_async_audio_source(
            sample_rate=config.SAMPLE_RATE,
            chunk_size=config.CHUNK_SIZE,
            channels=1,
            device=self.input_device,
        )

        # Thread for updating visualizer
        viz_stop_event = threading.Event()
        frames_buffer = []  # Buffer for visualizer updates

        def viz_updater():
            """Update visualizer from audio source queue.

            Note: The audio source queue is consumed by the async coroutine,
            so we use a separate buffer that's populated when chunks are read.
            """
            while not viz_stop_event.is_set():
                if frames_buffer:
                    chunk = frames_buffer.pop(0)
                    viz.update(chunk)
                else:
                    import time
                    time.sleep(0.01)

        def streaming_worker():
            """Run streaming transcription in async bridge.

            This runs in the async bridge thread and consumes audio
            from the queue while recording.
            """
            try:
                bridge = get_async_bridge()

                async def stream_with_viz():
                    """Stream audio and collect for visualizer."""
                    nonlocal frames_buffer

                    # Wrapper that also feeds visualizer
                    class VizAudioSource:
                        def __init__(self, source):
                            self._source = source

                        def __aiter__(self):
                            return self

                        async def __anext__(self):
                            chunk = await self._source.__anext__()
                            # Feed visualizer buffer
                            frames_buffer.append(chunk)
                            return chunk

                    viz_source = VizAudioSource(audio_source)

                    # Call provider's async streaming method
                    return await self._stt_provider._async_stream_transcribe(
                        viz_source,
                        on_partial=on_partial,
                    )

                future = bridge.submit(stream_with_viz())
                result_holder[0] = future.result(timeout=config.STT_TIMEOUT)

            except FutureTimeoutError:
                if config.DEBUG:
                    print("** Streaming timed out")
            except Exception as e:
                error_holder[0] = e
                if config.DEBUG:
                    print(f"** Streaming worker error: {e}")

        try:
            # Start audio capture
            audio_source.start()
            self.recording = True
            viz.start()
            print("** Recording (streaming)...")

            # Start visualizer updater thread
            viz_thread = threading.Thread(target=viz_updater, daemon=True)
            viz_thread.start()

            # Start streaming worker in background
            streaming_thread = threading.Thread(target=streaming_worker, daemon=True)
            streaming_thread.start()

            # Wait for recording to stop (user releases key or double-tap)
            while self.recording and not self._cancelled:
                import time
                time.sleep(0.05)

            # Stop audio capture - this will cause the async iterator to stop
            audio_source.stop()
            viz_stop_event.set()

            if self._cancelled:
                viz.stop()
                return None

            # Switch to processing mode while waiting for final result
            viz.start_processing()

            # Wait for streaming to complete
            streaming_thread.join(timeout=10.0)

            result = result_holder[0]
            if error_holder[0]:
                raise error_holder[0]

            if result is None:
                viz.stop()
                return None

            # Apply noise filtering
            if result.text:
                filtered = self._filter(result.text)
                if filtered:
                    return TranscriptionResult(
                        text=filtered,
                        language=result.language,
                        confidence=result.confidence,
                        is_final=True,
                        translation=result.translation,
                    )

            viz.stop()
            return None

        except Exception as e:
            print(f"** Streaming transcription error: {e}")
            if config.DEBUG:
                import traceback
                traceback.print_exc()
            viz.stop()
            return None
        finally:
            audio_source.stop()
            viz_stop_event.set()
            self.recording = False

    def _record_and_stream_transcribe_legacy(
        self,
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Legacy streaming implementation using sync generator.

        Kept for backward compatibility with providers that don't support
        the new async streaming architecture.
        """
        viz = get_visualizer()
        stream = None
        self._cancelled = False

        def audio_generator() -> Generator[bytes, None, None]:
            """Generate audio chunks as they're recorded."""
            nonlocal stream
            try:
                with suppress_stderr():
                    stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=config.SAMPLE_RATE,
                        input=True,
                        input_device_index=self.input_device,
                        frames_per_buffer=config.CHUNK_SIZE,
                    )

                self.recording = True
                viz.start()
                print("** Recording (streaming legacy)...")

                while self.recording and not self._cancelled:
                    try:
                        data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                        viz.update(data)
                        yield data
                    except Exception as e:
                        if config.DEBUG:
                            print(f"** Read error: {e}")
                        break

            finally:
                self.recording = False
                if stream:
                    stream.stop_stream()
                    stream.close()

        try:
            result = self._stt_provider.stream_transcribe(
                audio_generator(),
                on_partial=on_partial,
            )

            if self._cancelled or result is None:
                viz.stop()
                return None

            # Switch to processing mode briefly (for any post-processing)
            viz.start_processing()

            # Apply noise filtering
            if result and result.text:
                filtered = self._filter(result.text)
                if filtered:
                    return TranscriptionResult(
                        text=filtered,
                        language=result.language,
                        confidence=result.confidence,
                        is_final=True,
                        translation=result.translation,
                    )

            viz.stop()
            return None

        except Exception as e:
            print(f"** Streaming transcription error: {e}")
            if config.DEBUG:
                import traceback
                traceback.print_exc()
            viz.stop()
            return None

    def stop(self):
        """Stop recording (will process audio)."""
        self.recording = False

    def record_for_duration(self, duration_seconds: float) -> np.ndarray | None:
        """Record audio for a fixed duration (for latency testing)."""
        if not self._stt_provider.is_available():
            print("⚠ No STT provider available")
            return None

        stream = None
        frames = []

        try:
            with suppress_stderr():
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=config.SAMPLE_RATE,
                    input=True,
                    input_device_index=self.input_device,
                    frames_per_buffer=config.CHUNK_SIZE,
                )

            # Calculate number of chunks needed
            chunks_needed = int(duration_seconds * config.SAMPLE_RATE / config.CHUNK_SIZE)

            for _ in range(chunks_needed):
                try:
                    data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠ Read error: {e}")
                    break

        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

        finally:
            if stream:
                stream.stop_stream()
                stream.close()

        if not frames:
            return None

        # Convert to numpy array
        audio_data = b"".join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        return audio_array

    def cancel(self):
        """Cancel recording (discard audio, tap detected)."""
        self._cancelled = True
        self.recording = False

    def transcribe(self, audio: np.ndarray) -> str | None:
        """Transcribe recorded audio using configured STT provider.

        Args:
            audio: Audio data as float32 numpy array (range -1.0 to 1.0)

        Returns:
            Transcribed text after filtering, or None on failure
        """
        if audio is None or len(audio) == 0:
            return None

        if not self._stt_provider.is_available():
            print("⚠ No STT provider available")
            return None

        try:
            # Convert float32 audio to WAV bytes
            wav_bytes = self._audio_to_wav(audio)

            # Call provider
            result = self._stt_provider.transcribe(wav_bytes, audio_format="wav")

            if result and result.text:
                return self._filter(result.text)
            return None

        except Exception as e:
            print(f"❌ Transcription error: {e}")
            if config.DEBUG:
                import traceback
                traceback.print_exc()

            # Try fallback provider if available
            return self._transcribe_with_fallback(audio)

    def translate(self, audio: np.ndarray, target_language: str = "en") -> str | None:
        """Transcribe and translate audio using native provider translation.

        Uses Gladia's native translation when available (more efficient than
        separate transcription + LLM translation).

        Args:
            audio: Audio data as float32 numpy array
            target_language: Target language code (e.g., "en", "fr")

        Returns:
            Translated text, or None if native translation unavailable

        Raises:
            NotImplementedError: If provider doesn't support native translation
        """
        if audio is None or len(audio) == 0:
            return None

        if not self._stt_provider.is_available():
            return None

        if not self._stt_provider.supports_translation():
            raise NotImplementedError(
                f"{self._stt_provider.name} doesn't support native translation"
            )

        try:
            wav_bytes = self._audio_to_wav(audio)
            result = self._stt_provider.translate(wav_bytes, target_language)

            if result and result.translation:
                return self._filter(result.translation)
            return None

        except Exception as e:
            if config.DEBUG:
                print(f"Native translation error: {e}")
            raise

    def _audio_to_wav(self, audio: np.ndarray) -> bytes:
        """Convert float32 audio array to WAV bytes.

        Args:
            audio: Audio data as float32 numpy array (range -1.0 to 1.0)

        Returns:
            WAV file bytes
        """
        # Convert float32 audio to int16 bytes
        audio_int16 = (audio * 32767).astype(np.int16)

        # Create WAV in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(config.SAMPLE_RATE)
            wav_file.writeframes(audio_int16.tobytes())

        return wav_buffer.getvalue()

    def _transcribe_with_fallback(self, audio: np.ndarray) -> str | None:
        """Attempt transcription with fallback provider.

        Args:
            audio: Audio data as float32 numpy array

        Returns:
            Transcribed text or None if all providers fail
        """
        from .stt_factory import get_stt_provider

        available = get_available_stt_providers()
        current_name = self._stt_provider.name.lower()

        for provider_name in available:
            if provider_name != current_name:
                try:
                    fallback = get_stt_provider(provider_name)
                    if fallback.is_available():
                        wav_bytes = self._audio_to_wav(audio)
                        result = fallback.transcribe(wav_bytes)
                        if result and result.text:
                            if config.DEBUG:
                                print(f"✓ Fallback to {fallback.name} succeeded")
                            return self._filter(result.text)
                except Exception:
                    continue

        return None

    def _filter(self, text: str) -> str | None:
        """Filter out noise, apply custom dictionary, and clean up text."""
        if not text or len(text) < 3:
            return None

        lower = text.lower().strip()

        # Common noise phrases
        noise = {
            "thanks for watching",
            "thank you for watching",
            "subscribe",
            "you",
            "thank you",
            "merci",
            "bye",
            "ok",
            "okay",
            "um",
            "uh",
            "hmm",
            "huh",
            "ah",
            "oh",
            "eh",
        }
        if lower in noise:
            return None

        # Single short words are usually noise
        if len(text.split()) == 1 and len(text) < 10:
            return None

        # Apply custom dictionary replacements
        processor = get_text_processor()
        text = processor.process(text)

        return text

    def cleanup(self):
        """Cleanup resources."""
        self.audio.terminate()
