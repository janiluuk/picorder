#!/usr/bin/env python3
from menu_settings import *

################################################################################
# Settings menu

config = load_config()
audio_devices = get_audio_devices()
current_device_index = 0

# Find current device in list, or default to "None" if not found
current_device = config.get("audio_device", "")
for i, (dev, name) in enumerate(audio_devices):
    if dev == current_device:
        current_device_index = i
        break
else:
    # Device not found, check if it's valid
    if not is_audio_device_valid(current_device):
        # Invalid device, set to "None"
        current_device_index = 0
        config["audio_device"] = ""
        save_config(config)

def _1():
    # Select audio device (button 1)
    global current_device_index, config, audio_device, audio_devices
    # Refresh device list in case devices changed
    audio_devices = get_audio_devices()
    
    # Ensure we have at least the "None" option
    if len(audio_devices) == 0:
        audio_devices = [("", "None (Disabled)")]
        current_device_index = 0
    
    # Cycle to next device
    current_device_index = (current_device_index + 1) % len(audio_devices)
    audio_device = audio_devices[current_device_index][0]
    config["audio_device"] = audio_device
    save_config(config)
    
    # If "None" selected or device invalid, disable auto-record and stop any recordings
    # Skip validation to avoid blocking - just check if device is configured
    if audio_device == "":
        config["auto_record"] = False
        save_config(config)
        # Stop silentjack if running
        stop_silentjack()
        # Stop any active recording (thread-safe check)
        import menu_settings as ms
        try:
            if ms._recording_manager.is_recording:
                stop_recording()
        except Exception:
            pass
    
    # Update display
    update_display()

def _2():
    # Toggle auto-record (button 2)
    global auto_record_enabled, audio_devices, current_device_index
    config = load_config()
    audio_device = config.get("audio_device", "")
    
    # Can't enable auto-record if no device is selected
    if audio_device == "":
        # No device, can't enable
        return
    
    # Skip validation to avoid blocking - just check if device is configured
    auto_record_enabled = not config.get("auto_record", False)
    config["auto_record"] = auto_record_enabled
    save_config(config)
    
    # Start/stop silentjack based on new state
    if auto_record_enabled:
        # auto_record_monitor will handle starting silentjack
        pass
    else:
        stop_silentjack()
    
    update_display()

def _3():
    # Back to main menu (button 3)
    go_to_page(PAGE_01)

def _4():
    # Back to main menu (button 4 - also back)
    go_to_page(PAGE_01)

def _5():
    # Shutdown (button 5 - not shown in current layout)
    pygame.quit()
    run_cmd("/usr/bin/sudo /sbin/shutdown -h now")
    sys.exit()

def _6():
    # Not used
    pass

def update_display():
    """Update display with current settings"""
    global screen, names, audio_devices, current_device_index
    
    # Refresh device list
    audio_devices = get_audio_devices()
    
    # Ensure we have at least the "None" option
    if len(audio_devices) == 0:
        audio_devices = [("", "None (Disabled)")]
    
    # Ensure index is valid
    if current_device_index >= len(audio_devices):
        current_device_index = 0
    
    # Get current device name
    device_name = audio_devices[current_device_index][1]
    if len(device_name) > MAX_DEVICE_NAME_LENGTH:
        device_name = device_name[:17] + "..."
    
    # Get disk space
    disk_space = get_disk_space()
    
    # Get current device configuration with validation
    config, audio_device, auto_record_enabled, device_valid = get_current_device_config()
    
    # Display auto-record status
    if not device_valid:
        auto_status = "OFF (No Device)"
    else:
        auto_status = "ON" if auto_record_enabled else "OFF"
    
    # Use symbols for visual engagement
    device_symbol = "🎤" if device_valid else "❌"
    auto_symbol = "✅" if auto_record_enabled and device_valid else "⭕"
    
    names[0] = "⚙️ Settings"
    names[1] = f"{device_symbol} Device"
    names[2] = f"{auto_symbol} Auto-Record"
    names[3] = f"💾 {disk_space}"
    names[4] = "← Back"
    names[5] = ""
    names[6] = ""
    
    # Determine button colors for active states
    button_colors = {}
    if device_valid and auto_record_enabled:
        button_colors[2] = green  # Green background when auto-record is ON
    
    # Redraw screen
    screen.fill(black)
    draw_screen_border(screen)
    # Draw: label1 (title), buttons for Device and Auto-Record (b12), Back button (b34)
    populate_screen(names, screen, b12=True, b34=True, b56=False, label1=True, label2=False, label3=False, button_colors=button_colors)

config = load_config()
auto_record_enabled = config.get("auto_record", True)
audio_device = config.get("audio_device", "plughw:0,0")

device_name = audio_devices[current_device_index][1]
if len(device_name) > MAX_DEVICE_NAME_LENGTH:
    device_name = device_name[:17] + "..."

# Initialize names with symbols
device_symbol = "🎤" if audio_device else "❌"
auto_symbol = "✅" if auto_record_enabled else "⭕"
names = ["⚙️ Settings", f"{device_symbol} Device", f"{auto_symbol} Auto-Record", f"💾 {get_disk_space()}", "← Back", "", ""]

screen = init()
update_display()
main([_1, _2, _3, _4, _5, _6], update_callback=update_display)
