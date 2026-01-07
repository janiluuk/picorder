#!/usr/bin/env python3
from sys import argv as __argv__
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
    # Select audio device
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
    if audio_device == "" or not is_audio_device_valid(audio_device):
        config["auto_record"] = False
        save_config(config)
        # Stop silentjack if running
        stop_silentjack()
        # Stop any active recording (thread-safe check)
        import menu_settings as ms
        if ms._recording_manager.is_recording:
            stop_recording()
    
    # Update display
    update_display()

def _2():
    # Toggle auto-record (only if valid device is selected)
    global auto_record_enabled, audio_devices, current_device_index
    config = load_config()
    audio_device = config.get("audio_device", "")
    
    # Can't enable auto-record if no device is selected
    if audio_device == "" or not is_audio_device_valid(audio_device):
        # Device invalid, can't enable
        return
    
    auto_record_enabled = not config.get("auto_record", True)
    config["auto_record"] = auto_record_enabled
    save_config(config)
    update_display()

def _3():
    # Back to main menu
    go_to_page(PAGE_01)

def _4():
    # Shutdown
    pygame.quit()
    run_cmd("/usr/bin/sudo /sbin/shutdown -h now")
    sys.exit()

def _5():
    # Previous (back to main)
    go_to_page(PAGE_01)

def _6():
    # Next (not used)
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
    if len(device_name) > 20:
        device_name = device_name[:17] + "..."
    
    # Get disk space
    disk_space = get_disk_space()
    
    # Get auto-record status
    config = load_config()
    audio_device = config.get("audio_device", "")
    auto_record_enabled = config.get("auto_record", False)
    
    # Auto-record can only be ON if valid device is selected
    device_valid = audio_device and is_audio_device_valid(audio_device)
    if not device_valid:
        auto_record_enabled = False
        auto_status = "OFF (No Device)"
        # Update config if it was enabled
        if config.get("auto_record", False):
            config["auto_record"] = False
            save_config(config)
    else:
        auto_status = "ON" if auto_record_enabled else "OFF"
    
    names[0] = "Settings"
    names[1] = "Device: " + device_name
    names[2] = "Auto: " + auto_status
    names[3] = disk_space
    
    # Redraw screen
    screen.fill(black)
    pygame.draw.rect(screen, tron_regular, (0,0,479,319),8)
    pygame.draw.rect(screen, tron_light, (2,2,479-4,319-4),2)
    populate_screen(names, screen, b12=False, b34=False, b56=False, label2=True, label3=True)

config = load_config()
auto_record_enabled = config.get("auto_record", True)
audio_device = config.get("audio_device", "plughw:0,0")

device_name = audio_devices[current_device_index][1]
if len(device_name) > 20:
    device_name = device_name[:17] + "..."

names = ["Settings", "Device: " + device_name, "Auto: " + ("ON" if auto_record_enabled else "OFF"), get_disk_space(), "Back", "", ""]

screen = init()
update_display()
main([_1, _2, _3, _4, _5, _6], update_callback=update_display)
