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
                # Note: qsize() check is not atomic, but Queue.put() is thread-safe
                # The size limit is advisory - if exceeded, the worker will process items sequentially
                try:
                    _recording_queue.put_nowait(("stop", None, None))
                except queue_module.Full:
                    logger.debug("Queue full, but this should not happen with unbounded Queue")
                    # Fallback to blocking put with timeout
                    _recording_queue.put(("stop", None, None), timeout=0.1)
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
                    except queue_module.Full:
                        logger.debug("Queue full, but this should not happen with unbounded Queue")
                        # Fallback to blocking put with timeout
                        _recording_queue.put(("stop", None, None), timeout=0.1)
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
# Use the shared queue from menu_settings so it persists across page navigations
if ms._recording_queue is None:
    ms._recording_queue = Queue()
    ms._recording_operation_in_progress = threading.Event()
# Always initialize state machine if it doesn't exist
if ms._recording_state_machine is None:
    from recording_state import RecordingStateMachine
    ms._recording_state_machine = RecordingStateMachine(ms._recording_manager)
# Optimistic UI state - updated immediately, synced with actual state later
if not hasattr(ms, '_optimistic_recording_state'):
    ms._optimistic_recording_state = {
        'is_recording': False,
        'mode': None,
        'start_time': None,
        'pending_start': False,
        'pending_stop': False
    }
_recording_queue = ms._recording_queue
_recording_operation_in_progress = ms._recording_operation_in_progress
_recording_state_machine = ms._recording_state_machine
_optimistic_state = ms._optimistic_recording_state

