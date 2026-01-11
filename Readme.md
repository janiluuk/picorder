# Picorder - a Raspberry Pi TFT Audio Recorder

A Raspberry Pi menu system for audio recording with manual and automatic modes, compatible with Waveshare 3.5-inch TFT touch display. Also works on Linux desktop systems using pygame with X11.

![screenshot](https://github.com/janiluuk/picorder/blob/main/img/screenshot_1.png)

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

![screenshot](https://github.com/janiluuk/picorder/blob/main/img/screenshot_2.png)

## Usage ##

### Navigation Overview

- **Top Status Bar**: Screen title on the left, status indicators on the right.
- **Bottom Navigation**: Persistent tabs with icons and short labels:
  - **REC** (Home/Recorder)
  - **LIB** (Library)
  - **STAT** (Stats)
  - **SET** (Settings)

Tap the bottom nav at any time to switch screens.

### Home / Recorder (REC)

The recorder screen is the default view.

- **Timer**: Large recording duration readout.
- **Mode + State**: “Auto • Recording” or “Manual • Ready”.
- **Quick Toggles**:
  - **AUTO ON/OFF** pill toggles auto-record (requires a valid input device).
  - **SCREEN 30s** pill opens the screen-off view.
- **Record Button**: Large round button to start/stop manual recording.
- **Stop Any Recording**: Small stop-square button stops any active recording.
- **Power Icon**: Shortcut to screen-off mode.

**Auto-Record Mode:**
- When enabled, the device automatically starts recording when you plug in a 3.5mm audio jack.
- Recording stops automatically when you unplug the jack.
- Auto-record can only be enabled if a valid audio input device is configured.

**Manual Recording:**
- Tap the large record button to start recording manually.
- Tap it again (or the stop-square button) to stop recording.

![screenshot2](https://github.com/janiluuk/picorder/blob/main/img/screenshot_3.png)

### Library (LIB)

- Shows the most recent recordings in a compact list (date/time + filename).
- Tap a row to select and play the recording.
- Use the **up/down** buttons to move through the list.
- Use the **trash** button to delete the selected recording.

### Stats (STAT)

Shows a 2x2 grid of tiles for:
- Battery (placeholder if not available)
- Storage free space
- Input device
- Auto-record status

### Settings (SET)

Settings are presented as a 2x3 icon grid:
- **AUD**: Cycle audio input device.
- **AUTO**: Toggle auto-record.
- **STOR**: Jump to the Library screen.
- **SYS**: Open system/services screen.
- **SCR**: Screen-off shortcut.
- **INFO**: Jump to the Stats screen.

**Selecting Audio Device:**
- Tap **AUD** repeatedly to cycle through available audio input devices.
- "None (Disabled)" means no audio device is selected (recording disabled).
- The selected device is automatically validated before use.
- If a device becomes unavailable, auto-record is automatically disabled.

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
