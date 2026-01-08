#!/usr/bin/env python3
from menu_settings import *
import threading

################################################################################
# Recording menu - main interface

config = load_config()
auto_record_enabled = config.get("auto_record", True)
audio_device = config.get("audio_device", "plughw:0,0")

def _1():
    # Toggle auto-record (allow turning OFF even without valid device)
    global auto_record_enabled, config
    config = load_config()
    audio_device = config.get("audio_device", "")
    current_auto_record = config.get("auto_record", False)
    
    # Check if device is valid
    device_valid = audio_device and is_audio_device_valid(audio_device)
    
    # If trying to turn ON without valid device, prevent it
    # But always allow turning OFF (even without valid device)
    if current_auto_record:
        # Currently ON - allow turning OFF regardless of device validity
        auto_record_enabled = False
        config["auto_record"] = False
        save_config(config)
        stop_silentjack()
        # Use RecordingManager to check recording state (thread-safe)
        # Get state in a single thread-safe operation to avoid race conditions
        import menu_settings as ms
        is_currently_recording = ms._recording_manager.is_recording
        current_mode = ms._recording_manager.recording_mode
        if is_currently_recording and current_mode == "auto":
            stop_recording()
    elif device_valid:
        # Currently OFF - allow turning ON only if device is valid
        auto_record_enabled = True
        config["auto_record"] = True
        save_config(config)
        # auto_record_monitor will handle starting silentjack
    else:
        # Currently OFF and device invalid - can't turn ON
        # Still update display to provide visual feedback that the action was rejected
        update_display()
        return
    
    update_display()

def _2():
    # Manual record/stop (toggle)
    global audio_device
    config = load_config()
    audio_device = config.get("audio_device", "")
    
    # Check if device is valid before recording
    if not audio_device or not is_audio_device_valid(audio_device):
        # No valid device, can't record
        return
    
    # Use RecordingManager to check recording state (thread-safe)
    # Get state in a single thread-safe operation to avoid race conditions
    import menu_settings as ms
    is_currently_recording = ms._recording_manager.is_recording
    current_mode = ms._recording_manager.recording_mode
    if is_currently_recording and current_mode == "manual":
        stop_recording()
    else:
        # Stop any existing recording first
        if is_currently_recording:
            stop_recording()
        start_recording(audio_device, mode="manual")
    update_display()

def _3():
    # Stop recording (if active) - use thread-safe check
    import menu_settings as ms
    if ms._recording_manager.is_recording:
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
    global auto_record_enabled, config
    import menu_settings as ms
    import time
    while True:
        config = load_config()  # Reload config in case it changed
        auto_record_enabled = config.get("auto_record", False)
        audio_device = config.get("audio_device", "")
        
        # Get recording state in a single thread-safe operation to avoid race conditions
        is_currently_recording = ms._recording_manager.is_recording
        current_recording_mode = ms._recording_manager.recording_mode
        
        # Check if device is valid
        if not audio_device or not is_audio_device_valid(audio_device):
            # Invalid device, disable auto-record and stop silentjack
            if auto_record_enabled:
                config["auto_record"] = False
                save_config(config)
                auto_record_enabled = False
            stop_silentjack()
            # Stop any active recording (both auto and manual) if device becomes invalid
            if is_currently_recording:
                stop_recording()
            time.sleep(1)
            continue
        
        if auto_record_enabled:
            # Start silentjack if not running
            # Use RecordingManager property to check if silentjack is running (thread-safe)
            if not ms._recording_manager.is_silentjack_running:
                start_silentjack(audio_device)
            
            # Check if silentjack started a recording (optimize file I/O)
            # Note: RecordingManager.get_recording_status() handles state detection automatically
            # No need to manually update state - it's all thread-safe
            recording_start_file = ms.MENUDIR / ".recording_start"
            if recording_start_file.exists():
                try:
                    with open(recording_start_file, 'r') as f:
                        silentjack_start = float(f.read().strip())
                    # Check if process is running
                    recording_pid_file = ms.MENUDIR / ".recording_pid"
                    if recording_pid_file.exists():
                        try:
                            with open(recording_pid_file, 'r') as f:
                                pid = int(f.read().strip())
                            try:
                                os.kill(pid, 0)  # Check if process exists
                                # Silentjack recording is active
                                # RecordingManager.get_recording_status() will handle state detection
                                # No need to manually update state
                                pass
                            except ProcessLookupError:
                                # Process stopped, RecordingManager will handle cleanup via get_recording_status
                                pass
                            except OSError as e:
                                logger.debug(f"Error checking process {pid}: {e}")
                        except (ValueError, OSError) as e:
                            logger.debug(f"Error reading recording PID: {e}")
                except (ValueError, OSError) as e:
                    logger.debug(f"Error reading recording start time: {e}")
            # No silentjack recording - RecordingManager handles state via get_recording_status
        else:
            # Auto-record disabled, stop silentjack
            stop_silentjack()
            # Use thread-safe check with already retrieved state
            if is_currently_recording and current_recording_mode == "auto":
                stop_recording()
        
        # Use adaptive polling - check less frequently when idle
        # Get fresh state for polling decision (single thread-safe call)
        is_currently_recording = ms._recording_manager.is_recording
        if is_currently_recording:
            time.sleep(AUTO_RECORD_POLL_INTERVAL)
        else:
            time.sleep(FILE_CHECK_INTERVAL)