def _recording_worker():
    """Background worker thread for recording operations"""
    from queue import Empty
    logger.info("Worker thread started and running")
    iteration = 0
    while True:
        iteration += 1
        try:
            queue_size = _recording_queue.qsize()
            if queue_size > 0:
                logger.info(f"Worker iteration {iteration}: Queue has {queue_size} item(s), calling get()...")
            else:
                # Log every 10 iterations when queue is empty to show worker is alive
                if iteration % 10 == 0:
                    logger.debug(f"Worker iteration {iteration}: Queue empty, waiting with timeout...")
            
            # Try to get with timeout - but first check if queue has items
            # This helps diagnose if get() is blocking when it shouldn't
            try:
                operation = _recording_queue.get(timeout=0.5)  # Shorter timeout for more responsive checks
                logger.info(f"Worker: get() returned, got operation: {operation}")
            except Empty:
                # Timeout occurred - check if queue actually has items
                queue_size_after = _recording_queue.qsize()
                if queue_size_after > 0:
                    logger.warning(f"Worker: get() timed out but queue still has {queue_size_after} item(s) - trying get_nowait()")
                    try:
                        operation = _recording_queue.get_nowait()
                        logger.info(f"Worker: get_nowait() succeeded after timeout, got: {operation}")
                    except queue_module.Empty:
                        logger.error(f"Worker: Both get() and get_nowait() failed - queue state inconsistent!")
                        continue
                else:
                    # Queue is actually empty, normal timeout
                    continue
            if operation is None:  # Shutdown signal
                logger.info("Worker: Received shutdown signal, exiting")
                break
            op_type, device, mode = operation
            logger.info(f"Worker: Got operation from queue: {op_type}")
            _recording_operation_in_progress.set()  # Mark operation as in progress
            try:
                if op_type == "start":
                    try:
                        logger.info("Worker: Processing start recording operation from queue")
                        result = start_recording(device, mode=mode)
                        # Update optimistic state based on result
                        if result:
                            # Success - optimistic state was correct, just clear pending flag
                            ms._optimistic_recording_state['pending_start'] = False
                            ms._optimistic_recording_state['pending_stop'] = False  # Clear any pending stop
                            if ms._recording_state_machine is not None:
                                ms._recording_state_machine.on_start_success()
                            logger.info("Worker: Recording started successfully")
                        else:
                            # Failed - revert optimistic state
                            ms._optimistic_recording_state['is_recording'] = False
                            ms._optimistic_recording_state['mode'] = None
                            ms._optimistic_recording_state['start_time'] = None
                            ms._optimistic_recording_state['pending_start'] = False
                            ms._optimistic_recording_state['pending_stop'] = False
                            if ms._recording_state_machine is not None:
                                ms._recording_state_machine.on_start_failure("start_recording() returned False")
                            logger.warning("Worker: Recording start failed")
                    except Exception as e:
                        error_msg = str(e)
                        if ms._recording_state_machine is not None:
                            ms._recording_state_machine.on_start_failure(error_msg)
                        logger.warning(f"Failed to start recording in background: {e}", exc_info=True)
                elif op_type == "stop":
                    # ROBUST STOP: Always kill arecord processes, regardless of state
                    logger.info("Worker: Processing stop recording operation from queue - ROBUST MODE")
                    import menu_settings as ms
                    import time
                    import subprocess
                    
                    # Step 1: Get device from config (non-blocking)
                    config = None
                    audio_device = None
                    try:
                        config = load_config()
                        audio_device = config.get("audio_device", "")
                    except Exception as e:
                        logger.warning(f"Worker: Could not load config for stop: {e}")
                    
                    # Step 2: Call stop_recording() first (handles state cleanup)
                    result = False
                    try:
                        logger.info("Worker: Calling stop_recording()...")
                        result = stop_recording()
                        logger.info(f"Worker: stop_recording() returned: {result}")
                    except Exception as e:
                        logger.error(f"Worker: stop_recording() raised exception: {e}", exc_info=True)
                    
                    # Step 3: ALWAYS kill arecord processes, regardless of stop_recording() result
                    # This ensures recording stops even if state is out of sync
                    if audio_device:
                        logger.info(f"Worker: Aggressively killing all arecord processes for {audio_device}")
                        try:
                            # Kill zombie processes (this is the most reliable way)
                            ms._recording_manager._kill_zombie_arecord_processes(audio_device)
                            
                            # Clear ALL state (both actual and cached) after killing
                            with ms._recording_manager._lock:
                                ms._recording_manager._is_recording = False
                                ms._recording_manager._recording_process = None
                                ms._recording_manager._recording_filename = None
                                ms._recording_manager._recording_start_time = None
                                ms._recording_manager._recording_mode = None
                                ms._recording_manager._cached_is_recording = False
                                ms._recording_manager._cached_mode = None
                                ms._recording_manager._cached_start_time = None
                                logger.info("Worker: Cleared all recording state (actual + cached)")
                            
                            # Wait a moment for processes to die
                            time.sleep(0.15)
                            
                            # Double-check: verify no arecord processes remain
                            try:
                                pgrep_result = subprocess.run(
                                    ["pgrep", "-f", f"arecord.*-D.*{audio_device}"], 
                                    capture_output=True, 
                                    timeout=0.2
                                )
                                if pgrep_result.returncode == 0 and pgrep_result.stdout.strip():
                                    pids = pgrep_result.stdout.decode().strip().split('\n')
                                    logger.warning(f"Worker: Still found {len(pids)} arecord process(es) after kill: {pids}")
                                    # Kill again more aggressively
                                    ms._recording_manager._kill_zombie_arecord_processes(audio_device)
                                    time.sleep(0.1)
                                    # Final check
                                    pgrep_result2 = subprocess.run(
                                        ["pgrep", "-f", f"arecord.*-D.*{audio_device}"], 
                                        capture_output=True, 
                                        timeout=0.2
                                    )
                                    if pgrep_result2.returncode == 0 and pgrep_result2.stdout.strip():
                                        logger.error(f"Worker: arecord processes STILL running after double-kill!")
                                    else:
                                        logger.info("Worker: All arecord processes killed on second attempt")
                                else:
                                    logger.info("Worker: Verified - no arecord processes remain")
                            except Exception as e:
                                logger.warning(f"Worker: Could not verify arecord processes killed: {e}")
                        except Exception as e:
                            logger.error(f"Worker: Error killing arecord processes: {e}", exc_info=True)
                    else:
                        logger.warning("Worker: No audio device configured, cannot kill arecord processes")
                    
                    # Step 4: Update optimistic state to reflect stop
                    try:
                        ms._optimistic_recording_state['is_recording'] = False
                        ms._optimistic_recording_state['mode'] = None
                        ms._optimistic_recording_state['start_time'] = None
                        ms._optimistic_recording_state['pending_stop'] = False
                        ms._optimistic_recording_state['pending_start'] = False
                        logger.info("Worker: Updated optimistic state to 'not recording'")
                    except Exception as e:
                        logger.warning(f"Worker: Could not update optimistic state: {e}")
                    
                    # Step 5: Update state machine
                    if _recording_state_machine is not None:
                        try:
                            _recording_state_machine.on_stop_success()
                            logger.info("Worker: State machine updated to IDLE")
                        except Exception as e:
                            logger.warning(f"Worker: Could not update state machine: {e}")
                    else:
                        logger.warning("Worker: State machine not initialized")
                    
                    # Step 6: Final verification (non-blocking)
                    try:
                        state_after = ms._recording_manager.get_recording_state(blocking=False)
                        logger.info(f"Worker: Final state check: {state_after}")
                    except Exception as e:
                        logger.debug(f"Worker: Could not check final state: {e}")
                    
                    logger.info("Worker: Stop operation COMPLETE - all processes killed, state cleared")
            finally:
                _recording_operation_in_progress.clear()  # Mark operation as complete
            _recording_queue.task_done()
        except Empty:
            # Timeout is normal - just continue the loop
            # Log occasionally to show worker is alive and check for stuck items
            queue_size = _recording_queue.qsize()
            if queue_size > 0:
                logger.error(f"Worker: Queue has {queue_size} item(s) but get() timed out - queue might be corrupted or worker stuck!")
                # Try to get the item without timeout to force processing
                try:
                    operation = _recording_queue.get_nowait()
                    logger.info(f"Worker: Forced get_nowait() succeeded, got: {operation}")
                    # Process it below
                    if operation is None:
                        logger.info("Worker: Received shutdown signal, exiting")
                        break
                    op_type, device, mode = operation
                    logger.info(f"Worker: Got operation from queue (forced): {op_type}")
                    _recording_operation_in_progress.set()
                    # Process the operation - jump to the processing code
                    try:
                        if op_type == "start":
                            try:
                                start_recording(device, mode=mode)
                            except Exception as e:
                                logger.warning(f"Failed to start recording in background: {e}", exc_info=True)
                        elif op_type == "stop":
                            # Use the same robust stop logic as above
                            logger.info("Worker: Processing stop recording operation from queue (forced) - ROBUST MODE")
                            import menu_settings as ms
                            import time
                            import subprocess
                            
                            try:
                                # Get device
                                config = load_config()
                                audio_device = config.get("audio_device", "")
                                
                                # Call stop_recording()
                                result = stop_recording()
                                logger.info(f"Worker: stop_recording() returned: {result}")
                                
                                # Always kill arecord processes
                                if audio_device:
                                    ms._recording_manager._kill_zombie_arecord_processes(audio_device)
                                    with ms._recording_manager._lock:
                                        ms._recording_manager._is_recording = False
                                        ms._recording_manager._recording_process = None
                                        ms._recording_manager._recording_filename = None
                                        ms._recording_manager._recording_start_time = None
                                        ms._recording_manager._recording_mode = None
                                        ms._recording_manager._cached_is_recording = False
                                        ms._recording_manager._cached_mode = None
                                        ms._recording_manager._cached_start_time = None
                                    
                                    # Update optimistic state
                                    ms._optimistic_recording_state['is_recording'] = False
                                    ms._optimistic_recording_state['mode'] = None
                                    ms._optimistic_recording_state['start_time'] = None
                                    ms._optimistic_recording_state['pending_stop'] = False
                                    ms._optimistic_recording_state['pending_start'] = False
                                    
                                    time.sleep(0.15)
                                    
                                    # Verify kill
                                    pgrep_result = subprocess.run(
                                        ["pgrep", "-f", f"arecord.*-D.*{audio_device}"], 
                                        capture_output=True, 
                                        timeout=0.2
                                    )
                                    if pgrep_result.returncode == 0 and pgrep_result.stdout.strip():
                                        logger.warning("Worker: Still found arecord processes, killing again")
                                        ms._recording_manager._kill_zombie_arecord_processes(audio_device)
                            except Exception as e:
                                logger.error(f"Failed to stop recording in background: {e}", exc_info=True)
                                # Even on error, try to kill processes
                                try:
                                    config = load_config()
                                    audio_device = config.get("audio_device", "")
                                    if audio_device:
                                        ms._recording_manager._kill_zombie_arecord_processes(audio_device)
                                except:
                                    pass
                    finally:
                        _recording_operation_in_progress.clear()
                        _recording_queue.task_done()
                    continue  # Continue loop after processing
                except queue_module.Empty:
                    logger.error(f"Worker: get_nowait() also failed - queue is empty but qsize() says {queue_size} - queue state is inconsistent!")
                    continue
            else:
                # Queue is empty, normal timeout - continue
                continue
        except Exception as e:
            logger.error(f"Error in recording worker: {e}", exc_info=True)
            _recording_operation_in_progress.clear()  # Clear on error
            # Continue loop on errors
            continue

