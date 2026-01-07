#!/usr/bin/env python3
from sys import argv as __argv__
from menu_settings import *
import threading

################################################################################
# Recording menu - main interface

config = load_config()
auto_record_enabled = config.get("auto_record", True)
audio_device = config.get("audio_device", "plughw:0,0")

def _1():
    # Toggle auto-record
    global auto_record_enabled, config
    auto_record_enabled = not auto_record_enabled
    config["auto_record"] = auto_record_enabled
    save_config(config)
    if not auto_record_enabled:
        stop_silentjack()
        if is_recording and recording_mode == "auto":
            stop_recording()
    update_display()

def _2():
    # Manual record/stop (toggle)
    global is_recording, audio_device
    config = load_config()
    audio_device = config.get("audio_device", "")
    
    # Check if device is valid before recording
    if not audio_device or not is_audio_device_valid(audio_device):
        # No valid device, can't record
        return
    
    if is_recording and recording_mode == "manual":
        stop_recording()
    else:
        # Stop any existing recording first
        if is_recording:
            stop_recording()
        start_recording(audio_device, mode="manual")
    update_display()

def _3():
    # Stop recording (if active)
    if is_recording:
        stop_recording()
    update_display()

def _4():
    # Settings
    go_to_page(PAGE_02)

def _5():
    # Screen off
    go_to_page(SCREEN_OFF)

def _6():
    # Next page (not used in main menu)
    pass

def auto_record_monitor():
    """Monitor and manage silentjack for auto-recording"""
    global is_recording, auto_record_enabled, config, recording_mode, recording_start_time
    while True:
        config = load_config()  # Reload config in case it changed
        auto_record_enabled = config.get("auto_record", False)
        audio_device = config.get("audio_device", "")
        
        # Check if device is valid
        if not audio_device or not is_audio_device_valid(audio_device):
            # Invalid device, disable auto-record and stop silentjack
            if auto_record_enabled:
                config["auto_record"] = False
                save_config(config)
                auto_record_enabled = False
            stop_silentjack()
            if is_recording and recording_mode == "auto":
                stop_recording()
            time.sleep(1)
            continue
        
        if auto_record_enabled:
            # Start silentjack if not running
            import menu_settings as ms
            if ms.silentjack_process is None or (ms.silentjack_process.poll() is not None):
                start_silentjack(audio_device)
            
            # Check if silentjack started a recording
            if os.path.exists(MENUDIR + ".recording_start"):
                try:
                    with open(MENUDIR + ".recording_start", 'r') as f:
                        silentjack_start = float(f.read().strip())
                    # Check if process is running
                    if os.path.exists(MENUDIR + ".recording_pid"):
                        try:
                            with open(MENUDIR + ".recording_pid", 'r') as f:
                                pid = int(f.read().strip())
                            try:
                                os.kill(pid, 0)  # Check if process exists
                                # Silentjack recording is active
                                if not is_recording or recording_mode != "auto":
                                    # Update our state to reflect silentjack recording
                                    import menu_settings as ms
                                    ms.recording_start_time = silentjack_start
                                    ms.recording_mode = "auto"
                                    ms.is_recording = True
                            except:
                                # Process stopped, clean up
                                import menu_settings as ms
                                if ms.is_recording and ms.recording_mode == "auto":
                                    ms.is_recording = False
                                    ms.recording_mode = None
                                for f in [".recording_pid", ".recording_file", ".recording_start"]:
                                    try:
                                        os.remove(MENUDIR + f)
                                    except:
                                        pass
                        except:
                            pass
                except:
                    pass
            else:
                # No silentjack recording
                import menu_settings as ms
                if ms.is_recording and ms.recording_mode == "auto":
                    ms.is_recording = False
                    ms.recording_mode = None
        else:
            # Auto-record disabled, stop silentjack
            stop_silentjack()
            import menu_settings as ms
            if ms.is_recording and ms.recording_mode == "auto":
                stop_recording()
        
        time.sleep(0.5)

def update_display():
    """Update display with current recording status"""
    global screen, names, auto_record_enabled
    
    # Reload config to get latest settings
    config = load_config()
    audio_device = config.get("audio_device", "")
    auto_record_enabled = config.get("auto_record", False)
    
    # Check if device is valid
    device_valid = audio_device and is_audio_device_valid(audio_device)
    if not device_valid:
        auto_record_enabled = False
    
    # Update recording status
    status, duration = get_recording_status()
    
    # Update names with current status
    if device_valid:
        auto_text = "Auto: ON" if auto_record_enabled else "Auto: OFF"
    else:
        auto_text = "Auto: OFF (No Device)"
    
    names[0] = status
    names[1] = auto_text
    if is_recording and recording_mode == "manual":
        names[2] = "Stop"
    elif device_valid:
        names[2] = "Record"
    else:
        names[2] = "Record (Disabled)"
    names[3] = "Settings"
    names[4] = "Screen Off"
    
    # Redraw screen
    screen.fill(black)
    pygame.draw.rect(screen, tron_regular, (0,0,479,319),8)
    pygame.draw.rect(screen, tron_light, (2,2,479-4,319-4),2)
    populate_screen(names, screen, b34=False, b56=False)

# Start auto-record monitor thread
auto_record_thread = threading.Thread(target=auto_record_monitor, daemon=True)
auto_record_thread.start()

# Initial display setup
status, _ = get_recording_status()
names = [status, "Auto: ON" if auto_record_enabled else "Auto: OFF", "Record", "Settings", "Screen Off", "", ""]

screen = init()
update_display()
main([_1, _2, _3, _4, _5, _6], update_callback=update_display)
