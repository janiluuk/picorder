#!/usr/bin/env python3
from menu_settings import *
import threading
import time
from queue import Queue

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
    
    # Check if device is valid - skip validation to avoid blocking
    # Just check if device is configured, don't validate (validation can block)
    device_valid = bool(audio_device)  # Just check if device is configured
    
    # If trying to turn ON without valid device, prevent it
    # But always allow turning OFF (even without valid device)
    if current_auto_record:
        # Currently ON - allow turning OFF regardless of device validity
        auto_record_enabled = False
        config["auto_record"] = False
        save_config(config)
        # Stop silentjack and any auto recordings in background to avoid blocking
        # Use try-except to prevent crashes
        try:
            import menu_settings as ms
            # Use non-blocking state check to avoid freezing
            state = ms._recording_manager.get_recording_state(blocking=False)
            if state and state['is_recording'] and state['mode'] == "auto":
                # Queue stop operation to avoid blocking
                if not _recording_operation_in_progress.is_set() and _recording_queue.qsize() <= 2:
                    _recording_queue.put(("stop", None, None))
        except Exception as e:
            logger.debug(f"Error checking recording state when disabling auto-record: {e}")
        
        # Stop silentjack in background (non-blocking)
        # Use threading to avoid blocking the UI
        def stop_silentjack_async():
            try:
                stop_silentjack()
            except Exception as e:
                logger.debug(f"Error stopping silentjack: {e}")
        
        threading.Thread(target=stop_silentjack_async, daemon=True).start()
    elif device_valid:
        # Currently OFF - allow turning ON only if device is valid
        # Check if there's an active recording - if so, stop it first
        import menu_settings as ms
        try:
            # Use non-blocking state check to avoid freezing
            state = ms._recording_manager.get_recording_state(blocking=False)
            if state and state['is_recording']:
                # There's an active recording - stop it first before enabling auto-record
                # This prevents conflicts between manual and auto recording
                if state['mode'] == 'manual':
                    # Stop manual recording before enabling auto-record
                    # Queue the stop operation to avoid blocking
                    if not _recording_operation_in_progress.is_set() and _recording_queue.qsize() <= 2:
                        _recording_queue.put(("stop", None, None))
                # If it's an auto recording, we can still enable auto-record (it's already on)
        except Exception as e:
            logger.debug(f"Error checking recording state when enabling auto-record: {e}")
            # On error, continue anyway - auto_record_monitor will handle it
        
        auto_record_enabled = True
        config["auto_record"] = True
        save_config(config)
        # auto_record_monitor will handle starting silentjack
    else:
        # Currently OFF and device invalid - can't turn ON
        # Still update display to provide visual feedback that the action was rejected
        try:
            update_display()
        except:
            pass  # Don't let display update block
        return
    
    # Update display - wrap in try-except to prevent blocking
    try:
        update_display()
    except:
        pass  # Don't let display update block

# Queue for recording operations to avoid blocking UI
_recording_queue = Queue()
_recording_operation_in_progress = threading.Event()  # Track if operation is in progress

def _recording_worker():
    """Background worker thread for recording operations"""
    from queue import Empty
    while True:
        try:
            operation = _recording_queue.get(timeout=1.0)  # Use timeout to allow periodic checks
            if operation is None:  # Shutdown signal
                break
            op_type, device, mode = operation
            _recording_operation_in_progress.set()  # Mark operation as in progress
            try:
                if op_type == "start":
                    try:
                        start_recording(device, mode=mode)
                    except Exception as e:
                        logger.warning(f"Failed to start recording in background: {e}", exc_info=True)
                elif op_type == "stop":
                    try:
                        stop_recording()
                    except Exception as e:
                        logger.warning(f"Failed to stop recording in background: {e}", exc_info=True)
            finally:
                _recording_operation_in_progress.clear()  # Mark operation as complete
            _recording_queue.task_done()
        except Empty:
            # Timeout is normal - just continue the loop
            continue
        except Exception as e:
            logger.error(f"Error in recording worker: {e}", exc_info=True)
            _recording_operation_in_progress.clear()  # Clear on error
            # Continue loop on errors
            continue

# Start background worker thread
_recording_thread = threading.Thread(target=_recording_worker, daemon=True)
_recording_thread.start()

