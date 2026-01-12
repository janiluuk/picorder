#!/usr/bin/env python3
from menu_settings import *
from ui import theme, primitives, icons, nav

################################################################################
# Settings menu

# Settings page - no need to track device index here anymore
# Device selection is handled in separate page (PAGE_06)

# System info display mode
show_system_info = False

# Initialize device index - find current device in list
audio_devices = get_audio_devices()
current_device_index = 0
config = load_config()
current_device = config.get("audio_device", "")
for i, (dev, name) in enumerate(audio_devices):
    if dev == current_device:
        current_device_index = i
        break


def _1():
    # Select audio device (button 1) - cycle through devices
    global current_device_index, config, audio_device, audio_devices
    # Refresh device list in case devices changed
    audio_devices = get_audio_devices()

    # Ensure we have at least the "None" option
    if len(audio_devices) == 0:
        audio_devices = [("", "None (Disabled)")]
        current_device_index = 0
    else:
        # Find current device in refreshed list to maintain index
        config = load_config()
        current_device = config.get("audio_device", "")
        found = False
        for i, (dev, name) in enumerate(audio_devices):
            if dev == current_device:
                current_device_index = i
                found = True
                break
        if not found:
            current_device_index = 0

    # Cycle to next device
    current_device_index = (current_device_index + 1) % len(audio_devices)
    audio_device = audio_devices[current_device_index][0]
    config = load_config()  # Load fresh config before modifying
    config["audio_device"] = audio_device
    save_config(config)

    # If "None" selected or device invalid, disable auto-record and stop any recordings
    # Skip validation to avoid blocking - just check if device is configured
    if audio_device == "":
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

    # Update display
    update_display()


def _2():
    # Toggle auto-record (button 2)
    global auto_record_enabled, audio_devices, current_device_index
    config = load_config()
    audio_device = config.get("audio_device", "")

    # Can't enable auto-record if no device is selected
    if audio_device == "":
        # No device, can't enable
        return

    # Skip validation to avoid blocking - just check if device is configured
    auto_record_enabled = not config.get("auto_record", False)
    config["auto_record"] = auto_record_enabled
    save_config(config)

    # Start/stop silentjack based on new state
    if auto_record_enabled:
        # auto_record_monitor will handle starting silentjack
        pass
    else:
        stop_silentjack()

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


def _grid_layout():
    content_y = theme.TOP_BAR_HEIGHT
    content_h = theme.SCREEN_HEIGHT - theme.TOP_BAR_HEIGHT - theme.NAV_BAR_HEIGHT
    padding = theme.PADDING_X
    cols = 3
    rows = 2
    cell_w = (theme.SCREEN_WIDTH - padding * (cols + 1)) // cols
    cell_h = (content_h - padding * (rows + 1)) // rows
    rects = []
    for row in range(rows):
        for col in range(cols):
            x = padding + col * (cell_w + padding)
            y = content_y + padding + row * (cell_h + padding)
            rects.append((x, y, cell_w, cell_h))
    return rects


def _draw_status_bar(surface, title, status_text):
    import pygame

    bar_rect = pygame.Rect(0, 0, theme.SCREEN_WIDTH, theme.TOP_BAR_HEIGHT)
    pygame.draw.rect(surface, theme.PANEL, bar_rect)
    pygame.draw.line(surface, theme.OUTLINE, (0, theme.TOP_BAR_HEIGHT - 1), (theme.SCREEN_WIDTH, theme.TOP_BAR_HEIGHT - 1), 1)

    fonts = theme.get_fonts()
    reserved_right = 96
    max_title_width = theme.SCREEN_WIDTH - (theme.PADDING_X * 2) - reserved_right
    title_text = primitives.elide_text(title, max_title_width, fonts["medium"])
    title_surface = fonts["medium"].render(title_text, True, theme.TEXT)
    surface.blit(title_surface, (theme.PADDING_X, 4))

    status_text = primitives.elide_text(status_text, reserved_right, fonts["small"])
    status_surface = fonts["small"].render(status_text, True, theme.MUTED)
    status_x = theme.SCREEN_WIDTH - theme.PADDING_X - status_surface.get_width()
    surface.blit(status_surface, (status_x, 6))


