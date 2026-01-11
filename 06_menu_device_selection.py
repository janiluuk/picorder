#!/usr/bin/env python3
from menu_settings import *
from ui import theme

################################################################################
# Device Selection menu - Browse and select audio input devices

# Device list state
devices = []
selected_index = 0
scroll_offset = 0

def refresh_devices():
    """Refresh the device list"""
    global devices, selected_index, scroll_offset
    devices = get_audio_devices()
    # Find current device in list
    config = load_config()
    current_device = config.get("audio_device", "")
    for i, (dev, name) in enumerate(devices):
        if dev == current_device:
            selected_index = i
            scroll_offset = i
            break
    else:
        # Current device not found, select first item
        selected_index = 0
        scroll_offset = 0

def _1():
    """Up / Previous device"""
    global scroll_offset, selected_index
    if len(devices) == 0:
        refresh_devices()
    if len(devices) == 0:
        return
    if selected_index > 0:
        selected_index -= 1
        # Adjust scroll if needed (show 1 item per screen)
        if selected_index < scroll_offset:
            scroll_offset = selected_index
    update_display()

def _2():
    """Down / Next device"""
    global scroll_offset, selected_index
    if len(devices) == 0:
        refresh_devices()
    if len(devices) == 0:
        return
    if selected_index < len(devices) - 1:
        selected_index += 1
        # Adjust scroll if needed (show 1 item per screen)
        if selected_index >= scroll_offset + 1:
            scroll_offset = selected_index
    update_display()

def _3():
    """Select current device"""
    global devices, selected_index
    if len(devices) == 0:
        refresh_devices()
    if 0 <= selected_index < len(devices):
        device = devices[selected_index]
        device_id = device[0]
        device_name = device[1]
        
        # Save selected device to config
        config = load_config()
        config["audio_device"] = device_id
        save_config(config)
        
        logger.info(f"Selected audio device: {device_id} ({device_name})")
        
        # If "None" selected or device invalid, disable auto-record and stop any recordings
        if device_id == "":
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
        
        # Update display to show selection
        update_display()

def _4():
    """Not used"""
    pass

def _5():
    """Back to settings menu"""
    go_to_page(PAGE_02)

def _6():
    """Refresh device list"""
    global selected_index, scroll_offset
    refresh_devices()
    update_display()

def update_display():
    """Update display with current device list"""
    global screen, names, devices, scroll_offset, selected_index
    
    # Refresh devices if empty
    if not devices:
        refresh_devices()
    
    # Prepare display
    if len(devices) == 0:
        names[0] = "Input Device"
        names[1] = "No devices"
        names[2] = ""
        names[3] = ""  # Button 3 (not used when no devices)
        names[4] = ""  # Button 4 (not used when no devices)
        names[5] = "Back"   # Button 5
        names[6] = "Refresh" # Button 6
    else:
        names[0] = f"Input Device ({len(devices)})"
        # Show only 1 device at a time
        if scroll_offset < len(devices):
            device = devices[scroll_offset]
            device_name = device[1]
            device_id = device[0]
            
            # Truncate device name if too long
            if len(device_name) > 30:
                device_name = device_name[:27] + "..."
            
            # Format: "device_name" or "device_name (id)"
            if device_id:
                display_text = f"{device_name}"
            else:
                display_text = device_name
            
            # Highlight selected item
            if scroll_offset == selected_index:
                names[1] = "> " + display_text
            else:
                names[1] = display_text
        else:
            names[1] = ""
        
        names[2] = ""  # Not used (only showing 1 item)
        
        # Get current device from config to show selection status
        config = load_config()
        current_device = config.get("audio_device", "")
        current_device_id = devices[selected_index][0] if selected_index < len(devices) else ""
        
        # Button 3: Select (or show "Selected" if already selected)
        if current_device_id == current_device:
            names[3] = "Selected"  # Show "Selected" when current device matches
        else:
            names[3] = "Select"   # Show "Select" when different device
        
        names[4] = ""  # Button 4 (not used)
        names[5] = "Back"   # Button 5
        names[6] = "Refresh" # Button 6
    
    # Redraw screen
    screen.fill(black)
    draw_screen_border(screen)
    
    # Prepare button colors - make Select button green when device is already selected
    button_colors = {}
    config = load_config()
    current_device = config.get("audio_device", "")
    if selected_index < len(devices):
        current_device_id = devices[selected_index][0]
        if current_device_id == current_device:
            button_colors[3] = green  # Green background when device is selected
    
    # Draw: label1 (title), label2 (device), buttons for Select (b34), Back (b56)
    # Don't use b12 for up/down - we'll draw small custom buttons instead
    populate_screen(names, screen, b12=False, b34=True, b56=True, label1=True, label2=True, label3=False, button_colors=button_colors)
    
    # Draw up/down buttons on the right side - same style as library browser
    import pygame
    # Larger button size: 60x40 pixels
    up_button_x = 410
    up_button_y = 30  # Moved up to near the top
    down_button_x = 410
    down_button_y = 75  # Positioned below up button
    
    button_width = 60
    button_height = 40
    
    # Draw up button (button 1) with navigation button colors from theme
    up_rect = pygame.Rect(up_button_x, up_button_y, button_width, button_height)
    pygame.draw.rect(screen, theme.BUTTON_NAV_BG, up_rect)
    pygame.draw.rect(screen, theme.BUTTON_NAV_BORDER, up_rect, 2)
    # Draw up arrow as a triangle shape
    up_arrow_points = [
        (up_button_x + button_width // 2, up_button_y + 10),  # Top point
        (up_button_x + 15, up_button_y + button_height - 10),  # Bottom left
        (up_button_x + button_width - 15, up_button_y + button_height - 10)  # Bottom right
    ]
    pygame.draw.polygon(screen, theme.BUTTON_NAV_ARROW, up_arrow_points)
    
    # Draw down button (button 2) with navigation button colors from theme
    down_rect = pygame.Rect(down_button_x, down_button_y, button_width, button_height)
    pygame.draw.rect(screen, theme.BUTTON_NAV_BG, down_rect)
    pygame.draw.rect(screen, theme.BUTTON_NAV_BORDER, down_rect, 2)
    # Draw down arrow as a triangle shape
    down_arrow_points = [
        (down_button_x + 15, down_button_y + 10),  # Top left
        (down_button_x + button_width - 15, down_button_y + 10),  # Top right
        (down_button_x + button_width // 2, down_button_y + button_height - 10)  # Bottom point
    ]
    pygame.draw.polygon(screen, theme.BUTTON_NAV_ARROW, down_arrow_points)
    
    pygame.display.update()

# Initialize
refresh_devices()
names = ["Input Device", "", "", "Select", "", "Back", "Refresh"]
screen = init()
update_display()
main([_1, _2, _3, _4, _5, _6], update_callback=update_display)

