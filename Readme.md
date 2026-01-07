# Picorder - a Raspberry Pi TFT Audio Recorder

A Raspberry Pi menu system for audio recording with manual and automatic modes, compatible with Waveshare 3.5-inch TFT touch display.

## Hardware Compatibility ##

This project is compatible with the **Waveshare 3.5-inch Raspberry Pi LCD** display. Built for Raspberry Pi devices. You can use device you want for recording. 

## Setup ##

1. **Install LCD-Show library**

   Download and install the LCD-Show library from Waveshare:
   ```
   wget http://www.waveshare.com/w/upload/4/4b/LCD-show-161112.tar.gz
   tar xvf LCD-show-*.tar.gz
   cd LCD-show-*
   sudo ./LCD35-show
   ```

   Follow the manufacturer's guide for complete setup: [Waveshare 3.5inch RPi LCD Wiki](http://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A))

2. **Install this project**

   Clone this repository:
   ```bash
   git clone https://github.com/janiluuk/picorder.git /home/pi/picorder
   cd /home/pi/picorder
   pip install -r requirements.txt
   ```

3. **Run install script**

   To install and enable auto-start:
   ```bash
   sudo ./install.sh
   ```

   To uninstall:
   ```bash
   sudo ./install.sh uninstall
   ```

## Features ##

- **Automatic Recording**: Records audio when jack is plugged in using silentjack
- **Manual Recording**: Start/stop recording manually with button press
- **Recording Status**: Always displays recording status and duration
- **Audio Device Selection**: Choose which audio input device to use
- **Disk Space Monitoring**: View available disk space
- **Screen Management**: Screen turns off after 30 seconds of inactivity, stays on during recording
- **Smart File Naming**: Recordings are automatically named with date, time, and duration (e.g., `recording_20240115_143022_05m32s.wav`)

## Recordings ##

All recordings are stored in `/home/pi/recordings/` with filenames formatted as:
- `recording_YYYYMMDD_HHMMSS_DURATION.wav`
- Example: `recording_20240115_143022_05m32s.wav` (recorded on Jan 15, 2024 at 14:30:22 for 5 minutes 32 seconds)

## Testing ##

Run the unit tests with:
```bash
python3 -m unittest test_menu_settings -v
```
