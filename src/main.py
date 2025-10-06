#!/usr/bin/env python3
"""
Push-to-Write (P2W) - Voice to Text Application
Press Alt+T to start voice recording, speak, and the text will be inserted at cursor position
"""
import sys
import signal
import time
import threading
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from speech_recognition_engine import SpeechRecognizer, OnlineSpeechRecognizer
from keyboard_handler import KeyboardHandler
from ui_feedback import UIFeedback

class PushToWrite:
    """Main application class"""

    def __init__(self):
        # Create necessary directories
        config.create_dirs()

        # Initialize components
        self.ui = UIFeedback(self.quit)

        # Initialize speech recognizer (offline by default)
        if config.SPEECH_ENGINE == "whisper":
            print("Initializing offline speech recognition (Whisper)...")
            self.speech_recognizer = SpeechRecognizer()
        else:
            print("Initializing online speech recognition...")
            self.speech_recognizer = OnlineSpeechRecognizer()

        # Initialize keyboard handler
        self.keyboard_handler = KeyboardHandler(self.on_hotkey_pressed)

        # Flag for clean shutdown
        self.running = True

    def on_hotkey_pressed(self):
        """Handle hotkey press - start voice recording"""
        if config.DEBUG:
            print(f"Hotkey pressed! Starting voice capture...")

        # Show UI feedback
        self.ui.update_recording_status(True)
        self.ui.show_notification("🎤 Recording", "Speak now...", timeout=1)

        # Start recording in a separate thread
        threading.Thread(target=self._record_and_insert, daemon=True).start()

    def _record_and_insert(self):
        """Record voice and insert transcribed text"""
        try:
            # Get the configured language
            language = config.DEFAULT_LANGUAGE

            # Transcribe speech
            text = self.speech_recognizer.transcribe(language=language)

            # Update UI
            self.ui.update_recording_status(False)

            if text:
                # Insert text at cursor position
                KeyboardHandler.insert_text(text)

                # Show success notification
                preview = text[:50] + "..." if len(text) > 50 else text
                self.ui.show_notification("✓ Transcribed", preview, timeout=2)

                if config.DEBUG:
                    print(f"Inserted text: {text}")
            else:
                self.ui.show_notification("⚠ No Speech", "No speech detected", timeout=2)

        except Exception as e:
            print(f"Error in recording: {e}")
            self.ui.show_notification("❌ Error", str(e), timeout=3)
            self.ui.update_recording_status(False)

    def run(self):
        """Run the main application"""
        print("\n" + "="*60)
        print("🚀 Push-to-Write (P2W) Started")
        print("="*60)
        print(f"📍 Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")
        print(f"🌐 Language: {config.DEFAULT_LANGUAGE}")
        print(f"🔧 Engine: {config.SPEECH_ENGINE}")

        if config.SPEECH_ENGINE == "whisper":
            print(f"📦 Whisper Model: {config.WHISPER_MODEL}")
            print("✓ Working OFFLINE - No internet required!")

        print("\nPress the hotkey to start recording...")
        print("Press Ctrl+C to quit\n")
        print("="*60 + "\n")

        # Create system tray icon
        self.ui.create_tray_icon()

        # Start keyboard listener
        self.keyboard_handler.start()

        # Show startup notification
        self.ui.show_notification(
            "Push-to-Write Started",
            f"Press {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY} to record",
            timeout=3
        )

        # Keep the application running
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            self.quit()

    def quit(self):
        """Clean shutdown"""
        self.running = False

        print("\nCleaning up...")

        # Stop keyboard listener
        if self.keyboard_handler:
            self.keyboard_handler.stop()

        # Stop speech recognizer
        if self.speech_recognizer:
            self.speech_recognizer.stop_recording()
            self.speech_recognizer.cleanup()

        # Cleanup UI
        if self.ui:
            self.ui.cleanup()

        print("✓ Push-to-Write stopped")
        sys.exit(0)

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nReceived interrupt signal...")
    sys.exit(0)

def main():
    """Main entry point"""
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Create and run application
    app = PushToWrite()

    try:
        app.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()