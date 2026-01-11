#!/usr/bin/env python3
from menu_settings import *
import os
import threading
import subprocess
from subprocess import Popen, PIPE, TimeoutExpired
from pathlib import Path
from datetime import datetime
import re
from ui import theme, primitives, icons, nav

################################################################################
# Library menu - Browse and manage recordings

# Get list of recordings
def get_recordings(force_refresh=False):
    """Get list of all recording files, sorted by modification time (newest first)
    
    PERFORMANCE FIX: Repeated directory scans (#7) - cache results to reduce disk I/O
    
    Args:
        force_refresh: If True, bypass cache and reload from disk
        
    Returns:
        list: List of recording dictionaries
    """
    global _recordings_cache, _recordings_cache_time
    import time as time_module
    
    # Check cache first (unless forcing refresh)
    current_time = time_module.time()
    if not force_refresh and _recordings_cache is not None:
        age = current_time - _recordings_cache_time
        if age < RECORDINGS_CACHE_TTL:
            # Cache is still valid
            return _recordings_cache.copy()  # Return copy to prevent external modification
    
    # Cache expired or forced refresh - scan directory
    recordings = []
    try:
        recording_dir = Path(RECORDING_DIR)
        if recording_dir.exists():
            # Get all .wav files
            for file in recording_dir.glob("*.wav"):
                if file.is_file():
                    # Get file size and modification time
                    stat = file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    mod_time = stat.st_mtime
                    recordings.append({
                        'path': file,
                        'name': file.name,
                        'size_mb': size_mb,
                        'mod_time': mod_time
                    })
            # Sort by modification time (newest first)
            recordings.sort(key=lambda x: x['mod_time'], reverse=True)
    except (OSError, IOError, PermissionError) as e:
        logger.error(f"Error getting recordings: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error getting recordings: {e}", exc_info=True)
    
    # Update cache
    _recordings_cache = recordings.copy()
    _recordings_cache_time = current_time
    
    return recordings

# PERFORMANCE FIX: Repeated directory scans (#7) - cache recordings list
_recordings_cache = None
_recordings_cache_time = 0
RECORDINGS_CACHE_TTL = 2.0  # Cache recordings for 2 seconds

# Scrolling state
scroll_offset = 0
recordings = []
selected_index = 0

# Playback state - thread-safe with lock
# CRITICAL FIX: Use lock to prevent race conditions and ensure proper cleanup
import threading
playback_process = None
is_playing = False
_playback_lock = threading.Lock()
_last_touch_pos = None

# Layout constants (scaled via theme)
ROW_HEIGHT = int(48 * (theme.SCREEN_WIDTH / 320))  # Scale proportionally with screen width
CONTROL_BUTTON_SIZE = int(44 * (theme.SCREEN_WIDTH / 320))
CONTROL_BUTTON_GAP = int(6 * (theme.SCREEN_WIDTH / 320))


def _layout_cache():
    content_y = theme.TOP_BAR_HEIGHT
    content_h = theme.SCREEN_HEIGHT - theme.TOP_BAR_HEIGHT - theme.NAV_BAR_HEIGHT
    content_rect = (0, content_y, theme.SCREEN_WIDTH, content_h)
    list_rect = (
        theme.PADDING_X,
        content_y + 6,
        theme.SCREEN_WIDTH - (theme.PADDING_X * 2) - (CONTROL_BUTTON_SIZE + theme.PADDING_X),
        content_h - 12,
    )
    control_x = theme.SCREEN_WIDTH - theme.PADDING_X - CONTROL_BUTTON_SIZE
    total_control_height = (CONTROL_BUTTON_SIZE * 3) + (CONTROL_BUTTON_GAP * 2)
    start_y = content_y + (content_h - total_control_height) // 2
    up_rect = (control_x, start_y, CONTROL_BUTTON_SIZE, CONTROL_BUTTON_SIZE)
    delete_rect = (control_x, start_y + CONTROL_BUTTON_SIZE + CONTROL_BUTTON_GAP, CONTROL_BUTTON_SIZE, CONTROL_BUTTON_SIZE)
    down_rect = (control_x, start_y + (CONTROL_BUTTON_SIZE + CONTROL_BUTTON_GAP) * 2, CONTROL_BUTTON_SIZE, CONTROL_BUTTON_SIZE)
    return {
        "content": content_rect,
        "list": list_rect,
        "up": up_rect,
        "delete": delete_rect,
        "down": down_rect,
    }


