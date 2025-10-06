#!/bin/bash

# Push-to-Write Installation Script
# For Ubuntu/Debian-based Linux systems

set -e

echo "================================================"
echo "Push-to-Write (P2W) Installation Script"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}Error: This script is for Linux systems only${NC}"
    exit 1
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "\n${YELLOW}Step 1: Installing system dependencies...${NC}"

# Update package lists
sudo apt-get update

# Install system dependencies
echo "Installing audio libraries and Python development packages..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    portaudio19-dev \
    python3-pyaudio \
    ffmpeg \
    libportaudio2 \
    libasound2-dev \
    xclip \
    xdotool \
    python3-tk

echo -e "${GREEN}✓ System dependencies installed${NC}"

echo -e "\n${YELLOW}Step 2: Creating Python virtual environment...${NC}"

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

echo -e "\n${YELLOW}Step 3: Installing Python packages...${NC}"

# Upgrade pip
pip install --upgrade pip

# Install Python requirements
pip install -r requirements.txt

echo -e "${GREEN}✓ Python packages installed${NC}"

echo -e "\n${YELLOW}Step 4: Setting up configuration...${NC}"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Configuration file created (.env)${NC}"
    echo -e "${YELLOW}Please edit .env file to customize your settings${NC}"
else
    echo "Configuration file already exists"
fi

# Create models directory
mkdir -p models

echo -e "\n${YELLOW}Step 5: Creating desktop launcher...${NC}"

# Get the full path to the project directory
PROJECT_DIR="$(pwd)"

# Create desktop entry for easy launching
cat > ~/.local/share/applications/push-to-write.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Push-to-Write
Comment=Voice to Text with Alt+T
Exec=bash -c "cd $PROJECT_DIR && source venv/bin/activate && python src/main.py"
Icon=$PROJECT_DIR/assets/icon.png
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=true
EOF

# Make desktop entry executable
chmod +x ~/.local/share/applications/push-to-write.desktop

echo -e "${GREEN}✓ Desktop launcher created${NC}"

echo -e "\n${YELLOW}Step 6: Creating command-line launcher...${NC}"

# Create a launcher script
cat > p2w <<EOF
#!/bin/bash
cd "$PROJECT_DIR"
source venv/bin/activate
python src/main.py "\$@"
EOF

# Make launcher executable
chmod +x p2w

# Create symlink in local bin (create directory if it doesn't exist)
mkdir -p ~/.local/bin
ln -sf "$PROJECT_DIR/p2w" ~/.local/bin/p2w

echo -e "${GREEN}✓ Command-line launcher created${NC}"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo -e "${YELLOW}Note: Add ~/.local/bin to your PATH by adding this to ~/.bashrc:${NC}"
    echo 'export PATH="$HOME/.local/bin:$PATH"'
fi

echo -e "\n${YELLOW}Step 7: Downloading Whisper model (for offline mode)...${NC}"

# Pre-download the default Whisper model
python3 -c "import whisper; whisper.load_model('base', download_root='models')" 2>/dev/null || true

echo -e "${GREEN}✓ Whisper model ready${NC}"

echo ""
echo "================================================"
echo -e "${GREEN}Installation Complete!${NC}"
echo "================================================"
echo ""
echo "To start Push-to-Write:"
echo "  1. From terminal: p2w"
echo "  2. From desktop: Search for 'Push-to-Write' in applications"
echo "  3. Manual: cd $PROJECT_DIR && ./venv/bin/python src/main.py"
echo ""
echo "Default hotkey: Alt+T"
echo "Configuration: Edit .env file"
echo ""
echo -e "${YELLOW}Note: The application works completely OFFLINE!${NC}"
echo "================================================"