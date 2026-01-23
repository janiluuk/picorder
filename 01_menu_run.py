#!/usr/bin/env python3
from menu_settings import *
import threading
import time
import math
from queue import Queue
import queue as queue_module
import menu_settings as ms
from ui import theme, primitives, icons, nav

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

# Audio level cache for visualizer (updated periodically to avoid blocking UI)
_audio_level_cache = 0.0
_audio_level_cache_time = 0.0
AUDIO_LEVEL_UPDATE_INTERVAL = 0.2  # Update audio level every 200ms (optimized for Raspberry Pi)

def _get_cached_audio_level():
    """Get cached audio level for visualizer (non-blocking)"""
    global _audio_level_cache, _audio_level_cache_time
    current_time = time.time()
    
    # Update cache if it's stale (older than update interval)
    if current_time - _audio_level_cache_time > AUDIO_LEVEL_UPDATE_INTERVAL:
        try:
            audio_device = get_audio_device()
            if audio_device:
                # Get actual audio level (this can block for ~50ms, but only every 100ms)
                _audio_level_cache = get_audio_level(audio_device, sample_duration=0.05)
            else:
                _audio_level_cache = 0.0
        except Exception as e:
            logger.debug(f"Error getting audio level for visualizer: {e}")
            _audio_level_cache = 0.0
        _audio_level_cache_time = current_time
    
    return _audio_level_cache

