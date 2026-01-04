"""FN Key Handler for Dicton - Capture XF86WakeUp (keycode 151) via evdev

This module provides FN key capture on Linux using evdev, which can detect
special keys like XF86WakeUp that pynput may not support directly.

Delayed Start Mode:
    Recording starts after a small activation delay (default 50ms) to avoid
    confusion with double-tap. If released before delay, treated as a tap.
    Double-tap enters toggle mode (locked recording).
"""

import threading
import time
from collections.abc import Callable
from enum import Enum, auto

from .config import config
from .platform_utils import IS_LINUX
from .processing_mode import ProcessingMode

# XF86WakeUp keycode - typically mapped to FN key on many laptops
KEY_WAKEUP = 143  # evdev keycode for KEY_WAKEUP (XF86WakeUp)

# Modifier keycodes (from evdev/ecodes)
KEY_SPACE = 57
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_LEFTALT = 56
KEY_RIGHTALT = 100

# Secondary hotkey keycode mapping (name -> evdev keycode)
SECONDARY_HOTKEY_MAP = {
    "escape": 1, "esc": 1,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "capslock": 58, "caps": 58,
    "pause": 119, "break": 119,
    "insert": 110, "ins": 110,
    "home": 102, "end": 107,
    "pageup": 104, "pgup": 104,
    "pagedown": 109, "pgdn": 109,
}


class HotkeyState(Enum):
    """State machine states for FN key detection"""

    IDLE = auto()
    WAITING_ACTIVATION = auto()  # Key pressed, waiting for activation delay
    RECORDING_PTT = auto()  # Push-to-talk mode (recording active)
    WAITING_DOUBLE = auto()  # First tap released, waiting for second
    RECORDING_TOGGLE = auto()  # Toggle mode (double-tap locked)


