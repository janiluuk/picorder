#!/usr/bin/env python3
from menu_settings import *
import threading
import time
from queue import Queue
import queue as queue_module
import menu_settings as ms
from recording_state import RecordingStateMachine, RecordingState

################################################################################
# Recording menu - main interface

# MEDIUM PRIORITY FIX: Code duplication (#12) - use helper functions
config = load_config()
auto_record_enabled = get_auto_record_enabled()
audio_device = get_audio_device()

def _1():
    # Toggle auto-record (allow turning OFF even without valid device)
    global auto_record_enabled, config
    # MEDIUM PRIORITY FIX: Code duplication (#12) - use helper functions
    audio_device = get_audio_device()
    current_auto_record = get_auto_record_enabled()
    
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
                # Note: qsize() check is not atomic, but Queue.put() is thread-safe
                # The size limit is advisory - if exceeded, the worker will process items sequentially
                try:
                    _recording_queue.put_nowait(("stop", None, None))
                except (queue_module.Full, AttributeError, TypeError) as e:
                    logger.debug(f"Queue put_nowait failed: {e}, using timeout fallback")
                    # Fallback to blocking put with timeout
                    try:
                        _recording_queue.put(("stop", None, None), timeout=0.1)
                    except Exception as e2:
                        logger.error(f"Failed to queue stop operation: {e2}")
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
                    # Note: qsize() check is not atomic, but Queue.put() is thread-safe
                    try:
                        _recording_queue.put_nowait(("stop", None, None))
                    except (queue_module.Full, AttributeError, TypeError) as e:
                        logger.debug(f"Queue put_nowait failed: {e}, using timeout fallback")
                        # Fallback to blocking put with timeout
                        try:
                            _recording_queue.put(("stop", None, None), timeout=0.1)
                        except Exception as e2:
                            logger.error(f"Failed to queue stop operation: {e2}")
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
        except (AttributeError, pygame.error, OSError) as e:
            logger.debug(f"Error updating display: {e}")
            pass  # Don't let display update block
        return
    
    # Update display - wrap in try-except to prevent blocking
    try:
        update_display()
    except (AttributeError, pygame.error, OSError) as e:
        logger.debug(f"Error updating display: {e}")
        pass  # Don't let display update block

# Queue for recording operations to avoid blocking UI
# Use the shared queue from menu_settings so it persists across page navigations
# Both queue and event must always be initialized together to prevent AttributeError
if ms._recording_queue is None:
    # MEDIUM PRIORITY FIX: Unbounded queue (#19) - add size limit to prevent memory exhaustion
    # LOW PRIORITY FIX: Magic numbers (#13) - extracted to constant
    MAX_QUEUE_SIZE = 100  # Reasonable limit: 100 operations (if worker is slow, we'll drop old operations)
    ms._recording_queue = Queue(maxsize=MAX_QUEUE_SIZE)
# Always ensure the event is initialized, even if queue already exists
# This prevents crashes if queue persists but event doesn't (e.g., after page reload)
if not hasattr(ms, '_recording_operation_in_progress') or ms._recording_operation_in_progress is None:
    ms._recording_operation_in_progress = threading.Event()
# Simplified: Just use RecordingManager as source of truth
# No optimistic state, no state machine - just queue operations and let worker handle them
_recording_queue = ms._recording_queue
_recording_operation_in_progress = ms._recording_operation_in_progress