def _2():
    # Manual record/stop (toggle)
    global audio_device
    config = load_config()
    audio_device = config.get("audio_device", "")
    
    # Skip device validation to avoid blocking - just check if device is configured
    if not audio_device:
        # No device configured, can't record
        return
    
    # Prevent multiple operations from being queued
    # If an operation is already in progress, skip this one
    if _recording_operation_in_progress.is_set():
        # Operation already in progress, don't queue another
        return
    
    # Check if queue is already full or has pending operations
    # Limit queue size to prevent buildup
    if _recording_queue.qsize() > 2:
        # Too many operations queued, skip this one
        return
    
    # Don't check recording state here - it might block if lock is held
    # Just queue the operation and let the background thread handle state checking
    # This ensures the button handler returns immediately
    import pygame
    
    # Process events before starting to keep UI responsive
    pygame.event.pump()
    
    # Try to get current state non-blocking to decide if we should start or stop
    import menu_settings as ms
    try:
        state = ms._recording_manager.get_recording_state(blocking=False)
        if state and state['is_recording']:
            # Currently recording (any mode) - queue stop
            # The button should stop any active recording, not just manual ones
            _recording_queue.put(("stop", None, None))
            logger.debug(f"Queued stop operation (recording mode: {state.get('mode', 'unknown')})")
        else:
            # Not recording or can't get state - queue start
            _recording_queue.put(("start", audio_device, "manual"))
            logger.debug("Queued start operation")
    except Exception as e:
        # On error, try to check if recording is active using blocking call as fallback
        logger.debug(f"Non-blocking state check failed: {e}, trying blocking check")
        try:
            # Fallback: use blocking check if non-blocking fails
            state = ms._recording_manager.get_recording_state(blocking=True)
            if state and state['is_recording']:
                _recording_queue.put(("stop", None, None))
                logger.debug("Queued stop operation (from blocking check)")
            else:
                _recording_queue.put(("start", audio_device, "manual"))
                logger.debug("Queued start operation (from blocking check)")
        except:
            # If both fail, just queue start (safe default)
            _recording_queue.put(("start", audio_device, "manual"))
            logger.debug("Queued start operation (fallback)")
    
    # Process events after queuing operation to keep UI responsive
    pygame.event.pump()
    
    # Don't call update_display() here - it might block on property getters
    # Just update the display surface to show button was pressed
    # The display will update when the user presses another button or when recording actually starts
    try:
        pygame.display.update()
        pygame.event.pump()
    except:
        pass

def _3():
    # Settings (button 3)
    go_to_page(PAGE_02)

def _4():
    # Library (button 4)
    go_to_page(PAGE_05)

def _5():
    # Screen Off (button 5)
    go_to_page(SCREEN_OFF)

def _6():
    # Not used in main menu
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
    
    # Quick return if screen not initialized
    if 'screen' not in globals() or screen is None:
        return
    
    # Try to make this as lightweight as possible to avoid blocking
    # If anything takes too long, we'll skip it
    
    # Get current device configuration with validation
    # Use try-except to prevent blocking on validation errors
    # Skip validation entirely to avoid blocking - just use config values
    # Use cached config if available to avoid file I/O on every update
    try:
        # Try to get config quickly - use cached version if possible
        config = load_config()
        audio_device = config.get("audio_device", "")
        auto_record_enabled = config.get("auto_record", False)
        # Don't validate device here - it blocks! Just assume it might be valid
        # Validation can happen in background or be skipped for display purposes
        device_valid = bool(audio_device)  # Just check if device is configured, don't validate
    except Exception as e:
        # On error, use defaults quickly without retrying file I/O
        logger.debug(f"Error getting device config in update_display: {e}")
        audio_device = ""
        auto_record_enabled = False
        device_valid = False
    
    # Don't stop recordings here - it blocks! Just update the display
    # Recording management should happen in response to user actions, not in display updates
    
    # Update recording status - use thread-safe property getters
    # The property getters use locks, but they should be fast (just reading booleans)
    # If they block, it means start_recording is holding the lock, which should be brief
    status = "Ready"
    duration = 0
    audio_indicator = ""
    is_currently_recording = False
    current_mode = None
    recording_start_time = None
    
    try:
        import menu_settings as ms
        # Use get_recording_state() with non-blocking mode to avoid UI freeze
        # This now returns cached state if lock is held, so we always get a result
        state = ms._recording_manager.get_recording_state(blocking=False)
        # State is never None now - it returns cached state if lock is held
        is_currently_recording = state['is_recording']
        current_mode = state['mode']
        recording_start_time = state['start_time']
    except Exception as e:
        logger.debug(f"Error getting recording state: {e}")
        is_currently_recording = False
        current_mode = None
        recording_start_time = None
    
    # Calculate status based on state
    if is_currently_recording and recording_start_time:
        duration = int(time.time() - recording_start_time)
        minutes = duration // 60
        seconds = duration % 60
        mode_str = "Auto" if current_mode == "auto" else "Manual"
        # Add audio indicator (● for recording)
        audio_indicator = "●"
        status = f"{audio_indicator} {mode_str}: {minutes:02d}:{seconds:02d}"
    elif is_currently_recording:
        # Recording but no start time (shouldn't happen, but handle gracefully)
        status = "● Recording"
        audio_indicator = "●"
    else:
        # Not recording
        status = "Ready"
    audio_level = 0.0
    show_meter = False
    if device_valid and is_currently_recording:
        try:
            # Skip audio level check to avoid blocking - just show meter at 0
            # Audio level can be checked less frequently or in background
            audio_level = 0.0  # Don't check audio level - it blocks!
            show_meter = True
        except Exception:
            pass  # If getting audio level fails, just don't show meter
    
    # Update names with current status
    if device_valid:
        auto_text = "Auto"
    else:
        auto_text = "Auto (No Device)"
    
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
    names[3] = "Settings"  # Button 3
    names[4] = "Library"   # Button 4
    names[5] = "Screen Off"  # Button 5
    
    # Determine button colors for active states
    button_colors = {}
    # Auto button (button 1) should be green when enabled
    if auto_record_enabled and device_valid:
        button_colors[1] = green  # Green background when auto-record is enabled
    # Record button (button 2) should be red when recording
    if is_currently_recording:
        button_colors[2] = red  # Red background when recording
    
    # Redraw screen - wrap in try-except to prevent blocking
    import pygame
    try:
        # Process events before redraw to keep UI responsive
        pygame.event.pump()
        
        # Note: Property getters will block if lock is held, but they should be quick
        # The lock is only held briefly for reading state, so this should be fast
        
        # Redraw screen
        screen.fill(black)
        draw_screen_border(screen)
        # Draw: label1 (status), buttons for Auto/Record (b12), Settings/Library (b34), Screen Off (b56)
        # b12=True draws buttons at positions 1 and 2 (Auto toggle and Record/Stop)
        # b34=True draws buttons at positions 3 and 4 (Settings and Library)
        # b56=True draws buttons at positions 5 and 6 (Screen Off and empty)
        populate_screen(names, screen, b12=True, b34=True, b56=True, label1=True, label2=False, label3=False, show_audio_meter=show_meter, audio_level=audio_level, button_colors=button_colors)
        
        # Process events during redraw to keep UI responsive
        pygame.event.pump()
        
        # Ensure display is updated (non-blocking)
        pygame.display.update()
        
        # Process events after update to keep UI responsive
        pygame.event.pump()
    except Exception as e:
        logger.debug(f"Error in update_display: {e}")
        # Don't let display update errors break the callback
        try:
            pygame.event.pump()
        except:
            pass