class FnKeyHandler:
    """Handle FN key (XF86WakeUp) with push-to-talk and toggle modes

    Delayed Start State Machine (avoids confusion with double-tap):
        IDLE + key_down → WAITING_ACTIVATION (wait for activation delay)
        WAITING_ACTIVATION + delay_elapsed → RECORDING_PTT (start recording)
        WAITING_ACTIVATION + key_up → WAITING_DOUBLE (tap detected, wait for double-tap)
        RECORDING_PTT + key_up < threshold → WAITING_DOUBLE (cancel, wait for double-tap)
        RECORDING_PTT + key_up >= threshold → IDLE (stop recording, process)
        WAITING_DOUBLE + key_down < window → RECORDING_TOGGLE (start toggle recording)
        WAITING_DOUBLE + timeout → IDLE (no action)
        RECORDING_TOGGLE + tap → IDLE (stop recording, process)
    """

    def __init__(
        self,
        on_start_recording: Callable[[ProcessingMode], None] | None = None,
        on_stop_recording: Callable[[], None] | None = None,
        on_cancel_recording: Callable[[], None] | None = None,
    ):
        """Initialize FN key handler.

        Args:
            on_start_recording: Callback when recording starts, receives the ProcessingMode.
            on_stop_recording: Callback when recording stops (will process audio).
            on_cancel_recording: Callback when recording is cancelled (tap detected, discard audio).
        """
        self.on_start_recording = on_start_recording
        self.on_stop_recording = on_stop_recording
        self.on_cancel_recording = on_cancel_recording

        # State machine
        self._state = HotkeyState.IDLE
        self._state_lock = threading.Lock()

        # Current processing mode (determined by modifiers at key press)
        self._current_mode = ProcessingMode.BASIC

        # Modifier key states (tracked via evdev)
        self._space_pressed = False
        self._ctrl_pressed = False
        self._shift_pressed = False
        self._alt_pressed = False

        # Timing
        self._key_down_time: float = 0
        self._key_up_time: float = 0

        # Track if toggle mode was just started (to ignore first release for advanced modes)
        self._toggle_first_release: bool = False

        # Thresholds from config
        self._hold_threshold = config.HOTKEY_HOLD_THRESHOLD_MS / 1000.0
        self._double_tap_window = config.HOTKEY_DOUBLE_TAP_WINDOW_MS / 1000.0
        self._activation_delay = config.HOTKEY_ACTIVATION_DELAY_MS / 1000.0

        # Threads
        self._listener_thread: threading.Thread | None = None
        self._timer_thread: threading.Thread | None = None
        self._activation_timer: threading.Timer | None = None
        self._running = False

        # evdev devices
        self._device = None  # Primary device (laptop keyboard for FN key)
        self._secondary_device = None  # Secondary device (e.g., ZSA for secondary hotkey)
        self._evdev_available = False

        # Secondary hotkey (alternative to FN key)
        self._secondary_keycode = SECONDARY_HOTKEY_MAP.get(config.SECONDARY_HOTKEY, None)

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

        # Find keyboard devices
        self._device, self._secondary_device = self._find_keyboard_devices()
        if not self._device and not self._secondary_device:
            print("No keyboard device found")
            print("You may need to run with sudo or add user to 'input' group")
            return False

        self._running = True
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        # Log devices
        if self._device:
            print(f"FN key handler started on device: {self._device.name}")
        if self._secondary_device and self._secondary_keycode:
            print(f"Secondary hotkey: '{config.SECONDARY_HOTKEY}' → code {self._secondary_keycode} on {self._secondary_device.name}")

        return True

    def stop(self):
        """Stop the FN key listener"""
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
        if self._secondary_device:
            try:
                self._secondary_device.close()
            except Exception:
                pass
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)

    def _find_keyboard_devices(self):
        """Find keyboard devices for FN key and secondary hotkey.

        Returns:
            Tuple of (primary_device, secondary_device):
            - primary_device: Laptop keyboard for FN/KEY_WAKEUP (skips external keyboards)
            - secondary_device: External keyboard (ZSA etc.) for secondary hotkey
        """
        try:
            import evdev
            from evdev import ecodes

            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            # Helper to check if device is an external keyboard (ZSA, etc.)
            def is_external_keyboard(name: str) -> bool:
                external_brands = ["ZSA", "Voyager", "Ergodox", "Moonlander", "Planck"]
                return any(brand.lower() in name.lower() for brand in external_brands)

            # Debug: list all devices with KEY_WAKEUP capability
            if config.DEBUG:
                print("Scanning input devices...")
                for device in devices:
                    caps = device.capabilities()
                    if ecodes.EV_KEY in caps:
                        keys = caps[ecodes.EV_KEY]
                        has_wakeup = KEY_WAKEUP in keys
                        is_ext = is_external_keyboard(device.name)
                        if has_wakeup or is_ext:
                            print(f"  {device.path}: {device.name} (WAKEUP={has_wakeup}, external={is_ext})")

            primary_device = None
            secondary_device = None

            # Find primary device: laptop keyboard with KEY_WAKEUP (skip external)
            for device in devices:
                if is_external_keyboard(device.name):
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    if KEY_WAKEUP in keys or 464 in keys:
                        primary_device = device
                        break

            # Find secondary device: external keyboard with secondary hotkey
            if self._secondary_keycode:
                for device in devices:
                    if not is_external_keyboard(device.name):
                        continue
                    caps = device.capabilities()
                    if ecodes.EV_KEY in caps:
                        keys = caps[ecodes.EV_KEY]
                        # Must have secondary key AND be a full keyboard
                        if self._secondary_keycode in keys and ecodes.KEY_A in keys:
                            secondary_device = device
                            break

            # Fallback for primary: any laptop keyboard
            if not primary_device:
                for device in devices:
                    if is_external_keyboard(device.name):
                        continue
                    caps = device.capabilities()
                    if ecodes.EV_KEY in caps:
                        keys = caps[ecodes.EV_KEY]
                        if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                            if config.DEBUG:
                                print(f"Using fallback laptop keyboard: {device.name}")
                            primary_device = device
                            break

            return primary_device, secondary_device
        except PermissionError:
            print("Permission denied accessing input devices")
            print("Add user to 'input' group: sudo usermod -aG input $USER")
            return None, None
        except Exception as e:
            if config.DEBUG:
                print(f"Error finding keyboard device: {e}")
            return None, None

    def _listen_loop(self):
        """Main event loop for evdev - reads from both primary and secondary devices"""
        try:
            import select
            from evdev import ecodes

            # Build list of devices to monitor
            devices = {}
            if self._device:
                devices[self._device.fd] = self._device
                if config.DEBUG:
                    print(f"Listening for FN key on: {self._device.name}")
            if self._secondary_device:
                devices[self._secondary_device.fd] = self._secondary_device
                if config.DEBUG:
                    print(f"Listening for secondary hotkey on: {self._secondary_device.name}")

            if not devices:
                return

            while self._running:
                # Wait for events from any device (100ms timeout to check _running)
                r, _, _ = select.select(devices.keys(), [], [], 0.1)

                for fd in r:
                    device = devices[fd]
                    for event in device.read():
                        if not self._running:
                            return

                        # Only process key events
                        if event.type != ecodes.EV_KEY:
                            continue

                        # Debug: log key events
                        if config.DEBUG:
                            print(f"Key event from {device.name}: code={event.code} value={event.value}")

                        # Track modifier key states
                        self._update_modifier_state(event.code, event.value)

                        # Determine if this is a trigger key based on which device
                        is_trigger_key = False
                        if device == self._device:
                            # Primary device: check for FN key (KEY_WAKEUP or KEY_FN)
                            is_trigger_key = event.code == KEY_WAKEUP or event.code == 464
                        elif device == self._secondary_device:
                            # Secondary device: check for secondary hotkey
                            is_trigger_key = self._secondary_keycode and event.code == self._secondary_keycode

                        if is_trigger_key:
                            if event.value == 1:  # Key down
                                self._on_fn_key_down()
                            elif event.value == 0:  # Key up
                                self._on_fn_key_up()
                            # value == 2 is key repeat, ignored

        except Exception as e:
            if self._running and config.DEBUG:
                print(f"FN key listener error: {e}")

    def _update_modifier_state(self, keycode: int, value: int):
        """Track modifier key states for mode detection."""
        pressed = value == 1  # 1 = press, 0 = release, 2 = repeat

        if keycode == KEY_SPACE:
            self._space_pressed = pressed
        elif keycode in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
            self._ctrl_pressed = pressed
        elif keycode in (KEY_LEFTSHIFT, KEY_RIGHTSHIFT):
            self._shift_pressed = pressed
        elif keycode in (KEY_LEFTALT, KEY_RIGHTALT):
            self._alt_pressed = pressed

    def _detect_mode(self) -> ProcessingMode:
        """Detect processing mode based on current modifier states.

        Priority order:
        - FN + Ctrl + Shift → TRANSLATE_REFORMAT (Cyan)
        - FN + Ctrl → TRANSLATION (Green)
        - FN + Shift → ACT_ON_TEXT (Magenta)
        - FN + Alt → REFORMULATION (Purple)
        - FN + Space → RAW (Yellow)
        - FN only → BASIC (Orange)
        """
        if self._ctrl_pressed and self._shift_pressed:
            return ProcessingMode.TRANSLATE_REFORMAT
        elif self._ctrl_pressed:
            return ProcessingMode.TRANSLATION
        elif self._shift_pressed:
            return ProcessingMode.ACT_ON_TEXT
        elif self._alt_pressed:
            return ProcessingMode.REFORMULATION
        elif self._space_pressed:
            return ProcessingMode.RAW
        else:
            return ProcessingMode.BASIC

    def _on_fn_key_down(self):
        """Handle FN key press with activation delay

        Behavior depends on mode:
        - BASIC (FN only): PTT with hold (after delay), toggle with double-tap
        - Advanced modes (FN+modifier): Toggle-only (press to start, press to stop)
        """
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.IDLE:
                self._key_down_time = now
                self._current_mode = self._detect_mode()

                # Advanced modes (with modifiers) use toggle-only behavior
                if self._current_mode != ProcessingMode.BASIC:
                    self._state = HotkeyState.RECORDING_TOGGLE
                    self._toggle_first_release = True  # Ignore first release
                    self._trigger_start_recording()
                else:
                    # BASIC mode: Wait for activation delay before starting
                    self._state = HotkeyState.WAITING_ACTIVATION
                    self._start_activation_timer()

            elif self._state == HotkeyState.WAITING_DOUBLE:
                # Second tap within window - enter toggle mode (BASIC mode only)
                if now - self._key_up_time < self._double_tap_window:
                    self._cancel_activation_timer()
                    self._state = HotkeyState.RECORDING_TOGGLE
                    self._toggle_first_release = False  # Double-tap toggle stops on next tap
                    self._trigger_start_recording()
                else:
                    # Window expired, treat as new press
                    self._key_down_time = now
                    self._current_mode = self._detect_mode()
                    if self._current_mode != ProcessingMode.BASIC:
                        self._state = HotkeyState.RECORDING_TOGGLE
                        self._toggle_first_release = True
                        self._trigger_start_recording()
                    else:
                        self._state = HotkeyState.WAITING_ACTIVATION
                        self._start_activation_timer()

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # In toggle mode, second key press stops recording
                self._key_down_time = now
                self._state = HotkeyState.IDLE
                self._trigger_stop_recording()

    def _on_fn_key_up(self):
        """Handle FN key release"""
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.WAITING_ACTIVATION:
                # Key released before activation delay elapsed (tap detected)
                self._cancel_activation_timer()
                self._key_up_time = now
                self._state = HotkeyState.WAITING_DOUBLE
                self._start_double_tap_timer()

            elif self._state == HotkeyState.RECORDING_PTT:
                hold_duration = now - self._key_down_time
                if hold_duration < self._hold_threshold:
                    # Short press (tap) - CANCEL recording, wait for double-tap
                    self._key_up_time = now
                    self._state = HotkeyState.WAITING_DOUBLE
                    self._trigger_cancel_recording()
                    self._start_double_tap_timer()
                else:
                    # Held long enough - stop recording normally (will process)
                    self._state = HotkeyState.IDLE
                    self._trigger_stop_recording()

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # Toggle mode: recording continues until next key press
                # Just track timing, stop happens on next key DOWN
                self._key_up_time = now

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

    def _start_activation_timer(self):
        """Start timer for activation delay before recording starts"""
        self._cancel_activation_timer()  # Cancel any existing timer

        def on_activation_delay_elapsed():
            with self._state_lock:
                if self._state == HotkeyState.WAITING_ACTIVATION:
                    # Delay elapsed while still held - start PTT recording
                    self._state = HotkeyState.RECORDING_PTT
                    self._trigger_start_recording()

        self._activation_timer = threading.Timer(
            self._activation_delay, on_activation_delay_elapsed
        )
        self._activation_timer.daemon = True
        self._activation_timer.start()

    def _cancel_activation_timer(self):
        """Cancel the activation delay timer if running"""
        if self._activation_timer is not None:
            self._activation_timer.cancel()
            self._activation_timer = None

    def _trigger_start_recording(self):
        """Trigger recording start callback with current mode"""
        if self.on_start_recording:
            mode = self._current_mode
            # Run callback in separate thread to not block event handling
            threading.Thread(
                target=lambda: self.on_start_recording(mode), daemon=True
            ).start()

    def _trigger_stop_recording(self):
        """Trigger recording stop callback (will process audio)"""
        if self.on_stop_recording:
            threading.Thread(target=self.on_stop_recording, daemon=True).start()

    def _trigger_cancel_recording(self):
        """Trigger recording cancel callback (discard audio, tap detected)"""
        if self.on_cancel_recording:
            threading.Thread(target=self.on_cancel_recording, daemon=True).start()

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

    @property
    def current_mode(self) -> ProcessingMode:
        """Get the current processing mode"""
        with self._state_lock:
            return self._current_mode
