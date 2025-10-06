"""UI feedback and system tray integration"""
import os
import sys
import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item
from plyer import notification
from config import config

class UIFeedback:
    """Handle UI feedback and system tray"""

    def __init__(self, quit_callback):
        self.quit_callback = quit_callback
        self.tray_icon = None
        self.icon_thread = None

    def show_notification(self, title: str, message: str, timeout: int = 2):
        """Show desktop notification"""
        if not config.SHOW_NOTIFICATIONS:
            return

        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Push-to-Write",
                timeout=timeout
            )
        except Exception as e:
            print(f"Notification error: {e}")

    def create_tray_icon(self):
        """Create and show system tray icon"""
        if not config.SHOW_TRAY_ICON:
            return

        # Create icon image
        icon_image = self._create_icon_image()

        # Create menu
        menu = pystray.Menu(
            item(f"Push-to-Write", lambda: None, enabled=False),
            item(f"Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}", lambda: None, enabled=False),
            item("───────────", lambda: None, enabled=False),
            item("Language", pystray.Menu(
                item("Auto-detect", lambda: self._set_language("auto"),
                     checked=lambda item: config.DEFAULT_LANGUAGE == "auto"),
                item("English", lambda: self._set_language("en"),
                     checked=lambda item: config.DEFAULT_LANGUAGE == "en"),
                item("French", lambda: self._set_language("fr"),
                     checked=lambda item: config.DEFAULT_LANGUAGE == "fr")
            )),
            item("───────────", lambda: None, enabled=False),
            item("Quit", self._quit_app)
        )

        # Create system tray icon
        self.tray_icon = pystray.Icon(
            "push-to-write",
            icon_image,
            "Push-to-Write - Voice to Text",
            menu
        )

        # Run in separate thread
        self.icon_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.icon_thread.start()

    def _create_icon_image(self):
        """Create icon image for system tray"""
        # Create a simple microphone icon
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw microphone shape
        # Mic body
        draw.ellipse([20, 10, 44, 40], fill=(70, 130, 180), outline=(50, 90, 140), width=2)
        # Mic stand
        draw.rectangle([28, 35, 36, 48], fill=(60, 60, 60))
        # Mic base
        draw.ellipse([24, 45, 40, 52], fill=(60, 60, 60))

        return image

    def _set_language(self, language: str):
        """Set the default language"""
        config.DEFAULT_LANGUAGE = language
        self.show_notification("Language Changed", f"Language set to: {language}")
        print(f"Language changed to: {language}")

    def _quit_app(self):
        """Quit the application"""
        if self.tray_icon:
            self.tray_icon.stop()
        if self.quit_callback:
            self.quit_callback()

    def update_recording_status(self, is_recording: bool):
        """Update UI to show recording status"""
        if is_recording:
            self.show_notification("Recording", "Speak now...", timeout=1)
            # Could update tray icon color here
        else:
            # Recording stopped
            pass

    def cleanup(self):
        """Cleanup UI resources"""
        if self.tray_icon:
            self.tray_icon.stop()