def update_display():
    """Update display with current recording status"""
    global screen, names, auto_record_enabled
    
    # Get current device configuration with validation
    config, audio_device, auto_record_enabled, device_valid = get_current_device_config()
    
    if not device_valid:
        # Device invalid - stop silentjack and any active recordings
        stop_silentjack()
        # Stop any active recording if device becomes invalid
        import menu_settings as ms
        if ms._recording_manager.is_recording:
            logger.warning("Stopping recording due to invalid audio device")
            stop_recording()
    
    # Update recording status (thread-safe)
    status, duration = get_recording_status()
    
    # Get audio level for meter (only if device is valid and recording)
    # Use RecordingManager for thread-safe state check
    # Get state in a single thread-safe operation to avoid race conditions
    # Retrieve both is_recording and recording_mode atomically to ensure consistency
    import menu_settings as ms
    is_currently_recording = ms._recording_manager.is_recording
    current_mode = ms._recording_manager.recording_mode
    audio_level = 0.0
    show_meter = False
    if device_valid and is_currently_recording:
        try:
            audio_level = get_audio_level(audio_device)
            show_meter = True
        except Exception:
            pass  # If getting audio level fails, just don't show meter
    
    # Update names with current status
    if device_valid:
        auto_text = "Auto: ON" if auto_record_enabled else "Auto: OFF"
    else:
        auto_text = "Auto: OFF (No Device)"
    
    names[0] = status
    names[1] = auto_text
    # Use RecordingManager to check recording state (thread-safe)
    # Reuse state already retrieved above for consistency (both values retrieved atomically)
    if is_currently_recording:
        if current_mode == "manual":
            names[2] = "Stop"
        else:
            names[2] = "Stop"  # Auto recording can also be stopped
    elif device_valid:
        names[2] = "Record"
    else:
        names[2] = "Record (Disabled)"
    names[3] = "Settings"
    names[4] = "Screen Off"
    
    # Redraw screen
    screen.fill(black)
    draw_screen_border(screen)
    populate_screen(names, screen, b34=False, b56=False, show_audio_meter=show_meter, audio_level=audio_level)

# Start auto-record monitor thread
auto_record_thread = threading.Thread(target=auto_record_monitor, daemon=True)
auto_record_thread.start()

# Initial display setup
try:
    status, _ = get_recording_status()
    names = [status, "Auto: ON" if auto_record_enabled else "Auto: OFF", "Record", "Settings", "Screen Off", "", ""]

    screen = init()
    update_display()
    main([_1, _2, _3, _4, _5, _6], update_callback=update_display)
except (RuntimeError, Exception) as e:
    import sys
    print(f"Error starting menu: {e}", file=sys.stderr)
    print("This menu requires a physical display (TFT screen) connected to the Raspberry Pi.", file=sys.stderr)
    print("Cannot run over SSH without X11 forwarding.", file=sys.stderr)
    sys.exit(1)
