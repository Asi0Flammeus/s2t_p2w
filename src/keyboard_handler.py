"""Keyboard shortcut handler and text insertion"""
import time
import threading
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController
import pyautogui
import pyperclip
from config import config

class KeyboardHandler:
    """Handle keyboard shortcuts and text insertion"""

    def __init__(self, on_hotkey_callback):
        self.on_hotkey_callback = on_hotkey_callback
        self.keyboard = KeyboardController()
        self.listener = None
        self.current_keys = set()
        self.is_recording = False

        # Parse hotkey configuration
        self.hotkey = self._parse_hotkey()

    def _parse_hotkey(self):
        """Parse hotkey from config"""
        modifier = config.HOTKEY_MODIFIER.lower()
        key = config.HOTKEY_KEY.lower()

        # Map modifier strings to pynput keys
        modifier_map = {
            "alt": Key.alt,
            "alt_l": Key.alt_l,
            "alt_r": Key.alt_r,
            "ctrl": Key.ctrl,
            "ctrl_l": Key.ctrl_l,
            "ctrl_r": Key.ctrl_r,
            "cmd": Key.cmd,
            "shift": Key.shift,
            "shift_l": Key.shift_l,
            "shift_r": Key.shift_r,
        }

        modifier_key = modifier_map.get(modifier, Key.alt)

        # Return the combination
        return {modifier_key, key}

    def start(self):
        """Start listening for keyboard shortcuts"""
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        print(f"✓ Keyboard listener started (Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY})")

    def stop(self):
        """Stop listening for keyboard shortcuts"""
        if self.listener:
            self.listener.stop()
            self.listener = None

    def _on_press(self, key):
        """Handle key press events"""
        try:
            # Add to current keys
            if hasattr(key, 'char') and key.char:
                self.current_keys.add(key.char.lower())
            else:
                self.current_keys.add(key)

            # Check if hotkey combination is pressed
            if self._is_hotkey_pressed() and not self.is_recording:
                self.is_recording = True
                # Run callback in separate thread to not block keyboard listener
                threading.Thread(target=self._trigger_recording, daemon=True).start()

        except Exception as e:
            if config.DEBUG:
                print(f"Key press error: {e}")

    def _on_release(self, key):
        """Handle key release events"""
        try:
            # Remove from current keys
            if hasattr(key, 'char') and key.char:
                self.current_keys.discard(key.char.lower())
            else:
                self.current_keys.discard(key)

        except Exception as e:
            if config.DEBUG:
                print(f"Key release error: {e}")

    def _is_hotkey_pressed(self):
        """Check if the configured hotkey combination is pressed"""
        # Check for modifier
        modifier = config.HOTKEY_MODIFIER.lower()
        key_char = config.HOTKEY_KEY.lower()

        # Check if Alt is pressed
        if modifier in ["alt", "alt_l", "alt_r"]:
            if Key.alt not in self.current_keys and \
               Key.alt_l not in self.current_keys and \
               Key.alt_r not in self.current_keys:
                return False

        # Check if Ctrl is pressed
        if modifier in ["ctrl", "ctrl_l", "ctrl_r"]:
            if Key.ctrl not in self.current_keys and \
               Key.ctrl_l not in self.current_keys and \
               Key.ctrl_r not in self.current_keys:
                return False

        # Check if the main key is pressed
        return key_char in self.current_keys

    def _trigger_recording(self):
        """Trigger the recording callback"""
        try:
            if self.on_hotkey_callback:
                self.on_hotkey_callback()
        finally:
            # Reset recording flag after callback completes
            time.sleep(0.5)  # Small delay to prevent rapid re-triggering
            self.is_recording = False

    @staticmethod
    def insert_text(text: str):
        """Insert text at the current cursor position"""
        if not text:
            return

        try:
            # Method 1: Use clipboard (most reliable for complex text)
            old_clipboard = pyperclip.paste()  # Save current clipboard

            # Copy text to clipboard
            pyperclip.copy(text)

            # Small delay to ensure clipboard is updated
            time.sleep(0.05)

            # Paste using Ctrl+V (or Cmd+V on Mac)
            pyautogui.hotkey('ctrl', 'v')

            # Small delay before restoring clipboard
            time.sleep(0.1)

            # Restore original clipboard content
            try:
                pyperclip.copy(old_clipboard)
            except:
                pass  # Ignore clipboard restore errors

        except Exception as e:
            # Fallback: Type the text directly (slower but works everywhere)
            print(f"Clipboard method failed, using direct typing: {e}")
            try:
                pyautogui.typewrite(text, interval=0.001)
            except Exception as e2:
                print(f"Error inserting text: {e2}")

    @staticmethod
    def insert_text_with_typing(text: str):
        """Alternative method: Type text character by character"""
        try:
            pyautogui.typewrite(text, interval=0.001)
        except Exception as e:
            print(f"Error typing text: {e}")