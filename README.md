# Push-to-Write (P2W) 🎤

A lightweight, **offline-capable** voice-to-text application for Linux that transcribes your speech directly at the cursor position. Simply press `Alt+T`, speak, and watch your words appear instantly!

## ✨ Features

- **🔌 Offline Mode**: Works completely offline using OpenAI Whisper
- **🌍 Multilingual**: Supports English and French with auto-detection
- **⚡ Real-time**: Fast transcription with automatic silence detection
- **🎯 System-wide**: Works in any application where you can type
- **🔧 Configurable**: Customize hotkeys, language, and audio settings
- **💻 System Tray**: Convenient system tray integration with quick settings
- **🔔 Notifications**: Visual feedback for recording status

## 📋 Requirements

- Ubuntu/Debian-based Linux distribution
- Python 3.8 or higher
- PulseAudio or ALSA audio system
- X11 window system (for keyboard/mouse automation)

## 🚀 Installation

### Quick Install

```bash
git clone https://github.com/yourusername/push-to-write.git
cd push-to-write
chmod +x install.sh
./install.sh
```

The installer will:
1. Install system dependencies (portaudio, ffmpeg, etc.)
2. Create a Python virtual environment
3. Install Python packages including Whisper
4. Download the offline speech model
5. Create desktop and command-line launchers

### Manual Installation

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev \
    portaudio19-dev python3-pyaudio ffmpeg libportaudio2 \
    libasound2-dev xclip xdotool python3-tk

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt

# Copy configuration
cp .env.example .env

# Run the application
python src/main.py
```

## 🎮 Usage

### Starting the Application

**Option 1: Command Line**
```bash
p2w
```

**Option 2: Desktop**
Search for "Push-to-Write" in your applications menu

**Option 3: Direct**
```bash
cd /path/to/push-to-write
./venv/bin/python src/main.py
```

### Using Push-to-Write

1. Start the application
2. Press `Alt+T` (default hotkey)
3. Speak clearly into your microphone
4. Stop speaking (1 second of silence ends recording)
5. Text appears at your cursor position!

### System Tray Menu

Right-click the system tray icon to:
- Change language (Auto/English/French)
- View current hotkey
- Quit application

## ⚙️ Configuration

Edit the `.env` file to customize:

```bash
# Language settings
DEFAULT_LANGUAGE=auto  # Options: en, fr, auto

# Speech recognition engine
SPEECH_ENGINE=whisper  # Offline mode
WHISPER_MODEL=base     # Options: tiny, base, small, medium, large

# Keyboard shortcut
HOTKEY_MODIFIER=alt    # Options: alt, ctrl, shift
HOTKEY_KEY=t

# Audio settings
AUDIO_TIMEOUT=10       # Maximum recording time in seconds
SILENCE_DURATION=1.0   # Seconds of silence to stop recording

# UI settings
SHOW_TRAY_ICON=true
SHOW_NOTIFICATIONS=true
```

### Whisper Model Sizes

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| tiny | 39 MB | Fastest | Good |
| base | 74 MB | Fast | Better |
| small | 244 MB | Medium | Good |
| medium | 769 MB | Slow | Best |
| large | 1550 MB | Slowest | Excellent |

## 🔧 Troubleshooting

### No Audio Input Detected

```bash
# Check audio devices
pactl list sources

# Test microphone
arecord -d 5 test.wav && aplay test.wav
```

### Permission Errors

```bash
# Add user to audio group
sudo usermod -a -G audio $USER
# Log out and back in
```

### Whisper Model Download Issues

```bash
# Manually download model
python3 -c "import whisper; whisper.load_model('base')"
```

### Keyboard Shortcuts Not Working

- Ensure you're running X11 (not Wayland)
- Check if another application is using the same hotkey
- Try running with sudo (for testing only)

## 🏗️ Project Structure

```
push-to-write/
├── src/
│   ├── main.py                 # Main application
│   ├── config.py               # Configuration management
│   ├── speech_recognition_engine.py  # Whisper integration
│   ├── keyboard_handler.py    # Hotkey and text insertion
│   └── ui_feedback.py         # System tray and notifications
├── models/                     # Whisper model cache
├── .env                        # User configuration
├── requirements.txt            # Python dependencies
├── install.sh                  # Installation script
└── README.md                   # Documentation
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests.

## 📄 License

MIT License - feel free to use this project however you'd like!

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for offline speech recognition
- [pynput](https://github.com/moses-palmer/pynput) for keyboard handling
- [pyaudio](https://people.csail.mit.edu/hubert/pyaudio/) for audio capture

## 💡 Tips

- For faster transcription, use the `tiny` or `base` model
- For better accuracy, use the `small` or `medium` model
- The first run will download the Whisper model (one-time download)
- Works best in quiet environments
- Speak clearly and at a normal pace