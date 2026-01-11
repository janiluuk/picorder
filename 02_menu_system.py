#!/usr/bin/env python3
from menu_settings import *

################################################################################
# Settings menu

# Settings page - no need to track device index here anymore
# Device selection is handled in separate page (PAGE_06)

# System info display mode
show_system_info = False

def _1():
    # Navigate to device selection page (button 1)
    global show_system_info
    show_system_info = False  # Reset to normal view when navigating away
    go_to_page(PAGE_06)

def _2():
    # Toggle system info display (button 2)
    global show_system_info
    show_system_info = not show_system_info
    update_display()

def _3():
    # Back to main menu (button 3) or toggle system view
    global show_system_info
    if show_system_info:
        # If showing system info, go back to normal view
        show_system_info = False
        update_display()
    else:
        # Otherwise, go back to main menu
        go_to_page(PAGE_01)

def _4():
    # Back to main menu (button 4 - also back)
    go_to_page(PAGE_01)

def _5():
    # Shutdown (button 5 - not shown in current layout)
    pygame.quit()
    run_cmd("/usr/bin/sudo /sbin/shutdown -h now")
    sys.exit()

def _6():
    # Not used
    pass

def update_display():
    """Update display with current settings"""
    global screen, names, show_system_info
    
    if show_system_info:
        # System info view - show IP address and free space
        ip_address = get_ip()
        disk_space = get_disk_space()
        
        # Format IP address (remove leading space if present, ensure "IP:" prefix)
        ip_display = ip_address.strip() if ip_address else "Not connected"
        if ip_display != "Not connected" and not ip_display.startswith("IP:"):
            ip_display = f"IP: {ip_display}"
        
        names[0] = "⚙️ System Info"
        names[1] = ip_display
        names[2] = disk_space
        names[3] = "← Back"
        names[4] = ""
        names[5] = ""
        names[6] = ""
        
        button_colors = {}
        
        # Redraw screen
        screen.fill(black)
        draw_screen_border(screen)
        # Draw: label1 (title), label2 (IP), label3 (disk space), Back button (b34)
        populate_screen(names, screen, b12=False, b34=True, b56=False, label1=True, label2=True, label3=True, button_colors=button_colors)
    else:
        # Normal settings view
        # Get current device configuration with validation
        config, audio_device, auto_record_enabled, device_valid = get_current_device_config()
        
        # Get current device name for display
        audio_devices = get_audio_devices()
        device_name = "None"
        for dev_id, dev_name in audio_devices:
            if dev_id == audio_device:
                device_name = dev_name
                break
        
        # Truncate device name if too long
        if len(device_name) > 20:
            device_name = device_name[:17] + "..."
        
        # Get disk space
        disk_space = get_disk_space()
        
        # Use symbols for visual engagement
        device_symbol = "🎤" if device_valid else "❌"
        
        names[0] = "⚙️ Settings"
        names[1] = f"{device_symbol} Device"
        names[2] = "💻 System"
        names[3] = "← Back"
        names[4] = ""
        names[5] = ""
        names[6] = ""
        
        # No button colors needed
        button_colors = {}
        
        # Redraw screen
        screen.fill(black)
        draw_screen_border(screen)
        # Draw: label1 (title), buttons for Device and System (b12), Back (b34)
        populate_screen(names, screen, b12=True, b34=True, b56=False, label1=True, label2=False, label3=False, button_colors=button_colors)

# Initialize names - will be updated in update_display()
names = ["⚙️ Settings", "🎤 Device", "💻 System", "← Back", "", "", ""]

screen = init()
update_display()
main([_1, _2, _3, _4, _5, _6], update_callback=update_display)
