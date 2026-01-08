# Picorder - a Raspberry Pi TFT Audio Recorder

A Raspberry Pi menu system for audio recording with manual and automatic modes, compatible with Waveshare 3.5-inch TFT touch display. Also works on Linux desktop systems using pygame with X11.

## Hardware Compatibility ##

This project is compatible with the **Waveshare 3.5-inch Raspberry Pi LCD** display. Built for Raspberry Pi devices. You can use device you want for recording. 

**Desktop Support:** The application can also run on Linux desktop systems using pygame with X11 display. Use the `menu_desktop.sh` script to launch it on your desktop. 

## Setup ##

1. **Install LCD-Show library**

   Download and install the LCD-Show library:
   ```bash
   git clone https://github.com/goodtft/LCD-show.git
   chmod -R 755 LCD-show/LCD35-show
   cd LCD-show/
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

## Desktop Usage ##

To run the menu on a Linux desktop system:

1. **Install dependencies:**
   ```bash
   pip3 install pygame
   ```

2. **Run the desktop launcher:**
   ```bash
   ./menu_desktop.sh
   ```

   The application will:
   - Automatically detect it's running on desktop (not Raspberry Pi)
   - Use X11 display instead of framebuffer
   - Use mouse input instead of touchscreen
   - Store recordings in `~/recordings/` instead of `/home/pi/recordings/`
   - Store config in `~/picorder/config.json` instead of `/home/pi/picorder/config.json`
   - Disable screen timeout (no GPIO backlight control on desktop)

## Features ##

- **Automatic Recording**: Records audio when jack is plugged in using silentjack
- **Manual Recording**: Start/stop recording manually with button press
- **Recording Status**: Always displays recording status and duration
- **Audio Device Selection**: Choose which audio input device to use
- **Disk Space Monitoring**: View available disk space
- **Screen Management**: Screen turns off after 30 seconds of inactivity, stays on during recording
- **Smart File Naming**: Recordings are automatically named with date, time, and duration (e.g., `recording_20240115_143022_05m32s.wav`)

## Usage ##

### Main Menu (Recording)

The main menu is displayed when you start the application. The screen shows:

- **Top Row**: Current recording status and duration (e.g., "Manual: 05:32" or "Not Recording")
- **Row 1**: Auto-record status ("Auto: ON" or "Auto: OFF")
- **Row 2**: Record button ("Record" or "Stop" depending on state)

**Button Functions:**
1. **Button 1**: Toggle auto-record ON/OFF (only works if valid audio device is selected)
2. **Button 2**: Start/stop manual recording
3. **Button 3**: Stop any active recording
4. **Button 4**: Open Settings menu
5. **Button 5**: Turn screen off (enters sleep mode)
6. **Button 6**: (Not used in main menu)

**Auto-Record Mode:**
- When enabled, the device automatically starts recording when you plug in a 3.5mm audio jack
- Recording stops automatically when you unplug the jack
- Auto-record can only be enabled if a valid audio input device is configured

**Manual Recording:**
- Press Button 2 to start recording manually
- Press Button 2 again (or Button 3) to stop recording
- Manual recordings are saved with duration in the filename

### Settings Menu

Access the settings menu by pressing Button 4 from the main menu.

**Button Functions:**
1. **Button 1**: Cycle through available audio input devices
2. **Button 2**: (Not used)
3. **Button 3**: (Not used)
4. **Button 4**: (Not used)
5. **Button 5**: Return to previous page (Main Menu)
6. **Button 6**: (Not used)

**Selecting Audio Device:**
- Press Button 1 repeatedly to cycle through available audio input devices
- "None (Disabled)" means no audio device is selected (recording disabled)
- The selected device is automatically validated before use
- If a device becomes unavailable, auto-record is automatically disabled

### Screen Timeout

- Screen automatically turns off after 30 seconds of inactivity
- Screen stays on while recording (manual or auto)
- Touch the screen to wake it up when it's off
- Screen will also wake up automatically if:
  - A recording starts while it's off
  - Audio input is detected (even when not recording)

## Recordings ##

All recordings are stored in `/home/pi/recordings/` with filenames formatted as:
- `recording_YYYYMMDD_HHMMSS_DURATION.wav`
- Example: `recording_20240115_143022_05m32s.wav` (recorded on Jan 15, 2024 at 14:30:22 for 5 minutes 32 seconds)

## Testing ##

Run the unit tests with:
```bash
python3 -m unittest test_menu_settings -v
```