def _recording_worker():
    """Background worker thread for recording operations - REFACTORED for reliability"""
    from queue import Empty
    import menu_settings as ms  # Import at function level to avoid circular imports
    import time
    import subprocess
    
    logger.info("Worker thread started and running")
    iteration = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while True:
        operation = None
        
        try:
            # PERFORMANCE FIX: Worker thread polling overhead (#8) - use blocking get without timeout
            # This prevents unnecessary CPU usage from polling every 500ms
            # Block indefinitely until an item is available (thread will wake on item arrival)
            try:
                operation = _recording_queue.get(block=True, timeout=None)  # Block indefinitely
                logger.info(f"Worker: Got operation from queue: {operation}")
                consecutive_errors = 0  # Reset error counter on success
            except Empty:
                # Should not happen with blocking=True and timeout=None, but handle gracefully
                logger.warning("Worker: Unexpected Empty exception with blocking get")
                # LOW PRIORITY FIX: Magic numbers (#13) - extracted to constant
                WORKER_ERROR_SLEEP = 0.1  # 100ms - brief sleep to prevent tight loop
                time.sleep(WORKER_ERROR_SLEEP)
                continue
            
            if operation is None:  # Shutdown signal
                logger.info("Worker: Received shutdown signal, exiting")
                break
            
            # Parse operation
            try:
                op_type, device, mode = operation
            except (ValueError, TypeError) as e:
                logger.error(f"Worker: Invalid operation format: {operation}, error: {e}")
                _recording_queue.task_done()  # Mark as done even if invalid
                continue
            
            logger.info(f"Worker: Processing {op_type} operation (device={device}, mode={mode})")
            # THREAD SAFETY FIX: Queue qsize() without synchronization (#10) - removed for accuracy
            # qsize() is not atomic and can be misleading, so we don't log it
            # Safely set operation in progress - check for None to prevent AttributeError
            if _recording_operation_in_progress is not None:
                _recording_operation_in_progress.set()  # Mark operation as in progress
            else:
                logger.warning("Worker: _recording_operation_in_progress is None, skipping set()")
            
            # Process operation - SIMPLIFIED: Just execute and log result
            try:
                if op_type == "start":
                    try:
                        logger.info("Worker: Processing START operation from queue")
                        result = start_recording(device, mode=mode)
                        if result:
                            logger.info("Worker: Recording started successfully")
                        else:
                            logger.warning("Worker: Recording start failed")
                    except Exception as e:
                        logger.error(f"Worker: Failed to start recording: {e}", exc_info=True)
                elif op_type == "stop":
                    # SIMPLIFIED STOP: Kill processes first, then call stop_recording()
                    logger.info("Worker: Processing STOP operation from queue")
                    
                    # MEDIUM PRIORITY FIX: Code duplication (#12) - use helper function
                    audio_device = None
                    try:
                        audio_device = get_audio_device()
                    except Exception as e:
                        logger.warning(f"Worker: Could not get audio device: {e}")
                        audio_device = ""
                    
                    # Kill arecord processes FIRST (most reliable)
                    if audio_device:
                        try:
                            logger.info(f"Worker: Killing arecord processes for {audio_device}")
                            ms._recording_manager._kill_zombie_arecord_processes(audio_device)
                        except Exception as e:
                            logger.error(f"Worker: Error killing processes: {e}", exc_info=True)
                    
                    # Call stop_recording() to clean up state
                    try:
                        result = stop_recording()
                        logger.info(f"Worker: stop_recording() returned: {result}")
                    except Exception as e:
                        logger.error(f"Worker: stop_recording() exception: {e}", exc_info=True)
                    
                    # Ensure state is cleared (stop_recording() should do this, but be safe)
                    try:
                        with ms._recording_manager._lock:
                            if ms._recording_manager._is_recording:
                                logger.warning("Worker: State still marked as recording after stop, clearing...")
                                ms._recording_manager._is_recording = False
                                ms._recording_manager._recording_process = None
                                ms._recording_manager._recording_filename = None
                                ms._recording_manager._recording_start_time = None
                                ms._recording_manager._recording_mode = None
                                ms._recording_manager._cached_is_recording = False
                                ms._recording_manager._cached_mode = None
                                ms._recording_manager._cached_start_time = None
                    except Exception as e:
                        logger.error(f"Worker: Error clearing state: {e}", exc_info=True)
                    
                    logger.info("Worker: Stop operation COMPLETE")
            except Exception as e:
                logger.error(f"Worker: Exception processing {op_type} operation: {e}", exc_info=True)
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Worker: {consecutive_errors} consecutive errors - resetting error counter")
                    consecutive_errors = 0
            finally:
                # ALWAYS mark operation as done and clear in-progress flag
                # Safely clear - check for None to prevent AttributeError
                if _recording_operation_in_progress is not None:
                    _recording_operation_in_progress.clear()
                else:
                    logger.warning("Worker: _recording_operation_in_progress is None, skipping clear()")
                try:
                    _recording_queue.task_done()
                except (AttributeError, TypeError) as e:
                    logger.debug(f"Error calling task_done(): {e}")
                    pass  # Ignore errors in task_done()
                logger.info(f"Worker: Completed {op_type} operation")
                # THREAD SAFETY FIX: Queue qsize() without synchronization (#10) - removed
                
        except Exception as e:
            # Outer exception handler - catch any unexpected errors
            logger.error(f"Worker: Unexpected error in main loop: {e}", exc_info=True)
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"Worker: {max_consecutive_errors} consecutive errors - worker may be stuck!")
                consecutive_errors = 0
                # LOW PRIORITY FIX: Magic numbers (#13) - extracted to constant  
                WORKER_ERROR_SLEEP = 0.1  # 100ms - small delay to prevent tight error loop
                time.sleep(WORKER_ERROR_SLEEP)
            # Safely clear - check for None to prevent AttributeError
            if _recording_operation_in_progress is not None:
                _recording_operation_in_progress.clear()
            # Continue loop - don't let errors stop the worker
            continue

