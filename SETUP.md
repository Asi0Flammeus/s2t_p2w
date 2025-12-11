# Push-to-Write Setup Guide

Voice transcription tool using ElevenLabs STT. Hold a hotkey to record, release to transcribe and type.

## Quick Install

```bash
# 1. Clone and enter directory
cd /path/to/S2T_P2W

# 2. Run install script
chmod +x scripts/install.sh
./scripts/install.sh

# 3. Add your API key
nano .env
# Set: ELEVENLABS_API_KEY=your_key_here

# 4. Start the service
systemctl --user start p2w
```

## Requirements

- Python 3.10+
- PulseAudio or ALSA (for microphone)
- X11 display server
- ElevenLabs API key ([get one here](https://elevenlabs.io/app/settings/api-keys))

### System Dependencies (Debian/Ubuntu)

```bash
sudo apt install python3-venv python3-dev portaudio19-dev
```

### System Dependencies (Arch)

```bash
sudo pacman -S python portaudio
```

## Configuration

Edit `.env` to customize:

```bash
# Required
ELEVENLABS_API_KEY=your_key_here

# Optional
ELEVENLABS_MODEL=scribe_v1      # STT model
HOTKEY_MODIFIER=alt             # alt, ctrl, shift
HOTKEY_KEY=t                    # any key
LANGUAGE=auto                   # auto, en, fr, de, etc.
MIC_DEVICE=auto                 # auto or device index
DEBUG=false                     # show debug output
```

## Usage

| Action | Result |
|--------|--------|
| Hold `Alt+T` | Start recording (visualizer appears) |
| Release `Alt+T` | Stop recording, transcribe, type text |
| `Ctrl+C` | Stop the service |

## Service Management

```bash
# Start/stop
systemctl --user start p2w
systemctl --user stop p2w

# View status
systemctl --user status p2w

# View logs
journalctl --user -u p2w -f

# Disable auto-start
systemctl --user disable p2w

# Re-enable auto-start
systemctl --user enable p2w
```

## Manual Run (without service)

```bash
cd /path/to/S2T_P2W
source .venv/bin/activate
python src/main.py
```

## Troubleshooting

### No microphone detected

```bash
# List audio devices
arecord -l

# Set specific device in .env
MIC_DEVICE=1
```

### Service won't start

```bash
# Check logs
journalctl --user -u p2w -n 50

# Verify display
echo $DISPLAY  # Should be :0 or :1
```

### Visualizer not showing

- Ensure X11 is running (not Wayland)
- Check if pygame is installed: `pip show pygame`

### Permission denied for input

```bash
# Add user to input group
sudo usermod -aG input $USER
# Log out and back in
```

## Uninstall

```bash
systemctl --user stop p2w
systemctl --user disable p2w
rm ~/.config/systemd/user/p2w.service
systemctl --user daemon-reload
```
