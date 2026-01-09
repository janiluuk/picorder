#!/usr/bin/env python3
from menu_settings import *
import os
from pathlib import Path

################################################################################
# Library menu - Browse and manage recordings

# Get list of recordings
def get_recordings():
    """Get list of all recording files, sorted by modification time (newest first)"""
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
    except Exception as e:
        logger.error(f"Error getting recordings: {e}")
    return recordings

# Scrolling state
scroll_offset = 0
recordings = []
selected_index = 0

# Playback state
playback_process = None
is_playing = False

def refresh_recordings():
    """Refresh the recordings list"""
    global recordings
    recordings = get_recordings()

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
    """Play selected recording"""
    global recordings, selected_index
    if 0 <= selected_index < len(recordings):
        recording = recordings[selected_index]
        file_path = recording['path']
        # Play using aplay (non-blocking)
        try:
            # Use aplay to play the file in background
            Popen(["aplay", str(file_path)], stdout=PIPE, stderr=PIPE)
            logger.info(f"Playing recording: {file_path}")
        except Exception as e:
            logger.error(f"Error playing recording: {e}")

def _4():
    """Delete selected recording"""
    global recordings, selected_index, scroll_offset
    if 0 <= selected_index < len(recordings):
        recording = recordings[selected_index]
        file_path = recording['path']
        try:
            # Delete the file
            file_path.unlink()
            logger.info(f"Deleted recording: {file_path}")
            # Refresh list and adjust selection
            refresh_recordings()
            if selected_index >= len(recordings):
                selected_index = max(0, len(recordings) - 1)
            if scroll_offset >= len(recordings):
                scroll_offset = max(0, len(recordings) - 1)
            update_display()
        except Exception as e:
            logger.error(f"Error deleting recording: {e}")
            update_display()  # Update display even on error

def _5():
    """Back to main menu"""
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
    global screen, names, recordings, scroll_offset, selected_index
    
    # Refresh recordings if empty
    if not recordings:
        refresh_recordings()
    
    # Prepare display
    if len(recordings) == 0:
        names[0] = "Library"
        names[1] = "No recordings"
        names[2] = ""
        names[3] = ""  # Button 3 (not used when no recordings)
        names[4] = ""  # Button 4 (not used when no recordings)
        names[5] = "Back"   # Button 5
        names[6] = "Refresh" # Button 6
    else:
        names[0] = f"Library ({len(recordings)})"
        # Show only 1 recording at a time
        if scroll_offset < len(recordings):
            rec = recordings[scroll_offset]
            # Remove "recording_" prefix from filename for display
            name = rec['name']
            if name.startswith("recording_"):
                name = name[10:]  # Remove "recording_" (10 characters)
            # Truncate filename if too long (now we have more space since prefix is removed)
            if len(name) > 30:
                name = name[:27] + "..."
            # Format: "filename (size MB)"
            size_str = f"{rec['size_mb']:.1f}MB"
            display_text = f"{name} ({size_str})"
            # Highlight selected item
            if scroll_offset == selected_index:
                names[1] = "> " + display_text
            else:
                names[1] = display_text
        else:
            names[1] = ""
        
        names[2] = ""  # Not used (only showing 1 item)
        
        names[3] = "Play"   # Button 3
        names[4] = "Delete" # Button 4
        names[5] = "Back"   # Button 5
        names[6] = "Refresh" # Button 6
    
    # Redraw screen
    screen.fill(black)
    draw_screen_border(screen)
    # Draw: label1 (title), label2 (recording), buttons for Play/Delete (b34), Back (b56)
    # Don't use b12 for up/down - we'll draw small custom buttons instead
    populate_screen(names, screen, b12=False, b34=True, b56=True, label1=True, label2=True, label3=False)
    
    # Draw up/down buttons on the right side - moved up and made bigger
    import pygame
    # Larger button size: 60x40 pixels
    up_button_x = 410
    up_button_y = 30  # Moved up to near the top
    down_button_x = 410
    down_button_y = 75  # Positioned below up button
    
    button_width = 60
    button_height = 40
    
    # Dark orange background color (low contrast, dark)
    dark_orange = (120, 60, 20)  # Dark orange with low brightness
    dark_orange_border = (160, 80, 30)  # Slightly lighter for border
    arrow_color = (200, 150, 100)  # Light orange/beige for arrows (good contrast on dark orange)
    
    # Draw up button (button 1) with dark orange background
    up_rect = pygame.Rect(up_button_x, up_button_y, button_width, button_height)
    pygame.draw.rect(screen, dark_orange, up_rect)
    pygame.draw.rect(screen, dark_orange_border, up_rect, 2)
    # Draw up arrow as a triangle shape
    center_x = up_button_x + button_width // 2
    center_y = up_button_y + button_height // 2
    # Draw triangle pointing up
    up_points = [
        (center_x, center_y - 12),  # Top point
        (center_x - 15, center_y + 8),  # Bottom left
        (center_x + 15, center_y + 8)   # Bottom right
    ]
    pygame.draw.polygon(screen, arrow_color, up_points)
    pygame.draw.polygon(screen, dark_orange_border, up_points, 1)
    
    # Draw down button (button 2) with dark orange background
    down_rect = pygame.Rect(down_button_x, down_button_y, button_width, button_height)
    pygame.draw.rect(screen, dark_orange, down_rect)
    pygame.draw.rect(screen, dark_orange_border, down_rect, 2)
    # Draw down arrow as a triangle shape
    center_x = down_button_x + button_width // 2
    center_y = down_button_y + button_height // 2
    # Draw triangle pointing down
    down_points = [
        (center_x, center_y + 12),  # Bottom point
        (center_x - 15, center_y - 8),  # Top left
        (center_x + 15, center_y - 8)   # Top right
    ]
    pygame.draw.polygon(screen, arrow_color, down_points)
    pygame.draw.polygon(screen, dark_orange_border, down_points, 1)

# Initialize
refresh_recordings()
names = ["Library", "", "", "Play", "Delete", "Back", "Refresh"]

screen = init()
update_display()
main([_1, _2, _3, _4, _5, _6], update_callback=update_display)

