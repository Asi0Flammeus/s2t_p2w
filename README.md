# Push-to-Write (P2W) 🎤

A fast voice-to-text application for Linux that transcribes your speech directly at the cursor position. Press `Alt+T` to start recording, press again to stop and transcribe!

## ✨ Features

- **🚀 ElevenLabs STT**: Fast, accurate transcription using ElevenLabs Speech-to-Text API
- **🎯 System-wide**: Works in any application where you can type
- **🔊 Audio Visualizer**: Elegant circular waveform display while recording
- **🌍 Multilingual**: Supports auto language detection and manual language selection
- **🔔 Notifications**: Desktop notifications for recording status
- **🔧 Configurable**: Customize hotkeys, language, and microphone settings
- **⚡ Toggle Recording**: Press hotkey to start, press again to stop
- **🎨 Visual Feedback**: Animated donut visualizer shows audio levels in real-time

## 📋 Requirements

- Python 3.10 or higher
- Ubuntu/Debian or Arch Linux
- PulseAudio or ALSA audio system
- X11 window system (for keyboard automation and visualizer)
- ElevenLabs API key ([get one here](https://elevenlabs.io/app/settings/api-keys))

## 🚀 Installation

### Quick Install (Local)

```bash
# Clone the repository
git clone https://github.com/yourusername/push-to-write.git
cd push-to-write

# Run the install script
chmod +x scripts/install.sh
./scripts/install.sh

# Add your API key
nano .env
# Set: ELEVENLABS_API_KEY=your_key_here

# Start the service
systemctl --user start p2w
```

### System-wide Install (with sudo)

```bash
# Install system-wide to /opt/p2w
sudo ./install.sh install

# Edit configuration
sudo nano /opt/p2w/.env

# Run manually
p2w

# Or enable as systemd service
systemctl --user enable p2w
systemctl --user start p2w
```

### System Dependencies

**Debian/Ubuntu:**
```bash
sudo apt install python3-venv python3-dev portaudio19-dev xdotool libnotify-bin
```

**Arch Linux:**
```bash
sudo pacman -S python portaudio xdotool libnotify
```

## 🎮 Usage

### Starting the Application

**Option 1: As a Service (recommended)**
```bash
systemctl --user start p2w
```

**Option 2: Command Line**
```bash
p2w
```

**Option 3: Direct**
```bash
cd /path/to/push-to-write
source .venv/bin/activate
python src/main.py
```

### Recording Workflow

1. Start the application
2. Press `Alt+T` to **start recording** (visualizer appears)
3. Speak clearly into your microphone
4. Press `Alt+T` again to **stop recording**
5. Wait briefly for transcription
6. Text appears at your cursor position!

| Action | Result |
|--------|--------|
| Press `Alt+T` | Start recording (visualizer shows) |
| Press `Alt+T` again | Stop recording, transcribe, insert text |
| `Ctrl+C` | Quit the application |

## ⚙️ Configuration

Edit the `.env` file to customize:

```bash
# ElevenLabs API (required)
ELEVENLABS_API_KEY=your_elevenlabs_key_here

# ElevenLabs STT model
ELEVENLABS_MODEL=scribe_v1

# Keyboard shortcut
HOTKEY_MODIFIER=alt    # Options: alt, ctrl
HOTKEY_KEY=t           # Any key

# Language: auto, en, fr, de, es, etc. (ISO-639-1 codes)
# Set to "auto" for automatic language detection
LANGUAGE=auto

# Microphone: auto or device index number
# Run with DEBUG=true to see available devices
MIC_DEVICE=auto

# Local fallback model (only used if no API key)
WHISPER_MODEL=base
USE_CUDA=false

# Debug output
DEBUG=false
```

### Getting Your API Key

1. Sign up at [ElevenLabs](https://elevenlabs.io/)
2. Go to [API Settings](https://elevenlabs.io/app/settings/api-keys)
3. Create a new API key
4. Add it to your `.env` file

## 🏗️ Project Structure

```
push-to-write/
├── src/
│   ├── main.py                      # Main application entry point
│   ├── config.py                    # Configuration management
│   ├── speech_recognition_engine.py # ElevenLabs STT integration
│   ├── keyboard_handler.py          # Hotkey detection and text insertion
│   ├── visualizer.py                # Circular audio visualizer (pygame)
│   └── ui_feedback.py               # Desktop notifications
├── scripts/
│   ├── install.sh                   # Local installation script
│   └── p2w.service                  # Systemd service template
├── assets/
│   └── icon.png                     # Application icon
├── .env.example                     # Configuration template
├── requirements.txt                 # Python dependencies
├── install.sh                       # System-wide installer
├── SETUP.md                         # Detailed setup guide
└── README.md                        # This file
```

## 📦 Dependencies

Core dependencies (from `requirements.txt`):

| Package | Purpose |
|---------|---------|
| `elevenlabs` | Speech-to-text API client |
| `pyaudio` | Audio capture |
| `pynput` | Keyboard hotkey detection |
| `pygame` | Audio visualizer |
| `python-dotenv` | Environment configuration |
| `numpy` | Audio processing |

## 🔧 Service Management

```bash
# Start the service
systemctl --user start p2w

# Stop the service
systemctl --user stop p2w

# Enable auto-start on login
systemctl --user enable p2w

# Disable auto-start
systemctl --user disable p2w

# View status
systemctl --user status p2w

# View logs
journalctl --user -u p2w -f
```

## 🔧 Troubleshooting

### No Microphone Detected

```bash
# List available audio devices
arecord -l

# Or check with PulseAudio
pactl list sources short

# Set specific device in .env
MIC_DEVICE=1
```

### Visualizer Not Showing

- Ensure X11 is running (not Wayland): `echo $XDG_SESSION_TYPE`
- Check pygame installation: `.venv/bin/pip show pygame`
- Try running with `DEBUG=true` for more info

### Keyboard Shortcuts Not Working

- Ensure you're running X11 (not Wayland)
- Check if another application uses `Alt+T`
- Try a different hotkey in `.env`

### Permission Denied for Input

```bash
# Add user to input group
sudo usermod -aG input $USER
# Log out and back in
```

### Service Won't Start

```bash
# Check logs
journalctl --user -u p2w -n 50

# Verify display is set
echo $DISPLAY  # Should be :0 or :1
```

### ALSA/JACK Warnings

These are harmless! PyAudio scans multiple backends. The warnings are suppressed automatically.

## 🗑️ Uninstall

**Local installation:**
```bash
systemctl --user stop p2w
systemctl --user disable p2w
rm ~/.config/systemd/user/p2w.service
systemctl --user daemon-reload
```

**System-wide installation:**
```bash
sudo ./install.sh uninstall
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests.

## 📄 License

MIT License - feel free to use this project however you'd like!

## 🙏 Acknowledgments

- [ElevenLabs](https://elevenlabs.io/) for the speech-to-text API
- [pynput](https://github.com/moses-palmer/pynput) for keyboard handling
- [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) for audio capture
- [Pygame](https://www.pygame.org/) for the visualizer

## 💡 Tips

- Speak clearly and at a normal pace for best results
- The visualizer shows when audio is being captured
- Works best in quiet environments
- The first transcription may be slightly slower (API warmup)
- Keep recordings under 30 seconds for faster processing
