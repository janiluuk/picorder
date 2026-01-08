#!/bin/bash
##############################################
##                                          ##
##  Install/Uninstall Script                ##
##  Installs or uninstalls the menu         ##
##  to start automatically on boot          ##
##                                          ##
##############################################

MENUDIR="/home/pi/picorder"
SCRIPT="$MENUDIR/menu.sh"
CRON_ENTRY="@reboot sh $SCRIPT >/home/pi/logs/cronlog 2>&1"
BASH_LOGOUT_ENTRY="if [ \"\$SHLVL\" = 1 ]; then\n    sudo $SCRIPT\nfi"

if [ "$1" = "uninstall" ]; then
    echo "Uninstalling..."
    
    # Remove cron job
    sudo crontab -l 2>/dev/null | grep -v "$CRON_ENTRY" | sudo crontab -
    echo "Removed cron job"
    
    # Remove from bash_logout
    if [ -f ~/.bash_logout ]; then
        sed -i '/picorder/d' ~/.bash_logout
        sed -i '/menu.sh/d' ~/.bash_logout
        echo "Removed from ~/.bash_logout"
    fi
    
    echo "Uninstall complete!"
    exit 0
fi

echo "Installing..."

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y build-essential libasound2-dev libjack-dev libjack0 jackd python3-pip

# Install Python dependencies
echo "Installing Python dependencies..."
# Install system-wide since menu.sh runs with sudo
sudo pip3 install -r "$MENUDIR/requirements.txt" || {
    echo "Failed to install from requirements.txt, trying pygame directly..."
    sudo pip3 install "pygame>=2.0.0" || {
        echo "Warning: Failed to install pygame. You may need to install it manually with: sudo pip3 install pygame"
    }
}

# Install silentjack
echo "Installing silentjack..."
SILENTJACK_DIR="/tmp/silentjack"
SILENTJACK_URL="https://www.aelius.com/njh/silentjack/silentjack-0.3.tar.gz"
SILENTJACK_TAR="/tmp/silentjack-0.3.tar.gz"

# Download silentjack
if [ ! -f "$SILENTJACK_TAR" ]; then
    echo "Downloading silentjack..."
    wget -O "$SILENTJACK_TAR" "$SILENTJACK_URL" || {
        echo "Failed to download silentjack. Please check your internet connection."
        exit 1
    }
fi

# Extract and compile
if [ -d "$SILENTJACK_DIR" ]; then
    rm -rf "$SILENTJACK_DIR"
fi
mkdir -p "$SILENTJACK_DIR"
tar -xzf "$SILENTJACK_TAR" -C "$SILENTJACK_DIR" --strip-components=1

cd "$SILENTJACK_DIR"
echo "Configuring silentjack..."
./configure || {
    echo "Configuration failed. Trying with default settings..."
    # Try to compile anyway
}

echo "Compiling silentjack..."
make || {
    echo "Compilation failed. Please check dependencies."
    exit 1
}

echo "Installing silentjack..."
sudo make install || {
    echo "Installation failed. Trying to copy binary manually..."
    sudo cp silentjack /usr/local/bin/ || {
        echo "Failed to install silentjack binary."
        exit 1
    }
}

echo "silentjack installed successfully!"

# Create logs and recordings directories
mkdir -p /home/pi/logs
mkdir -p /home/pi/recordings
chmod 755 /home/pi/recordings
echo "Created recordings directory: /home/pi/recordings"

# Make scripts executable
chmod +x "$MENUDIR"/*.sh
chmod +x "$MENUDIR"/*.py

# Add cron job
(sudo crontab -l 2>/dev/null; echo "$CRON_ENTRY") | sudo crontab -
echo "Added cron job for auto-start on boot"

# Add to bash_logout
if [ ! -f ~/.bash_logout ]; then
    touch ~/.bash_logout
fi

if ! grep -q "menu.sh" ~/.bash_logout; then
    echo -e "$BASH_LOGOUT_ENTRY" >> ~/.bash_logout
    echo "Added to ~/.bash_logout"
else
    echo "Already present in ~/.bash_logout"
fi

echo "Installation complete!"
echo "The menu will start automatically on boot and when logging out."

