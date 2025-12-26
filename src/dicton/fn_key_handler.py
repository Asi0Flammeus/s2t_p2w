"""FN Key Handler for Dicton - Capture XF86WakeUp (keycode 151) via evdev

This module provides FN key capture on Linux using evdev, which can detect
special keys like XF86WakeUp that pynput may not support directly.
"""

import threading
import time
from collections.abc import Callable
from enum import Enum, auto

from .config import config
from .platform_utils import IS_LINUX

# XF86WakeUp keycode - typically mapped to FN key on many laptops
KEY_WAKEUP = 143  # evdev keycode for KEY_WAKEUP (XF86WakeUp)


class HotkeyState(Enum):
    """State machine states for FN key detection"""

    IDLE = auto()
    KEY_DOWN = auto()  # Key pressed, waiting to determine hold vs tap
    RECORDING_PTT = auto()  # Push-to-talk mode (hold)
    WAITING_DOUBLE = auto()  # First tap released, waiting for second
    RECORDING_TOGGLE = auto()  # Toggle mode (double-tap locked)


class FnKeyHandler:
    """Handle FN key (XF86WakeUp) with push-to-talk and toggle modes

    State Machine:
        IDLE + key_down → KEY_DOWN (start timer)
        KEY_DOWN + hold > threshold → RECORDING_PTT (start recording)
        KEY_DOWN + key_up < threshold → WAITING_DOUBLE (wait for second tap)
        RECORDING_PTT + key_up → IDLE (stop, process, output)
        WAITING_DOUBLE + key_down < window → RECORDING_TOGGLE (lock recording)
        WAITING_DOUBLE + timeout → IDLE (no action)
        RECORDING_TOGGLE + double_tap → IDLE (stop, process, output)
    """

    def __init__(
        self,
        on_start_recording: Callable[[], None] | None = None,
        on_stop_recording: Callable[[], None] | None = None,
    ):
        self.on_start_recording = on_start_recording
        self.on_stop_recording = on_stop_recording

        # State machine
        self._state = HotkeyState.IDLE
        self._state_lock = threading.Lock()

        # Timing
        self._key_down_time: float = 0
        self._key_up_time: float = 0

        # Thresholds from config
        self._hold_threshold = config.HOTKEY_HOLD_THRESHOLD_MS / 1000.0
        self._double_tap_window = config.HOTKEY_DOUBLE_TAP_WINDOW_MS / 1000.0

        # Threads
        self._listener_thread: threading.Thread | None = None
        self._timer_thread: threading.Thread | None = None
        self._running = False

        # evdev device
        self._device = None
        self._evdev_available = False

    def start(self):
        """Start the FN key listener"""
        if not IS_LINUX:
            print("FN key handler only supported on Linux")
            return False

        try:
            import evdev  # noqa: F401

            self._evdev_available = True
        except ImportError:
            print("evdev not installed. Install with: pip install evdev")
            print("Or: pip install dicton[fnkey]")
            return False

        # Find keyboard device with KEY_WAKEUP support
        self._device = self._find_keyboard_device()
        if not self._device:
            print("No keyboard device with FN key (KEY_WAKEUP) found")
            print("You may need to run with sudo or add user to 'input' group")
            return False

        self._running = True
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        if config.DEBUG:
            print(f"FN key handler started on device: {self._device.name}")
        return True

    def stop(self):
        """Stop the FN key listener"""
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)

    def _find_keyboard_device(self):
        """Find a keyboard device that supports KEY_WAKEUP"""
        try:
            import evdev
            from evdev import ecodes

            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            for device in devices:
                caps = device.capabilities()
                # Check if device has EV_KEY capability
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    # Check for KEY_WAKEUP (143)
                    if KEY_WAKEUP in keys:
                        return device
                    # Some systems may have it as a different keycode
                    # Also check for KEY_FN (0x1d0 = 464)
                    if 464 in keys:
                        return device

            # Fallback: return first keyboard-like device
            for device in devices:
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    # Check if it looks like a keyboard (has common letter keys)
                    if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                        if config.DEBUG:
                            print(f"Using fallback keyboard: {device.name}")
                        return device

            return None
        except PermissionError:
            print("Permission denied accessing input devices")
            print("Add user to 'input' group: sudo usermod -aG input $USER")
            return None
        except Exception as e:
            if config.DEBUG:
                print(f"Error finding keyboard device: {e}")
            return None

    def _listen_loop(self):
        """Main event loop for evdev"""
        try:
            from evdev import ecodes

            for event in self._device.read_loop():
                if not self._running:
                    break

                # Only process key events
                if event.type != ecodes.EV_KEY:
                    continue

                # Check for our target key (KEY_WAKEUP or fallback)
                if event.code == KEY_WAKEUP or event.code == 464:  # KEY_FN
                    if event.value == 1:  # Key down
                        self._on_fn_key_down()
                    elif event.value == 0:  # Key up
                        self._on_fn_key_up()
                    # value == 2 is key repeat, ignored

        except Exception as e:
            if self._running and config.DEBUG:
                print(f"FN key listener error: {e}")

    def _on_fn_key_down(self):
        """Handle FN key press"""
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.IDLE:
                self._key_down_time = now
                self._state = HotkeyState.KEY_DOWN
                # Start timer to check for hold
                self._start_hold_timer()

            elif self._state == HotkeyState.WAITING_DOUBLE:
                # Second tap within window - enter toggle mode
                if now - self._key_up_time < self._double_tap_window:
                    self._state = HotkeyState.RECORDING_TOGGLE
                    self._trigger_start_recording()
                else:
                    # Window expired, treat as new press
                    self._key_down_time = now
                    self._state = HotkeyState.KEY_DOWN
                    self._start_hold_timer()

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # In toggle mode, key down starts the stop sequence
                self._key_down_time = now

    def _on_fn_key_up(self):
        """Handle FN key release"""
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.KEY_DOWN:
                hold_duration = now - self._key_down_time
                if hold_duration < self._hold_threshold:
                    # Short press - wait for potential double-tap
                    self._key_up_time = now
                    self._state = HotkeyState.WAITING_DOUBLE
                    self._start_double_tap_timer()
                # If hold threshold passed, we're already in RECORDING_PTT

            elif self._state == HotkeyState.RECORDING_PTT:
                # Release during PTT - stop recording
                self._state = HotkeyState.IDLE
                self._trigger_stop_recording()

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # Check for double-tap to exit toggle mode
                hold_duration = now - self._key_down_time
                if hold_duration < self._hold_threshold:
                    # Quick tap while in toggle - check if it's a double-tap to stop
                    if now - self._key_up_time < self._double_tap_window:
                        self._state = HotkeyState.IDLE
                        self._trigger_stop_recording()
                self._key_up_time = now

    def _start_hold_timer(self):
        """Start timer to detect hold gesture"""

        def check_hold():
            time.sleep(self._hold_threshold)
            with self._state_lock:
                if self._state == HotkeyState.KEY_DOWN:
                    # Still holding - enter PTT mode
                    self._state = HotkeyState.RECORDING_PTT
                    self._trigger_start_recording()

        self._timer_thread = threading.Thread(target=check_hold, daemon=True)
        self._timer_thread.start()

    def _start_double_tap_timer(self):
        """Start timer for double-tap window"""

        def check_timeout():
            time.sleep(self._double_tap_window)
            with self._state_lock:
                if self._state == HotkeyState.WAITING_DOUBLE:
                    # Timeout - return to idle (single tap does nothing)
                    self._state = HotkeyState.IDLE

        timer = threading.Thread(target=check_timeout, daemon=True)
        timer.start()

    def _trigger_start_recording(self):
        """Trigger recording start callback"""
        if self.on_start_recording:
            # Run callback in separate thread to not block event handling
            threading.Thread(target=self.on_start_recording, daemon=True).start()

    def _trigger_stop_recording(self):
        """Trigger recording stop callback"""
        if self.on_stop_recording:
            threading.Thread(target=self.on_stop_recording, daemon=True).start()

    @property
    def state(self) -> HotkeyState:
        """Get current state (thread-safe)"""
        with self._state_lock:
            return self._state

    @property
    def is_recording(self) -> bool:
        """Check if currently in a recording state"""
        with self._state_lock:
            return self._state in (HotkeyState.RECORDING_PTT, HotkeyState.RECORDING_TOGGLE)

    @property
    def is_toggle_mode(self) -> bool:
        """Check if in toggle (locked) recording mode"""
        with self._state_lock:
            return self._state == HotkeyState.RECORDING_TOGGLE