# Start background worker thread (only if not already running)
# Use the shared thread from menu_settings so it persists across page navigations
if ms._recording_thread is None or not ms._recording_thread.is_alive():
    ms._recording_thread = threading.Thread(target=_recording_worker, daemon=True)
    ms._recording_thread.start()
    logger.info("Started recording worker thread")
_recording_thread = ms._recording_thread

def _2():
    # Manual record/stop (toggle) - ultra-minimal, completely non-blocking
    # Only queue operation - all state updates happen in worker/display callback
    global audio_device, _recording_thread
    
    # Bug 1 Fix: Check audio_device BEFORE assigning default
    # Only use default if audio_device is empty/None, but still check if device is valid
    if not audio_device:
        # No device configured - can't record
        logger.warning("No audio device configured, cannot start recording")
        return
    
    device = audio_device  # Use configured device, no fallback default
    
    # Check optimistic state to determine action (simple dict read, no blocking)
    is_optimistically_recording = _optimistic_state.get('is_recording', False)
    
    if is_optimistically_recording:
        # User wants to stop - queue operation first, then update optimistic state
        queue_success = False
        try:
            _recording_queue.put_nowait(("stop", None, None))
            queue_success = True
            logger.info("Stop queued successfully")
        except queue_module.Full:
            try:
                _recording_queue.put(("stop", None, None), timeout=0.01)
                queue_success = True
                logger.info("Stop queued (with timeout)")
            except:
                logger.error("Failed to queue stop operation")
        
        # Bug 2 Fix: Only update optimistic state after successful queue operation
        if queue_success:
            import time
            _optimistic_state['is_recording'] = False
            _optimistic_state['mode'] = None
            _optimistic_state['start_time'] = None
            _optimistic_state['pending_stop'] = True
            _optimistic_state['pending_start'] = False
    else:
        # User wants to start - queue operation first, then update optimistic state
        queue_success = False
        try:
            _recording_queue.put_nowait(("start", device, "manual"))
            queue_success = True
            logger.info("Start queued successfully")
        except queue_module.Full:
            try:
                _recording_queue.put(("start", device, "manual"), timeout=0.01)
                queue_success = True
                logger.info("Start queued (with timeout)")
            except:
                logger.error("Failed to queue start operation")
        
        # Bug 2 Fix: Only update optimistic state after successful queue operation
        if queue_success:
            import time
            _optimistic_state['is_recording'] = True
            _optimistic_state['mode'] = "manual"
            _optimistic_state['start_time'] = time.time()
            _optimistic_state['pending_start'] = True
            _optimistic_state['pending_stop'] = False
    
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
        
        # Fallback: If state says not recording, check for arecord processes
        # This handles cases where state is stale but recording is actually active
        # BUT: Only check if cached state also says not recording (to avoid overriding cleared state)
        if not is_currently_recording and device_valid:
            # Check if cached state was intentionally cleared (both False means cleared, not stale)
            try:
                cached_is_recording = ms._recording_manager._cached_is_recording
                # If both actual and cached state say False, trust it (state was intentionally cleared)
                # Only check arecord if cached state is True but actual is False (stale state)
                if cached_is_recording and not is_currently_recording:
                    # Cached says recording but actual says not - might be stale, check arecord
                    try:
                        import subprocess
                        result = subprocess.run(["pgrep", "-f", f"arecord.*-D.*{audio_device}"], 
                                              capture_output=True, timeout=0.1)
                        if result.returncode == 0 and result.stdout.strip():
                            # arecord is running but state says not recording - state is stale
                            logger.debug("State says not recording but arecord process found - using arecord as truth")
                            is_currently_recording = True
                            # Try to get mode from state, default to manual
                            if current_mode is None:
                                current_mode = "manual"
                            # If start_time is None, try to estimate it from file modification time
                            if recording_start_time is None:
                                try:
                                    from pathlib import Path
                                    recordings_dir = Path(ms._recording_manager.recording_dir)
                                    if recordings_dir.exists():
                                        wav_files = list(recordings_dir.glob("recording_*.wav"))
                                        if wav_files:
                                            wav_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                                            most_recent = wav_files[0]
                                            recording_start_time = most_recent.stat().st_mtime
                                except:
                                    pass
                    except:
                        pass  # If pgrep fails, just use the state we got
                # If both cached and actual say False, trust it - don't check arecord
            except:
                pass  # If check fails, just use the state we got
    except Exception as e:
        logger.debug(f"Error getting recording state: {e}")
        is_currently_recording = False
        current_mode = None
        recording_start_time = None
    
    # Use optimistic state for immediate UI feedback, but sync with actual state
    # This provides instant visual feedback while actual state catches up
    optimistic_is_recording = _optimistic_state.get('is_recording', False)
    optimistic_mode = _optimistic_state.get('mode')
    optimistic_start_time = _optimistic_state.get('start_time')
    pending_start = _optimistic_state.get('pending_start', False)
    pending_stop = _optimistic_state.get('pending_stop', False)
    
    # Determine display state: use optimistic if pending, otherwise use actual
    # This gives immediate feedback while operation is in progress
    if pending_start and optimistic_is_recording:
        # Start is pending and optimistic says recording - use optimistic for immediate feedback
        display_is_recording = True
        display_mode = optimistic_mode or "manual"
        display_start_time = optimistic_start_time
    elif pending_stop and not optimistic_is_recording:
        # Stop is pending and optimistic says not recording - use optimistic for immediate feedback
        display_is_recording = False
        display_mode = None
        display_start_time = None
    else:
        # No pending operations or optimistic state matches actual - use actual state
        display_is_recording = is_currently_recording
        display_mode = current_mode
        display_start_time = recording_start_time
        # Sync optimistic state with actual if no pending operations
        if not pending_start and not pending_stop:
            _optimistic_state['is_recording'] = is_currently_recording
            _optimistic_state['mode'] = current_mode
            _optimistic_state['start_time'] = recording_start_time
    
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