def _point_in_rect(pos, rect):
    x, y = pos
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _draw_status_bar(surface, title, status_text):
    import pygame

    bar_rect = pygame.Rect(0, 0, theme.SCREEN_WIDTH, theme.TOP_BAR_HEIGHT)
    pygame.draw.rect(surface, theme.PANEL, bar_rect)
    pygame.draw.line(surface, theme.OUTLINE, (0, theme.TOP_BAR_HEIGHT - 1), (theme.SCREEN_WIDTH, theme.TOP_BAR_HEIGHT - 1), 1)

    fonts = theme.get_fonts()
    title_surface = fonts["medium"].render(title, True, theme.TEXT)
    surface.blit(title_surface, (theme.PADDING_X, 4))

    status_surface = fonts["small"].render(status_text, True, theme.MUTED)
    status_x = theme.SCREEN_WIDTH - theme.PADDING_X - status_surface.get_width()
    surface.blit(status_surface, (status_x, 6))


def _parse_duration(name):
    # FIX: Regex pattern should use single backslash for digit character class
    # Double backslash was being interpreted as literal backslash instead of \d
    match = re.search(r"(\d{2})m(\d{2})s", name)
    if match:
        return f"{match.group(1)}m{match.group(2)}s"
    return "--m--s"


def _handle_touch(pos):
    global _last_touch_pos
    nav_tab = nav.nav_hit_test(pos[0], pos[1])
    if nav_tab:
        return f"nav_{nav_tab}"

    rects = _layout_cache()
    if _point_in_rect(pos, rects["up"]):
        return "up"
    if _point_in_rect(pos, rects["down"]):
        return "down"
    if _point_in_rect(pos, rects["delete"]):
        return "delete"

    if _point_in_rect(pos, rects["list"]):
        _last_touch_pos = pos
        return "row"
    return None

def _stop_playback_safe():
    """Stop playback safely with lock - ensures proper cleanup"""
    global playback_process, is_playing
    with _playback_lock:
        try:
            if playback_process is not None:
                playback_process.terminate()
                try:
                    playback_process.wait(timeout=0.5)
                except (TimeoutExpired, AttributeError, ProcessLookupError):
                    try:
                        playback_process.kill()
                    except (ProcessLookupError, AttributeError):
                        pass  # Process already dead
                # Close file handles to prevent resource leak
                try:
                    if playback_process.stdout:
                        playback_process.stdout.close()
                    if playback_process.stderr:
                        playback_process.stderr.close()
                except (AttributeError, OSError):
                    pass  # Handles already closed or invalid
                playback_process = None
            is_playing = False
            # Also kill any remaining aplay processes (best effort)
            try:
                import subprocess
                subprocess.run(["pkill", "-f", "aplay"], timeout=0.3, capture_output=True)
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                pass  # pkill not available or failed
        except Exception as e:
            logger.error(f"Error stopping playback: {e}", exc_info=True)
            is_playing = False
            playback_process = None

def refresh_recordings():
    """Refresh the recordings list (forces cache refresh)"""
    global recordings
    recordings = get_recordings(force_refresh=True)

def _1():
    """Up / Previous recording"""
    global scroll_offset, selected_index, recordings
    # Refresh recordings list in case it changed
    if not recordings:
        refresh_recordings()
    if len(recordings) == 0:
        return
    if selected_index > 0:
        selected_index -= 1
        # Adjust scroll if needed (show 1 item per screen)
        if selected_index < scroll_offset:
            scroll_offset = selected_index
    update_display()

def _2():
    """Down / Next recording"""
    global scroll_offset, selected_index, recordings
    # Refresh recordings list in case it changed
    if not recordings:
        refresh_recordings()
    if len(recordings) == 0:
        return
    if selected_index < len(recordings) - 1:
        selected_index += 1
        # Adjust scroll if needed (show 1 item per screen)
        if selected_index >= scroll_offset + 1:
            scroll_offset = selected_index
    update_display()

