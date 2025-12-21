# Changelog

All notable changes to Dicton will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-12-21

### Added

- **ElevenLabs Speech-to-Text Integration**
  - Real-time transcription using ElevenLabs Scribe API
  - Automatic language detection
  - High-quality transcription with noise filtering

- **Cross-Platform Support**
  - Linux (X11/Wayland) with xdotool text insertion
  - Windows with pyautogui fallback
  - macOS support via pynput

- **Audio Visualizers**
  - Pygame-based circular donut visualizer (default)
  - VisPy-based GPU-accelerated visualizer (optional)
  - Multiple visual styles: toric, classic, legacy, minimalistic, terminal
  - Configurable colors and position

- **Hotkey System**
  - Configurable hotkey (default: Alt+G)
  - Toggle-based recording (press to start, press to stop)
  - Cross-platform keyboard handling via pynput

- **Desktop Notifications**
  - Recording status notifications
  - Transcription completion alerts
  - Cross-platform notification support (notify-send, plyer)

- **Configuration**
  - Environment-based configuration via `.env` file
  - Configurable microphone device selection
  - Adjustable audio parameters (sample rate, chunk size)

- **Installation Options**
  - pip installable package (`pip install -e .`)
  - System-wide installation script (`install.sh`)
  - Systemd service support for auto-start

### Technical Details

- Python 3.10+ required
- Uses PyAudio for audio capture
- Supports both pygame and VisPy visualizer backends
- MIT licensed

[1.0.0]: https://github.com/asi0flammern/dicton/releases/tag/v1.0.0
