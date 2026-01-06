"""Wayland Context Detector for Dicton

Provides context detection on Wayland compositors using compositor-specific methods:
- GNOME: D-Bus extensions (Window Calls Extended or Focused Window D-Bus)
- Sway/i3: swaymsg -t get_tree JSON parsing
- KDE: D-Bus KWin interface
- Hyprland: hyprctl activewindow JSON parsing

Falls back gracefully when compositor-specific methods are unavailable.
"""

import json
import logging
import subprocess

from .context_detector import (
    ContextDetector,
    TerminalInfo,
    WidgetInfo,
    WindowInfo,
)
from .platform_utils import WAYLAND_COMPOSITOR

logger = logging.getLogger(__name__)


# =============================================================================
# Wayland Context Detector
# =============================================================================


class WaylandContextDetector(ContextDetector):
    """Context detector for Wayland display servers.

    Supports multiple compositors with fallback chain:
    1. GNOME: D-Bus extension (requires installation)
    2. Sway/i3: Native swaymsg support
    3. Hyprland: Native hyprctl support
    4. KDE: D-Bus KWin interface
    """

    def __init__(self):
        self._compositor = WAYLAND_COMPOSITOR
        self._gnome_extension_checked = False
        self._gnome_extension_available = False

    def get_active_window(self) -> WindowInfo | None:
        """Get active window info using compositor-specific method."""
        if self._compositor == "gnome":
            return self._get_gnome_window()
        elif self._compositor == "sway":
            return self._get_sway_window()
        elif self._compositor == "hyprland":
            return self._get_hyprland_window()
        elif self._compositor == "kde":
            return self._get_kde_window()
        else:
            logger.debug(f"Unknown Wayland compositor: {self._compositor}")
            return None

    def _get_gnome_window(self) -> WindowInfo | None:
        """Get active window via GNOME D-Bus extension.

        Requires one of these extensions:
        - Focused Window D-Bus (org.gnome.Shell.Extensions.FocusedWindow)
        - Window Calls Extended (org.gnome.Shell.Extensions.WindowCallsExtended)
        """
        # Try Focused Window D-Bus extension first
        try:
            import dbus

            bus = dbus.SessionBus()

            # Method 1: Focused Window D-Bus extension
            try:
                proxy = bus.get_object(
                    "org.gnome.Shell",
                    "/org/gnome/Shell/Extensions/FocusedWindow",
                )
                iface = dbus.Interface(proxy, "org.gnome.Shell.Extensions.FocusedWindow")
                result = iface.Get()

                if result:
                    data = json.loads(str(result))
                    return WindowInfo(
                        wm_class=data.get("wm_class", ""),
                        title=data.get("title", ""),
                        pid=data.get("pid"),
                    )
            except dbus.exceptions.DBusException:
                pass  # Extension not available

            # Method 2: Window Calls Extended
            try:
                proxy = bus.get_object(
                    "org.gnome.Shell",
                    "/org/gnome/Shell/Extensions/WindowsExt",
                )
                iface = dbus.Interface(proxy, "org.gnome.Shell.Extensions.WindowsExt")
                result = iface.FocusWindow()

                if result:
                    data = json.loads(str(result))
                    return WindowInfo(
                        wm_class=data.get("wm_class", ""),
                        title=data.get("title", ""),
                        pid=data.get("pid"),
                    )
            except dbus.exceptions.DBusException:
                pass  # Extension not available

            logger.warning(
                "GNOME context detection requires a D-Bus extension. "
                "Install 'Focused Window D-Bus' from extensions.gnome.org"
            )
            return None

        except ImportError:
            logger.warning("dbus-python not installed - GNOME context detection unavailable")
            return None
        except Exception as e:
            logger.debug(f"GNOME window detection failed: {e}")
            return None

    def _get_sway_window(self) -> WindowInfo | None:
        """Get active window via swaymsg."""
        try:
            result = subprocess.run(
                ["swaymsg", "-t", "get_tree"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode != 0:
                return None

            tree = json.loads(result.stdout)
            focused = self._find_focused_sway(tree)

            if focused:
                app_id = focused.get("app_id", "")
                window_props = focused.get("window_properties", {})
                wm_class = window_props.get("class", app_id) or app_id

                return WindowInfo(
                    wm_class=wm_class,
                    title=focused.get("name", ""),
                    pid=focused.get("pid"),
                    geometry=self._get_sway_geometry(focused),
                )

        except FileNotFoundError:
            logger.debug("swaymsg not found")
        except subprocess.TimeoutExpired:
            logger.debug("swaymsg timeout")
        except Exception as e:
            logger.debug(f"Sway window detection failed: {e}")

        return None

    def _find_focused_sway(self, node: dict) -> dict | None:
        """Recursively find focused node in Sway tree."""
        if node.get("focused"):
            return node

        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            result = self._find_focused_sway(child)
            if result:
                return result

        return None

    def _get_sway_geometry(self, node: dict) -> tuple[int, int, int, int] | None:
        """Extract geometry from Sway node."""
        rect = node.get("rect")
        if rect:
            return (rect.get("x", 0), rect.get("y", 0), rect.get("width", 0), rect.get("height", 0))
        return None

    def _get_hyprland_window(self) -> WindowInfo | None:
        """Get active window via hyprctl."""
        try:
            result = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)

            return WindowInfo(
                wm_class=data.get("class", ""),
                title=data.get("title", ""),
                pid=data.get("pid"),
                geometry=(
                    data.get("at", [0, 0])[0],
                    data.get("at", [0, 0])[1],
                    data.get("size", [0, 0])[0],
                    data.get("size", [0, 0])[1],
                )
                if data.get("at") and data.get("size")
                else None,
            )

        except FileNotFoundError:
            logger.debug("hyprctl not found")
        except subprocess.TimeoutExpired:
            logger.debug("hyprctl timeout")
        except Exception as e:
            logger.debug(f"Hyprland window detection failed: {e}")

        return None

    def _get_kde_window(self) -> WindowInfo | None:
        """Get active window via KDE/KWin D-Bus interface."""
        try:
            import dbus

            bus = dbus.SessionBus()

            # KWin D-Bus interface for active window
            proxy = bus.get_object(
                "org.kde.KWin",
                "/KWin",
            )
            iface = dbus.Interface(proxy, "org.kde.KWin")

            # Get active window ID
            # Note: KWin's D-Bus API varies by version
            # This uses the scripting interface
            script = """
            var w = workspace.activeClient;
            print(JSON.stringify({
                "caption": w.caption,
                "resourceClass": w.resourceClass,
                "pid": w.pid
            }));
            """

            try:
                result = iface.evaluateScript(script)
                if result:
                    data = json.loads(result)
                    return WindowInfo(
                        wm_class=data.get("resourceClass", ""),
                        title=data.get("caption", ""),
                        pid=data.get("pid"),
                    )
            except (dbus.exceptions.DBusException, json.JSONDecodeError):
                pass

            logger.debug("KDE window detection via D-Bus failed")
            return None

        except ImportError:
            logger.warning("dbus-python not installed - KDE context detection unavailable")
            return None
        except Exception as e:
            logger.debug(f"KDE window detection failed: {e}")
            return None

    def get_widget_focus(self) -> WidgetInfo | None:
        """Get focused widget info via AT-SPI.

        AT-SPI works on Wayland when the AT-SPI D-Bus daemon is running.
        Requires python3-pyatspi system package.
        """
        try:
            import pyatspi

            # Get the desktop (top-level accessible)
            desktop = pyatspi.Registry.getDesktop(0)
            if not desktop:
                return None

            # Find focused application
            for app in desktop:
                if not app:
                    continue

                for window in app:
                    if not window:
                        continue

                    focused = self._find_focused_widget(window, pyatspi)
                    if focused:
                        role = pyatspi.getRoleName(focused)
                        return WidgetInfo(
                            role=role,
                            name=focused.name or "",
                            application=app.name or "",
                        )

        except ImportError:
            logger.debug("pyatspi not available - widget focus detection disabled")
        except Exception as e:
            logger.debug(f"AT-SPI widget focus detection failed: {e}")

        return None

    def _find_focused_widget(self, accessible, pyatspi) -> object | None:
        """Recursively find focused widget in accessibility tree."""
        try:
            state_set = accessible.getState()
            if state_set.contains(pyatspi.STATE_FOCUSED):
                return accessible

            for child in accessible:
                if not child:
                    continue
                result = self._find_focused_widget(child, pyatspi)
                if result:
                    return result
        except Exception:
            pass

        return None

    def get_terminal_context(self) -> TerminalInfo | None:
        """Get terminal context via psutil and shell detection.

        Works similarly to X11 implementation since psutil is
        display-server agnostic.
        """
        window = self.get_active_window()
        if not window or not window.pid:
            return None

        try:
            import psutil

            term_proc = psutil.Process(window.pid)

            shell_proc = None
            shell_name = ""
            cwd = ""

            for child in term_proc.children(recursive=True):
                try:
                    name = child.name().lower()
                    if name in ("bash", "zsh", "fish", "sh", "tcsh", "csh", "dash"):
                        shell_proc = child
                        shell_name = name
                        cwd = child.cwd()
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            running_cmd = None
            if shell_proc:
                try:
                    for child in shell_proc.children():
                        cmdline = child.cmdline()
                        if cmdline:
                            running_cmd = " ".join(cmdline[:3])
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Check for tmux/screen
            session_type = None
            session_name = None
            pane_id = None

            tmux_info = self._get_tmux_info()
            if tmux_info:
                session_type = "tmux"
                session_name = tmux_info.get("session")
                pane_id = tmux_info.get("pane")
                if tmux_info.get("cwd"):
                    cwd = tmux_info["cwd"]

            return TerminalInfo(
                shell=shell_name,
                cwd=cwd,
                running_command=running_cmd,
                session_type=session_type,
                session_name=session_name,
                pane_id=pane_id,
            )

        except ImportError:
            logger.debug("psutil not available - terminal context unavailable")
        except Exception as e:
            logger.debug(f"Terminal context detection failed: {e}")

        return None

    def _get_tmux_info(self) -> dict | None:
        """Get tmux session info if inside tmux."""
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}:#{window_index}.#{pane_index}"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(":")
                if len(parts) >= 2:
                    session = parts[0]
                    pane = parts[1]

                    cwd_result = subprocess.run(
                        ["tmux", "display-message", "-p", "#{pane_current_path}"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    cwd = cwd_result.stdout.strip() if cwd_result.returncode == 0 else ""

                    return {"session": session, "pane": pane, "cwd": cwd}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None