def _handle_touch(pos):
    nav_tab = nav.nav_hit_test(pos[0], pos[1])
    if nav_tab:
        return f"nav_{nav_tab}"

    for idx, rect in enumerate(_grid_layout()):
        x, y, w, h = rect
        if x <= pos[0] <= x + w and y <= pos[1] <= y + h:
            return f"cell_{idx}"
    return None


def update_display():
    """Update display with current settings"""
    global screen, audio_devices, current_device_index

    audio_devices = get_audio_devices()
    if len(audio_devices) == 0:
        audio_devices = [("", "None (Disabled)")]

    # Ensure current_device_index is valid (defensive check)
    # Variable is initialized at module level, but device list may have changed
    if current_device_index >= len(audio_devices):
        current_device_index = 0
    # Also verify the index still points to the current device (device list may have changed)
    config = load_config()
    current_device = config.get("audio_device", "")
    # If current device doesn't match, find it in the list
    if current_device_index < len(audio_devices):
        if audio_devices[current_device_index][0] != current_device:
            # Device list changed - find current device
            for i, (dev, name) in enumerate(audio_devices):
                if dev == current_device:
                    current_device_index = i
                    break
            else:
                # Current device not found in list, default to first
                current_device_index = 0

    device_name = audio_devices[current_device_index][1]
    if len(device_name) > MAX_DEVICE_NAME_LENGTH:
        device_name = device_name[:17] + "..."

    config, audio_device, auto_record_enabled, device_valid = get_current_device_config()
    disk_space = get_disk_space()

    fonts = theme.get_fonts()
    screen.fill(theme.BG)
    _draw_status_bar(screen, "Settings", disk_space)

    labels = [
        ("AUD", device_name),
        ("AUTO", "ON" if auto_record_enabled and device_valid else "OFF"),
        ("STOR", disk_space),
        ("SYS", "Services"),
        ("SCR", f"{SCREEN_TIMEOUT}s"),
        ("INFO", "Stats"),
    ]

    rects = _grid_layout()
    for idx, rect in enumerate(rects):
        primitives.rounded_rect(screen, rect, 10, theme.PANEL, outline=theme.OUTLINE, width=2)
        icon_cx = rect[0] + rect[2] // 2
        icon_cy = rect[1] + rect[3] // 2 - 8

        if idx == 0:
            icons.draw_icon_record(screen, icon_cx, icon_cy, theme.ICON_SIZE_MEDIUM, active=device_valid)
        elif idx == 1:
            icons.draw_icon_chart(screen, icon_cx, icon_cy, theme.ICON_SIZE_MEDIUM)
        elif idx == 2:
            icons.draw_icon_list(screen, icon_cx, icon_cy, theme.ICON_SIZE_MEDIUM)
        elif idx == 3:
            icons.draw_icon_gear(screen, icon_cx, icon_cy, theme.ICON_SIZE_MEDIUM)
        elif idx == 4:
            icons.draw_icon_power(screen, icon_cx, icon_cy, theme.ICON_SIZE_MEDIUM)
        else:
            icons.draw_icon_chart(screen, icon_cx, icon_cy, theme.ICON_SIZE_MEDIUM)

        label, status = labels[idx]
        label_surface = fonts["small"].render(label, True, theme.TEXT)
        label_x = rect[0] + (rect[2] - label_surface.get_width()) // 2
        label_y = rect[1] + rect[3] - label_surface.get_height() - 6
        screen.blit(label_surface, (label_x, label_y))

        status_surface = fonts["small"].render(status, True, theme.MUTED)
        status_x = rect[0] + (rect[2] - status_surface.get_width()) // 2
        screen.blit(status_surface, (status_x, rect[1] + 8))

    nav.draw_nav(screen, "settings")
    pygame.display.update()


screen = init()
update_display()

action_handlers = {
    "nav_home": lambda: go_to_page(PAGE_01),
    "nav_library": lambda: go_to_page(PAGE_05),
    "nav_stats": lambda: go_to_page(PAGE_04),
    "nav_settings": lambda: None,
    "cell_0": _1,
    "cell_1": _2,
    "cell_2": lambda: go_to_page(PAGE_05),
    "cell_3": lambda: go_to_page(PAGE_03),
    "cell_4": lambda: go_to_page(SCREEN_OFF),
    "cell_5": lambda: go_to_page(PAGE_04),
}

main(update_callback=update_display, touch_handler=_handle_touch, action_handlers=action_handlers)
