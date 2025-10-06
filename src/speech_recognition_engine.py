"""Speech recognition engine with offline support using Whisper"""
import os
import sys
import wave
import json
import numpy as np
import threading
import queue
from pathlib import Path
from typing import Optional, Tuple
import pyaudio
import whisper
from config import config

class SpeechRecognizer:
    """Offline-first speech recognition using OpenAI Whisper"""

    def __init__(self):
        self.model = None
        self.audio = pyaudio.PyAudio()
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.frames = []

        # Load Whisper model for offline recognition
        self._load_model()

    def _load_model(self):
        """Load Whisper model for offline speech recognition"""
        try:
            print(f"Loading Whisper {config.WHISPER_MODEL} model (this may take a moment on first run)...")

            # Whisper will automatically download the model if not present
            self.model = whisper.load_model(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                download_root=str(config.MODELS_DIR)
            )

            print(f"✓ Whisper model loaded successfully (device: {config.WHISPER_DEVICE})")
        except Exception as e:
            print(f"Error loading Whisper model: {e}")
            print("Falling back to tiny model...")
            self.model = whisper.load_model("tiny", download_root=str(config.MODELS_DIR))

    def detect_silence(self, audio_chunk) -> bool:
        """Detect if audio chunk contains silence"""
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
        return np.max(np.abs(audio_data)) < config.SILENCE_THRESHOLD

    def record_audio(self) -> Optional[np.ndarray]:
        """Record audio from microphone until silence is detected"""
        stream = None
        try:
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=config.SAMPLE_RATE,
                input=True,
                frames_per_buffer=config.CHUNK_SIZE
            )

            frames = []
            silence_counter = 0
            silence_threshold_chunks = int(
                config.SILENCE_DURATION * config.SAMPLE_RATE / config.CHUNK_SIZE
            )

            print("🎤 Listening... (speak now)")
            self.is_recording = True

            # Record for maximum timeout or until silence
            max_chunks = int(config.AUDIO_TIMEOUT * config.SAMPLE_RATE / config.CHUNK_SIZE)

            for _ in range(max_chunks):
                if not self.is_recording:
                    break

                data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                frames.append(data)

                # Check for silence
                if self.detect_silence(data):
                    silence_counter += 1
                    if silence_counter >= silence_threshold_chunks and len(frames) > 10:
                        print("✓ Silence detected, processing...")
                        break
                else:
                    silence_counter = 0

            if frames:
                # Convert to numpy array for Whisper
                audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
                audio_float = audio_data.astype(np.float32) / 32768.0
                return audio_float

        except Exception as e:
            print(f"Error recording audio: {e}")
            return None
        finally:
            self.is_recording = False
            if stream:
                stream.stop_stream()
                stream.close()

    def transcribe(self, language: Optional[str] = None) -> Optional[str]:
        """Record and transcribe speech to text"""
        # Record audio
        audio_data = self.record_audio()

        if audio_data is None or len(audio_data) == 0:
            return None

        try:
            # Detect or use specified language
            if language == "auto" or language is None:
                # Let Whisper detect the language
                result = self.model.transcribe(
                    audio_data,
                    fp16=False,
                    language=None,  # Auto-detect
                    task="transcribe"
                )
                detected_lang = result.get("language", "unknown")
                if config.DEBUG:
                    print(f"Detected language: {detected_lang}")
            else:
                # Use specified language
                lang_code = "french" if language == "fr" else "english"
                result = self.model.transcribe(
                    audio_data,
                    fp16=False,
                    language=lang_code,
                    task="transcribe"
                )

            text = result["text"].strip()

            if config.DEBUG:
                print(f"Transcribed: {text}")

            return text

        except Exception as e:
            print(f"Error transcribing audio: {e}")
            return None

    def stop_recording(self):
        """Stop the current recording"""
        self.is_recording = False

    def cleanup(self):
        """Cleanup resources"""
        self.audio.terminate()


class OnlineSpeechRecognizer:
    """Fallback online speech recognition using Google Speech API"""

    def __init__(self):
        import speech_recognition as sr
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

    def transcribe(self, language: Optional[str] = None) -> Optional[str]:
        """Record and transcribe using Google Speech API (requires internet)"""
        import speech_recognition as sr

        try:
            with self.microphone as source:
                print("🎤 Listening (online mode)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(
                    source,
                    timeout=1,
                    phrase_time_limit=config.AUDIO_TIMEOUT
                )

            # Determine language code
            if language == "fr":
                lang_code = "fr-FR"
            elif language == "en":
                lang_code = "en-US"
            else:
                # Try to recognize in both languages
                try:
                    text = self.recognizer.recognize_google(audio, language="en-US")
                    return text
                except:
                    lang_code = "fr-FR"

            text = self.recognizer.recognize_google(audio, language=lang_code)
            return text

        except sr.WaitTimeoutError:
            print("No speech detected")
        except sr.UnknownValueError:
            print("Could not understand audio")
        except sr.RequestError as e:
            print(f"Error with speech service: {e}")
        except Exception as e:
            print(f"Error: {e}")

        return None

    def stop_recording(self):
        """Stop recording (for compatibility)"""
        pass

    def cleanup(self):
        """Cleanup (for compatibility)"""
        pass