# Start background worker thread (only if not already running)
# Use the shared thread from menu_settings so it persists across page navigations
if ms._recording_thread is None or not ms._recording_thread.is_alive():
    logger.info("Initializing recording worker thread...")
    ms._recording_thread = threading.Thread(target=_recording_worker, daemon=True, name="RecordingWorker")
    ms._recording_thread.start()
    logger.info(f"Started recording worker thread: {ms._recording_thread.name}, alive: {ms._recording_thread.is_alive()}")
else:
    logger.info(f"Recording worker thread already running: {ms._recording_thread.name}, alive: {ms._recording_thread.is_alive()}")
_recording_thread = ms._recording_thread

def _2():
    # Manual record/stop (toggle) - COMPLETELY NON-BLOCKING
    # Simplified: Just queue the operation based on current button state
    # No complex state checking, no locks, no blocking calls
    global audio_device, _recording_thread
    
    # Debounce: Prevent rapid double-clicks
    import time
    if not hasattr(_2, '_last_call_time'):
        _2._last_call_time = 0
    current_time = time.time()
    time_since_last_call = current_time - _2._last_call_time
    # LOW PRIORITY FIX: Magic numbers (#13) - extracted to constant
    BUTTON_DEBOUNCE_TIME = 0.2  # 200ms debounce to prevent double-clicks
    if time_since_last_call < BUTTON_DEBOUNCE_TIME:
        logger.debug(f"_2(): Ignoring rapid click (debounce: {time_since_last_call:.3f}s)")
        return
    _2._last_call_time = current_time
    
    # MEDIUM PRIORITY FIX: Code duplication (#12) - use helper function
    try:
        device = get_audio_device()
    except Exception as e:
        logger.warning(f"_2(): Could not get audio device: {e}")
        return
    
    if not device:
        logger.warning("_2(): No audio device configured")
        return
    
    # SIMPLIFIED: Check current button state from display (non-blocking)
    # The button text tells us what to do - no need for complex state checking
    try:
        # Get current recording state WITHOUT blocking
        actual_state = ms._recording_manager.get_recording_state(blocking=False)
        is_recording = actual_state['is_recording'] if actual_state else False
    except Exception as e:
        logger.warning(f"_2(): Could not get recording state: {e}")
        is_recording = False
    
    # SIMPLE DECISION: If recording, queue stop. If not, queue start.
    # No optimistic state, no pending flags, no complex logic
    try:
        if is_recording:
            # Currently recording - queue stop
            logger.info("_2(): Queuing STOP operation")
            _recording_queue.put_nowait(("stop", None, None))
            logger.info("_2(): Stop operation queued")
            # THREAD SAFETY FIX: Queue qsize() without synchronization (#10) - removed for accuracy
        else:
            # Not recording - queue start
            logger.info(f"_2(): Queuing START operation for device: {device}")
            _recording_queue.put_nowait(("start", device, "manual"))
            logger.info("_2(): Start operation queued")
            # THREAD SAFETY FIX: Queue qsize() without synchronization (#10) - removed
    except (queue_module.Full, AttributeError, TypeError) as e:
        # MEDIUM PRIORITY FIX: Unbounded queue (#19) - handle Full exception for bounded queue
        if isinstance(e, queue_module.Full):
            logger.warning("_2(): Queue is full - dropping operation (worker may be slow)")
            # Could implement queue drop policy (drop oldest, drop this, etc.)
            # For now, just log and continue - better to drop than block UI
        else:
            # Fallback with timeout if put_nowait fails for other reasons
            logger.warning(f"_2(): put_nowait failed: {e}, trying timeout fallback")
            try:
                if is_recording:
                    # LOW PRIORITY FIX: Magic numbers (#13) - extracted to constant
                    QUEUE_FALLBACK_TIMEOUT = 0.01  # 10ms - short timeout for fallback queue operations
                    _recording_queue.put(("stop", None, None), timeout=QUEUE_FALLBACK_TIMEOUT)
                else:
                    _recording_queue.put(("start", device, "manual"), timeout=QUEUE_FALLBACK_TIMEOUT)
                logger.info("_2(): Operation queued with timeout fallback")
            except Exception as e2:
                logger.error(f"_2(): Failed to queue operation: {e2}")
    except Exception as e:
        logger.error(f"_2(): Unexpected error queuing operation: {e}", exc_info=True)
    
    # NO display update here - let the callback handle it to avoid blocking
    # The display will update automatically on the next callback cycle
    
    # Return immediately - no blocking operations
    return

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
        # MEDIUM PRIORITY FIX: Code duplication (#12) - use helper functions
        auto_record_enabled = get_auto_record_enabled()
        audio_device = get_audio_device()
        
        # Get recording state in a single thread-safe operation to avoid race conditions
        # Use get_recording_state() to get both values atomically
        recording_state = ms._recording_manager.get_recording_state(blocking=False)
        if recording_state:
            is_currently_recording = recording_state['is_recording']
            current_recording_mode = recording_state['mode']
        else:
            is_currently_recording = False
            current_recording_mode = None
        
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
        # Use get_recording_state() for consistency, but we only need is_recording here
        polling_state = ms._recording_manager.get_recording_state(blocking=False)
        is_currently_recording = polling_state['is_recording'] if polling_state else False
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
        # MEDIUM PRIORITY FIX: Code duplication (#12) - use helper functions (cache-aware)
        audio_device = get_audio_device()
        auto_record_enabled = get_auto_record_enabled()
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
    
    # SIMPLIFIED: Get recording state - just use actual state, no optimistic state
    # This eliminates lock contention and complexity - just get state and display it
    display_is_recording = False
    display_mode = None
    display_start_time = None
    
    try:
        import menu_settings as ms
        # Get actual recording state (non-blocking)
        state = ms._recording_manager.get_recording_state(blocking=False)
        if state:
            display_is_recording = state['is_recording']
            display_mode = state['mode']
            display_start_time = state['start_time']
    except Exception as e:
        logger.debug(f"Error getting recording state: {e}")
        # Default to not recording on error
    
    # Calculate status based on display state
    if display_is_recording and display_start_time:
        duration = int(time.time() - display_start_time)
        minutes = duration // 60
        seconds = duration % 60
        mode_str = "Auto" if display_mode == "auto" else "Manual"
        status = f"● {mode_str}: {minutes:02d}:{seconds:02d}"
    elif display_is_recording:
        status = "● Recording"
    else:
        status = "Ready"
    audio_level = 0.0
    show_meter = False
    # Use display_is_recording instead of is_currently_recording to match the displayed UI state
    # This ensures the meter appears when optimistic updates show "Recording" even if actual recording hasn't started yet
    if device_valid and display_is_recording:
        try:
            # Skip audio level check to avoid blocking - just show meter at 0
            # Audio level can be checked less frequently or in background
            audio_level = 0.0  # Don't check audio level - it blocks!
            show_meter = True
        except (AttributeError, OSError) as e:
            logger.debug(f"Error getting audio level: {e}")
            pass  # If getting audio level fails, just don't show meter
    
    # Update names with current status
    if device_valid:
        auto_text = "Auto"
    else:
        auto_text = "Auto (No Device)"
    
    names[0] = status
    names[1] = auto_text
    # Use display state for button text (includes optimistic updates for immediate feedback)
    if display_is_recording:
        if display_mode == "manual":
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
    # Record button (button 2) should be red when recording (use display state)
    if display_is_recording:
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
        except (AttributeError, pygame.error) as e:
            logger.debug(f"Error pumping events: {e}")
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
    except (AttributeError, OSError, KeyError) as e:
        logger.debug(f"Error getting initial recording state: {e}")
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
        # MEDIUM PRIORITY FIX: Code duplication (#12) - use helper functions
        auto_record_enabled = get_auto_record_enabled()
        audio_device = get_audio_device()
        if auto_record_enabled and audio_device:
            button_colors[1] = green  # Green background when auto-record is enabled
    except (AttributeError, OSError, KeyError) as e:
        logger.debug(f"Error getting initial state for button colors: {e}")
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