def _layout_cache():
    content_y = theme.TOP_BAR_HEIGHT
    content_h = theme.SCREEN_HEIGHT - theme.TOP_BAR_HEIGHT - theme.NAV_BAR_HEIGHT
    content_rect = (0, content_y, theme.SCREEN_WIDTH, content_h)
    auto_rect = (theme.PADDING_X, content_y + 10, 130, 44)
    screen_rect = (theme.PADDING_X, content_y + 62, 130, 44)
    record_size = 72
    record_cx = theme.SCREEN_WIDTH - 70
    record_cy = content_y + content_h // 2
    record_rect = (record_cx - record_size // 2, record_cy - record_size // 2, record_size, record_size)
    stop_rect = (theme.SCREEN_WIDTH - theme.PADDING_X - 44, content_y + content_h - 50, 44, 44)
    power_rect = (theme.SCREEN_WIDTH - theme.PADDING_X - 48, content_y + 6, 48, 48)  # Increased from 44 to 48 for better touch target
    wave_rect = (theme.PADDING_X, content_y + 112, 170, 32)
    return {
        "content": content_rect,
        "auto": auto_rect,
        "screen": screen_rect,
        "record": record_rect,
        "stop": stop_rect,
        "power": power_rect,
        "wave": wave_rect,
    }


def _point_in_rect(pos, rect):
    x, y = pos
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _draw_status_bar(surface, title, status_text, mode_state_text=None):
    import pygame

    bar_rect = pygame.Rect(0, 0, theme.SCREEN_WIDTH, theme.TOP_BAR_HEIGHT)
    pygame.draw.rect(surface, theme.PANEL, bar_rect)
    pygame.draw.line(surface, theme.OUTLINE, (0, theme.TOP_BAR_HEIGHT - 1), (theme.SCREEN_WIDTH, theme.TOP_BAR_HEIGHT - 1), 1)

    fonts = theme.get_fonts()
    reserved_right = 96  # Space reserved for status text and icons
    
    # If mode_state_text is provided, show two-line layout with title and subtitle
    if mode_state_text:
        # Draw title on top line (smaller font to fit two lines)
        title_y_offset = 3
        mode_state_y_offset = 15
        title_surface = fonts["small"].render(title, True, theme.TEXT)
        surface.blit(title_surface, (theme.PADDING_X, title_y_offset))
        
        # Draw mode/state text on second line
        mode_surface = fonts["small"].render(mode_state_text, True, theme.MUTED)
        surface.blit(mode_surface, (theme.PADDING_X, mode_state_y_offset))
        
        # Position status text to align with center of two-line layout
        status_y = 9  # Centered between the two lines
    else:
        # Original single-line layout with medium font for title
        max_title_width = theme.SCREEN_WIDTH - (theme.PADDING_X * 2) - reserved_right
        title_text = primitives.elide_text(title, max_title_width, fonts["medium"])
        title_surface = fonts["medium"].render(title_text, True, theme.TEXT)
        surface.blit(title_surface, (theme.PADDING_X, 4))
        
        # Position status text for single-line layout
        status_y = 6

    # Draw status text and icons on the right side
    status_text = primitives.elide_text(status_text, reserved_right, fonts["small"])
    status_surface = fonts["small"].render(status_text, True, theme.MUTED)
    status_x = theme.SCREEN_WIDTH - theme.PADDING_X - status_surface.get_width()

    icon_gap = 6
    icon_size = 12
    battery_x = status_x - icon_size - icon_gap
    storage_x = battery_x - icon_size - icon_gap
    icon_y = 7  # Fixed Y position for icons

    pygame.draw.rect(surface, theme.MUTED, (battery_x, icon_y, icon_size, 8), 1)
    pygame.draw.rect(surface, theme.MUTED, (battery_x + icon_size, icon_y + 2, 2, 4))
    pygame.draw.rect(surface, theme.MUTED, (storage_x, icon_y, icon_size, 8), 1)
    pygame.draw.line(surface, theme.MUTED, (storage_x + 3, icon_y + 2), (storage_x + icon_size - 3, icon_y + 2), 1)

    surface.blit(status_surface, (status_x, status_y))


def _draw_home_content(surface, timer_text, is_recording, auto_enabled):
    import pygame

    rects = _layout_cache()
    content_rect = pygame.Rect(*rects["content"])
    pygame.draw.rect(surface, theme.BG, content_rect)

    fonts = theme.get_fonts()
    timer_color = theme.ACCENT if is_recording else theme.TEXT
    timer_surface = fonts["large"].render(timer_text, True, timer_color)
    surface.blit(timer_surface, (theme.PADDING_X, rects["content"][1] + 8))

    if is_recording:
        badge_rect = pygame.Rect(theme.SCREEN_WIDTH - 92, rects["content"][1] + 8, 64, 24)
        primitives.rounded_rect(surface, badge_rect, 10, theme.ACCENT, outline=theme.OUTLINE, width=2)
        badge_text = fonts["small"].render("REC", True, theme.TEXT)
        surface.blit(
            badge_text,
            (badge_rect.centerx - badge_text.get_width() // 2, badge_rect.centery - badge_text.get_height() // 2),
        )

    # Audio level visualizer - show actual audio signal strength
    wave_rect = rects["wave"]
    wx, wy, ww, wh = wave_rect
    bar_count = 10
    bar_gap = 4
    bar_width = (ww - (bar_count - 1) * bar_gap) // bar_count
    
    # Get audio level for visualizer (use cached value to avoid blocking)
    audio_level = _get_cached_audio_level()
    
    # Create visualizer bars with actual audio levels
    # Use frequency domain-like visualization: spread the level across bars with variation
    for i in range(bar_count):
        # Create a pattern that responds to audio level
        # Each bar represents a different frequency band, scaled by the overall level
        band_factor = (i + 1) / bar_count  # 0.1 to 1.0
        # Add some variation for visual interest, but base it on actual audio level
        base_height = audio_level * band_factor * 0.9  # Scale by level and band
        # Add small random-like variation based on position (creates natural variation)
        variation = abs(math.sin(time.time() * 2 + i * 0.5)) * 0.1 * audio_level
        normalized_height = base_height + variation
        normalized_height = min(1.0, max(0.1, normalized_height))  # Clamp between 0.1 and 1.0
        
        height = int(wh * normalized_height)
        bar_x = wx + i * (bar_width + bar_gap)
        bar_y = wy + (wh - height)
        
        # Color bars based on level (green for low, yellow for medium, red for high)
        if normalized_height > 0.7:
            bar_color = theme.ACCENT  # Red/high
        elif normalized_height > 0.4:
            bar_color = theme.ACCENT_ALT  # Yellow/medium
        else:
            bar_color = theme.MUTED_DARK  # Dark/low
        pygame.draw.rect(surface, bar_color, (bar_x, bar_y, bar_width, height))

    auto_rect = pygame.Rect(*rects["auto"])
    auto_color = theme.ACCENT_ALT if auto_enabled else theme.PANEL
    primitives.rounded_rect(surface, auto_rect, 12, auto_color, outline=theme.OUTLINE, width=2)
    auto_label = "AUTO ON" if auto_enabled else "AUTO OFF"
    auto_text = fonts["small"].render(auto_label, True, theme.TEXT)
    surface.blit(auto_text, (auto_rect.x + 10, auto_rect.y + 12))

    screen_rect = pygame.Rect(*rects["screen"])
    primitives.rounded_rect(surface, screen_rect, 12, theme.PANEL, outline=theme.OUTLINE, width=2)
    screen_label = f"SCREEN {SCREEN_TIMEOUT}s"
    screen_text = fonts["small"].render(screen_label, True, theme.TEXT)
    surface.blit(screen_text, (screen_rect.x + 10, screen_rect.y + 12))

    power_rect = pygame.Rect(*rects["power"])
    primitives.rounded_rect(surface, power_rect, 10, theme.PANEL, outline=theme.OUTLINE, width=2)
    icons.draw_icon_power(surface, power_rect.centerx, power_rect.centery, theme.ICON_SIZE_SMALL)

    record_rect = pygame.Rect(*rects["record"])
    record_center = record_rect.center
    icons.draw_icon_record(surface, record_center[0], record_center[1], record_rect.width, active=is_recording)
    if is_recording:
        stop_text = fonts["small"].render("STOP", True, theme.TEXT)
        surface.blit(stop_text, (record_center[0] - stop_text.get_width() // 2, record_center[1] - stop_text.get_height() // 2))

    stop_rect = pygame.Rect(*rects["stop"])
    stop_fill = theme.ACCENT if is_recording else theme.PANEL
    primitives.rounded_rect(surface, stop_rect, 8, stop_fill, outline=theme.OUTLINE, width=2)
    icons.draw_icon_stop(surface, stop_rect.centerx, stop_rect.centery, theme.ICON_SIZE_SMALL)


def _handle_touch(pos):
    nav_tab = nav.nav_hit_test(pos[0], pos[1])
    if nav_tab:
        return f"nav_{nav_tab}"

    rects = _layout_cache()
    if _point_in_rect(pos, rects["record"]):
        return "record"
    if _point_in_rect(pos, rects["auto"]):
        return "auto"
    if _point_in_rect(pos, rects["screen"]):
        return "screen"
    if _point_in_rect(pos, rects["stop"]):
        return "stop"
    if _point_in_rect(pos, rects["power"]):
        return "power"
    return None


def _stop_any_recording():
    try:
        _recording_queue.put_nowait(("stop", None, None))
    except (queue_module.Full, AttributeError, TypeError) as e:
        if isinstance(e, queue_module.Full):
            logger.warning("Stop queue full - dropping stop operation")
        else:
            try:
                _recording_queue.put(("stop", None, None), timeout=0.01)
            except Exception as e2:
                logger.error(f"Failed to queue stop operation: {e2}")

def update_display():
    """Update display with current recording status"""
    global screen, auto_record_enabled

    if 'screen' not in globals() or screen is None:
        return

    try:
        audio_device = get_audio_device()
        auto_record_enabled = get_auto_record_enabled()
        device_valid = bool(audio_device)
    except Exception as e:
        logger.debug(f"Error getting device config in update_display: {e}")
        audio_device = ""
        auto_record_enabled = False
        device_valid = False

    display_is_recording = False
    display_mode = None
    display_start_time = None

    try:
        import menu_settings as ms
        state = ms._recording_manager.get_recording_state(blocking=False)
        if state:
            display_is_recording = state['is_recording']
            display_mode = state['mode']
            display_start_time = state['start_time']
    except Exception as e:
        logger.debug(f"Error getting recording state: {e}")

    timer_text = "--:--"
    if display_is_recording and display_start_time:
        duration = int(time.time() - display_start_time)
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60
        if hours > 0:
            timer_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            timer_text = f"{minutes:02d}:{seconds:02d}"

    mode_label = "Auto" if auto_record_enabled else "Manual"
    state_label = "Recording" if display_is_recording else "Ready"
    mode_state_text = f"{mode_label} • {state_label}"

    status_text = "MIC 48k" if device_valid else "No Mic"

    import pygame
    try:
        pygame.event.pump()
        screen.fill(theme.BG)
        _draw_status_bar(screen, "Recorder", status_text, mode_state_text)
        _draw_home_content(screen, timer_text, display_is_recording, auto_record_enabled)
        nav.draw_nav(screen, "home")
        pygame.display.update()
        pygame.event.pump()
    except Exception as e:
        logger.debug(f"Error in update_display: {e}")
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
    
    print(f"Initial status: {status}", flush=True)
    update_display()

    pygame.time.wait(300)
    print("Starting main loop...", flush=True)

    action_handlers = {
        "nav_home": lambda: None,
        "nav_library": _4,
        "nav_stats": lambda: go_to_page(PAGE_04),
        "nav_settings": _3,
        "record": _2,
        "auto": _1,
        "screen": _5,
        "power": _5,
        "stop": _stop_any_recording,
    }

    main(update_callback=update_display, touch_handler=_handle_touch, action_handlers=action_handlers)
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