def _3():
    """Play/Stop selected recording - toggle playback"""
    global recordings, selected_index, playback_process, is_playing, _playback_lock
    
    # Thread-safe check of playback state
    with _playback_lock:
        currently_playing = is_playing
        current_process = playback_process
    
    if currently_playing:
        # Currently playing - stop playback (thread-safe)
        logger.info("Stopping playback")
        _stop_playback_safe()
        update_display()
    else:
        # Not playing - start playback (thread-safe)
        if 0 <= selected_index < len(recordings):
            recording = recordings[selected_index]
            file_path = recording['path']
            try:
                # Stop any existing playback first (thread-safe)
                with _playback_lock:
                    if playback_process is not None:
                        try:
                            playback_process.terminate()
                            playback_process.wait(timeout=0.3)
                        except (TimeoutExpired, AttributeError, ProcessLookupError):
                            try:
                                playback_process.kill()
                            except (ProcessLookupError, AttributeError):
                                pass
                        try:
                            if playback_process.stdout:
                                playback_process.stdout.close()
                            if playback_process.stderr:
                                playback_process.stderr.close()
                        except (AttributeError, OSError):
                            pass
                        playback_process = None
                
                # Start new playback (non-blocking, thread-safe)
                new_process = Popen(["aplay", str(file_path)], stdout=PIPE, stderr=PIPE)
                with _playback_lock:
                    playback_process = new_process
                    is_playing = True
                logger.info(f"Playing recording: {file_path}")
                update_display()
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                logger.error(f"Error playing recording: {e}", exc_info=True)
                with _playback_lock:
                    is_playing = False
                    playback_process = None
            except Exception as e:
                logger.error(f"Unexpected error playing recording: {e}", exc_info=True)
                with _playback_lock:
                    is_playing = False
                    playback_process = None

def _4():
    """Delete selected recording"""
    global recordings, selected_index, scroll_offset
    if 0 <= selected_index < len(recordings):
        recording = recordings[selected_index]
        file_path = recording['path']
        try:
            # Stop playback if playing (thread-safe)
            _stop_playback_safe()
            
            # Delete the file
            file_path.unlink()
            logger.info(f"Deleted recording: {file_path}")
            # PERFORMANCE FIX: Invalidate cache after file deletion
            global _recordings_cache
            _recordings_cache = None
            # Refresh list and adjust selection (force refresh after delete)
            refresh_recordings()
            if selected_index >= len(recordings):
                selected_index = max(0, len(recordings) - 1)
            if scroll_offset >= len(recordings):
                scroll_offset = max(0, len(recordings) - 1)
            update_display()
        except (OSError, PermissionError) as e:
            logger.error(f"Error deleting recording: {e}", exc_info=True)
            update_display()  # Update display even on error
        except Exception as e:
            logger.error(f"Unexpected error deleting recording: {e}", exc_info=True)
            update_display()  # Update display even on error

def _5():
    """Back to main menu"""
    # CRITICAL FIX: Clean up playback process before navigating away
    # This prevents resource leak when user navigates away while playing
    _stop_playback_safe()
    go_to_page(PAGE_01)

def _6():
    """Refresh recordings list"""
    global selected_index, scroll_offset
    refresh_recordings()
    selected_index = 0
    scroll_offset = 0
    update_display()