# Start auto-record monitor thread
auto_record_thread = threading.Thread(target=auto_record_monitor, daemon=True)
auto_record_thread.start()

# Initial display setup
try:
    print("Initializing display...", flush=True)
    # Initialize display FIRST to show window immediately
    screen = init()
    import pygame
    print("Display initialized", flush=True)
    
    # Update activity to prevent immediate screen timeout
    update_activity()
    
    # Show initial screen immediately (before any validation that might block)
    # Use default status initially to avoid any blocking - will be updated by callback
    print("Setting up initial display...", flush=True)
    # Check actual recording state on startup (non-blocking)
    import menu_settings as ms
    try:
        state = ms._recording_manager.get_recording_state(blocking=False)
        if state and state['is_recording'] and state['start_time']:
            duration = int(time.time() - state['start_time'])
            minutes = duration // 60
            seconds = duration % 60
            mode_str = "Auto" if state['mode'] == "auto" else "Manual"
            status = f"● {mode_str}: {minutes:02d}:{seconds:02d}"
        else:
            status = "Ready"
    except:
        status = "Ready"  # Default status if we can't get state
    
    names = [status, "Auto", "Record", "Settings", "Library", "Screen Off", ""]
    print(f"Initial status: {status}", flush=True)
    
    # Draw initial screen without validation (fast)
    # First, make sure screen is filled (init() already does this, but be safe)
    print("Drawing screen...", flush=True)
    screen.fill(black)
    draw_screen_border(screen)
    
    # Determine button colors based on current state
    button_colors = {}
    try:
        state = ms._recording_manager.get_recording_state(blocking=False)
        if state and state['is_recording']:
            button_colors[2] = red  # Red background when recording
        # Check auto-record status
        config = load_config()
        auto_record_enabled = config.get("auto_record", False)
        audio_device = config.get("audio_device", "")
        if auto_record_enabled and audio_device:
            button_colors[1] = green  # Green background when auto-record is enabled
    except:
        pass  # If we can't get state, just don't set colors
    
    # Make sure we draw everything: label1 (status), buttons for Auto/Record (b12), Settings and Screen Off (b34)
    print("Populating screen...", flush=True)
    populate_screen(names, screen, b12=True, b34=True, b56=True, label1=True, label2=False, label3=False, button_colors=button_colors)
    
    # Force display update multiple times to ensure it's visible
    print("Updating display...", flush=True)
    pygame.display.flip()
    for _ in range(10):
        pygame.event.pump()
        pygame.display.update()
    
    # Update activity again after drawing to ensure screen doesn't timeout
    update_activity()
    
    pygame.time.wait(500)  # Give time for window to render
    print("Starting main loop...", flush=True)
    
    # Start main loop with lightweight callback
    # Callback updates display but is throttled to prevent blocking
    main([_1, _2, _3, _4, _5, _6], update_callback=update_display)
except (RuntimeError, Exception) as e:
    import sys
    from menu_settings import IS_RASPBERRY_PI
    print(f"Error starting menu: {e}", file=sys.stderr)
    if not IS_RASPBERRY_PI:
        print("This menu requires X11 display. Make sure DISPLAY is set and you're running in a graphical environment.", file=sys.stderr)
    else:
        print("This menu requires a physical display (TFT screen) connected to the Raspberry Pi.", file=sys.stderr)
        print("Cannot run over SSH without X11 forwarding.", file=sys.stderr)
    sys.exit(1)
