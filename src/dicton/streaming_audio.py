"""Async audio source for non-blocking streaming transcription.

This module provides an async-compatible audio source that captures audio
in a background thread and yields chunks via an async iterator, ensuring
the asyncio event loop is never blocked.

Problem solved:
    The previous implementation used a synchronous generator that blocked
    the event loop, preventing concurrent WebSocket send/receive operations.

Architecture:
    +-----------------+    +------------------+    +------------------+
    | AUDIO THREAD    |    | ASYNC THREAD     |    | MAIN THREAD      |
    |                 |    |                  |    |                  |
    | sounddevice     |    | asyncio loop     |    | visualizer       |
    | (callback)      |    | (persistent)     |    | keyboard         |
    |     |           |    |                  |    |                  |
    |     v           |    |  WebSocket       |    |                  |
    |  Queue.put()    |--->|  send/recv       |    |                  |
    |                 |    |                  |    |                  |
    +-----------------+    +------------------+    +------------------+

Usage:
    async with AsyncAudioSource() as source:
        async for chunk in source:
            await websocket.send(chunk)
"""

import asyncio
import queue
import threading
from typing import AsyncIterator

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False


class AsyncAudioSource:
    """Async audio source with non-blocking iteration.

    Captures audio via sounddevice callback and provides chunks through
    an async iterator that properly yields control to the event loop.

    Attributes:
        sample_rate: Audio sample rate in Hz (default: 16000)
        chunk_size: Number of samples per chunk (default: 1024)
        channels: Number of audio channels (default: 1)
        dtype: Audio data type (default: int16)

    Example:
        source = AsyncAudioSource(sample_rate=16000)
        source.start()

        async for chunk in source:
            # Process chunk (non-blocking)
            await websocket.send(chunk)

        source.stop()
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        channels: int = 1,
        device: int | None = None,
        queue_maxsize: int = 64,
    ):
        """Initialize async audio source.

        Args:
            sample_rate: Audio sample rate in Hz
            chunk_size: Number of samples per chunk (frames_per_buffer)
            channels: Number of audio channels (mono=1, stereo=2)
            device: Audio device index (None for default)
            queue_maxsize: Maximum queue size before dropping frames
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.device = device

        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=queue_maxsize)
        self._stop_event = threading.Event()
        self._stream: sd.InputStream | None = None
        self._started = False
        self._error: Exception | None = None

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback from sounddevice - runs in audio thread.

        This callback is invoked by sounddevice whenever audio data is available.
        It MUST be non-blocking to avoid audio glitches.

        Args:
            indata: Numpy array with audio data
            frames: Number of frames
            time_info: Timing information
            status: Status flags (overflow, underflow, etc.)
        """
        if status:
            # Log overflow/underflow but don't stop
            from .config import config
            if config.DEBUG:
                print(f"Audio status: {status}")

        if not self._stop_event.is_set():
            try:
                # Convert to bytes and put in queue (non-blocking)
                self._queue.put_nowait(indata.tobytes())
            except queue.Full:
                # Drop oldest frame if queue is full
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(indata.tobytes())
                except (queue.Empty, queue.Full):
                    pass  # Race condition, skip frame

    def start(self) -> None:
        """Start audio capture.

        Creates and starts a sounddevice InputStream with callback mode.
        Audio data is placed in the queue as it arrives.

        Raises:
            RuntimeError: If sounddevice is not available or capture fails
        """
        if not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError(
                "sounddevice is not installed. Install with: pip install sounddevice"
            )

        if self._started:
            return

        self._stop_event.clear()
        self._error = None

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                channels=self.channels,
                dtype="int16",
                device=self.device,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._started = True
        except Exception as e:
            self._error = e
            raise RuntimeError(f"Failed to start audio capture: {e}") from e

    def stop(self) -> None:
        """Stop audio capture.

        Signals the async iterator to stop and closes the audio stream.
        """
        self._stop_event.set()

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass  # Ignore errors during cleanup
            finally:
                self._stream = None

        self._started = False

        # Clear remaining items in queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def get_chunk_sync(self, timeout: float = 0.1) -> bytes | None:
        """Get a single audio chunk synchronously.

        Useful for feeding the visualizer from the main thread.

        Args:
            timeout: Maximum time to wait for a chunk

        Returns:
            Audio chunk bytes, or None if no data available
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def peek_chunk(self) -> bytes | None:
        """Peek at the next chunk without removing it.

        Note: This is not truly atomic - the chunk could be consumed
        by another thread before you can process it.

        Returns:
            Audio chunk bytes if available, None otherwise
        """
        try:
            chunk = self._queue.get_nowait()
            # Put it back at the front (approximately)
            self._queue.put(chunk)
            return chunk
        except queue.Empty:
            return None

    @property
    def is_active(self) -> bool:
        """Check if audio capture is active."""
        return self._started and not self._stop_event.is_set()

    @property
    def queue_size(self) -> int:
        """Get current queue size (number of buffered chunks)."""
        return self._queue.qsize()

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Return async iterator."""
        return self

    async def __anext__(self) -> bytes:
        """Get next audio chunk asynchronously.

        This method properly yields control to the event loop while waiting
        for audio data, preventing the blocking issue in the original design.

        Returns:
            Next audio chunk as bytes

        Raises:
            StopAsyncIteration: When stop() is called or capture ends
        """
        # Poll interval for yielding control
        poll_interval = 0.01  # 10ms - balance between latency and CPU usage

        while not self._stop_event.is_set():
            try:
                # Non-blocking get
                chunk = self._queue.get_nowait()
                return chunk
            except queue.Empty:
                # Yield control to event loop
                await asyncio.sleep(poll_interval)

        # Stop was signaled
        raise StopAsyncIteration

    async def __aenter__(self) -> "AsyncAudioSource":
        """Async context manager entry."""
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        self.stop()


class PyAudioAsyncAdapter:
    """Adapter for PyAudio to provide async iteration.

    Falls back to PyAudio when sounddevice is not available.
    Uses a background thread to capture audio and a queue for async iteration.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        channels: int = 1,
        device: int | None = None,
        queue_maxsize: int = 64,
    ):
        """Initialize PyAudio async adapter.

        Args:
            sample_rate: Audio sample rate in Hz
            chunk_size: Number of samples per chunk
            channels: Number of audio channels
            device: Audio device index (None for default)
            queue_maxsize: Maximum queue size before dropping frames
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.device = device

        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=queue_maxsize)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._error: Exception | None = None
        self._pyaudio = None
        self._stream = None

    def _capture_thread(self):
        """Background thread for PyAudio capture."""
        import pyaudio

        try:
            # Suppress ALSA warnings
            import os
            import contextlib

            @contextlib.contextmanager
            def suppress_stderr():
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
                    yield

            with suppress_stderr():
                self._pyaudio = pyaudio.PyAudio()
                self._stream = self._pyaudio.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.device,
                    frames_per_buffer=self.chunk_size,
                )

            while not self._stop_event.is_set():
                try:
                    data = self._stream.read(self.chunk_size, exception_on_overflow=False)
                    try:
                        self._queue.put_nowait(data)
                    except queue.Full:
                        # Drop oldest frame if queue is full
                        try:
                            self._queue.get_nowait()
                            self._queue.put_nowait(data)
                        except (queue.Empty, queue.Full):
                            pass
                except Exception as e:
                    if not self._stop_event.is_set():
                        self._error = e
                    break

        except Exception as e:
            self._error = e

        finally:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
            if self._pyaudio is not None:
                try:
                    self._pyaudio.terminate()
                except Exception:
                    pass

    def start(self) -> None:
        """Start audio capture in background thread."""
        if self._started:
            return

        self._stop_event.clear()
        self._error = None

        self._thread = threading.Thread(target=self._capture_thread, daemon=True)
        self._thread.start()

        # Wait briefly for thread to start
        import time
        time.sleep(0.1)

        if self._error is not None:
            raise RuntimeError(f"Failed to start audio capture: {self._error}")

        self._started = True

    def stop(self) -> None:
        """Stop audio capture."""
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        self._started = False

        # Clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def get_chunk_sync(self, timeout: float = 0.1) -> bytes | None:
        """Get a single audio chunk synchronously."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_active(self) -> bool:
        """Check if audio capture is active."""
        return self._started and not self._stop_event.is_set()

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Return async iterator."""
        return self

    async def __anext__(self) -> bytes:
        """Get next audio chunk asynchronously."""
        poll_interval = 0.01

        while not self._stop_event.is_set():
            try:
                chunk = self._queue.get_nowait()
                return chunk
            except queue.Empty:
                await asyncio.sleep(poll_interval)

        raise StopAsyncIteration

    async def __aenter__(self) -> "PyAudioAsyncAdapter":
        """Async context manager entry."""
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        self.stop()


def create_async_audio_source(
    sample_rate: int = 16000,
    chunk_size: int = 1024,
    channels: int = 1,
    device: int | None = None,
) -> AsyncAudioSource | PyAudioAsyncAdapter:
    """Factory function to create an async audio source.

    Prefers sounddevice if available, falls back to PyAudio adapter.

    Args:
        sample_rate: Audio sample rate in Hz
        chunk_size: Number of samples per chunk
        channels: Number of audio channels
        device: Audio device index (None for default)

    Returns:
        AsyncAudioSource if sounddevice available, else PyAudioAsyncAdapter
    """
    if SOUNDDEVICE_AVAILABLE:
        return AsyncAudioSource(
            sample_rate=sample_rate,
            chunk_size=chunk_size,
            channels=channels,
            device=device,
        )
    else:
        return PyAudioAsyncAdapter(
            sample_rate=sample_rate,
            chunk_size=chunk_size,
            channels=channels,
            device=device,
        )