def update_display():
    """Update display with current recordings list"""
    global screen, recordings, scroll_offset, selected_index, playback_process, is_playing, _playback_lock

    import pygame

    with _playback_lock:
        currently_playing = is_playing
        current_process = playback_process

    if currently_playing and current_process is not None:
        try:
            if current_process.poll() is not None:
                with _playback_lock:
                    is_playing = False
                    try:
                        if playback_process.stdout:
                            playback_process.stdout.close()
                        if playback_process.stderr:
                            playback_process.stderr.close()
                    except (AttributeError, OSError):
                        pass
                    playback_process = None
        except (AttributeError, ProcessLookupError) as e:
            logger.debug(f"Playback process invalid: {e}")
            with _playback_lock:
                is_playing = False
                playback_process = None
        except Exception as e:
            logger.debug(f"Error checking playback process: {e}")
            with _playback_lock:
                is_playing = False
                playback_process = None

    if not recordings:
        refresh_recordings()

    fonts = theme.get_fonts()
    screen.fill(theme.BG)
    _draw_status_bar(screen, "Library", f"{len(recordings)} files")

    rects = _layout_cache()
    list_rect = rects["list"]
    list_x, list_y, list_w, list_h = list_rect
    visible_rows = max(1, list_h // ROW_HEIGHT)

    with _playback_lock:
        display_is_playing = is_playing

    for row in range(visible_rows):
        idx = scroll_offset + row
        row_y = list_y + row * ROW_HEIGHT
        row_rect = (list_x, row_y, list_w, ROW_HEIGHT - 4)

        if idx >= len(recordings):
            break

        rec = recordings[idx]
        name = rec["name"]
        if name.startswith("recording_"):
            name = name[10:]
        duration = _parse_duration(name)
        timestamp = datetime.fromtimestamp(rec["mod_time"]).strftime("%m/%d %H:%M")

        is_selected = idx == selected_index
        row_color = theme.PANEL if is_selected else theme.BG
        primitives.rounded_rect(screen, row_rect, 8, row_color, outline=theme.OUTLINE, width=1)

        icon_cx = list_x + theme.PADDING_X + theme.PADDING_X // 2
        icon_cy = row_y + (ROW_HEIGHT // 2)
        if display_is_playing and is_selected:
            icons.draw_icon_stop(screen, icon_cx, icon_cy, theme.ICON_SIZE_SMALL)
        else:
            icons.draw_icon_play(screen, icon_cx, icon_cy, theme.ICON_SIZE_SMALL)

        text_x = list_x + theme.PADDING_X * 3 + theme.ICON_SIZE_SMALL
        date_text = fonts["small"].render(timestamp, True, theme.MUTED)
        screen.blit(date_text, (text_x, row_y + 6))

        name_text = primitives.elide_text(name, list_w - 80, fonts["small"])
        file_surface = fonts["small"].render(name_text, True, theme.TEXT)
        screen.blit(file_surface, (text_x, row_y + 24))

        duration_surface = fonts["small"].render(duration, True, theme.MUTED)
        duration_x = list_x + list_w - duration_surface.get_width() - 6
        screen.blit(duration_surface, (duration_x, row_y + 16))

    if len(recordings) == 0:
        empty_surface = fonts["medium"].render("No recordings", True, theme.MUTED)
        empty_x = list_x + (list_w - empty_surface.get_width()) // 2
        empty_y = list_y + (list_h - empty_surface.get_height()) // 2
        screen.blit(empty_surface, (empty_x, empty_y))

    for rect_key, icon_draw in [(rects["up"], "up"), (rects["delete"], "delete"), (rects["down"], "down")]:
        rx, ry, rw, rh = rect_key
        primitives.rounded_rect(screen, (rx, ry, rw, rh), 8, theme.PANEL, outline=theme.OUTLINE, width=2)
        if icon_draw == "up":
            pygame.draw.polygon(screen, theme.TEXT, [(rx + rw // 2, ry + 10), (rx + 10, ry + rh - 10), (rx + rw - 10, ry + rh - 10)])
        elif icon_draw == "down":
            pygame.draw.polygon(screen, theme.TEXT, [(rx + 10, ry + 10), (rx + rw - 10, ry + 10), (rx + rw // 2, ry + rh - 10)])
        else:
            icons.draw_icon_trash(screen, rx + rw // 2, ry + rh // 2, theme.ICON_SIZE_MEDIUM)

    nav.draw_nav(screen, "library")

# Initialize
refresh_recordings()

screen = init()
update_display()

def _row_action():
    global selected_index, scroll_offset
    rects = _layout_cache()
    list_x, list_y, list_w, list_h = rects["list"]
    if _last_touch_pos is None:
        return
    _, y = _last_touch_pos
    row = int((y - list_y) // ROW_HEIGHT)
    visible_rows = max(1, list_h // ROW_HEIGHT)
    if row < 0 or row >= visible_rows:
        return
    idx = scroll_offset + row
    if idx >= len(recordings):
        return
    selected_index = idx
    _stop_playback_safe()
    _3()


action_handlers = {
    "nav_home": _5,
    "nav_library": lambda: None,
    "nav_stats": lambda: (_stop_playback_safe(), go_to_page(PAGE_04)),
    "nav_settings": lambda: (_stop_playback_safe(), go_to_page(PAGE_02)),
    "up": _1,
    "down": _2,
    "delete": _4,
    "row": _row_action,
}

main(update_callback=update_display, touch_handler=_handle_touch, action_handlers=action_handlers)
