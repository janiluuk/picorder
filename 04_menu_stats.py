#!/usr/bin/env python3
from menu_settings import *
from ui import theme, primitives, nav

################################################################################

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


def _layout_tiles():
    content_y = theme.TOP_BAR_HEIGHT
    content_h = theme.SCREEN_HEIGHT - theme.TOP_BAR_HEIGHT - theme.NAV_BAR_HEIGHT
    padding = theme.PADDING_X
    tile_w = (theme.SCREEN_WIDTH - padding * 3) // 2
    tile_h = (content_h - padding * 3) // 2
    tiles = []
    for row in range(2):
        for col in range(2):
            x = padding + col * (tile_w + padding)
            y = content_y + padding + row * (tile_h + padding)
            tiles.append((x, y, tile_w, tile_h))
    return tiles


def _handle_touch(pos):
    nav_tab = nav.nav_hit_test(pos[0], pos[1])
    if nav_tab:
        return f"nav_{nav_tab}"
    return None


def update_display():
    global screen
    if 'screen' not in globals() or screen is None:
        return

    import pygame

    fonts = theme.get_fonts()
    screen.fill(theme.BG)
    _draw_status_bar(screen, "Stats", get_disk_space())

    tiles = _layout_tiles()
    auto_status = "ON" if get_auto_record_enabled() else "OFF"
    audio_device = get_audio_device()
    device_label = audio_device if audio_device else "None"
    tile_data = [
        ("Battery", "N/A"),
        ("Storage", get_disk_space()),
        ("Input", device_label),
        ("Auto Rec", auto_status),
    ]

    for (rect, (label, value)) in zip(tiles, tile_data):
        primitives.rounded_rect(screen, rect, 10, theme.PANEL, outline=theme.OUTLINE, width=2)
        label_surface = fonts["small"].render(label, True, theme.MUTED)
        value_surface = fonts["medium"].render(value, True, theme.TEXT)
        screen.blit(label_surface, (rect[0] + 10, rect[1] + 10))
        screen.blit(value_surface, (rect[0] + 10, rect[1] + 34))

    nav.draw_nav(screen, "stats")
    pygame.display.update()


screen = init()
update_display()

action_handlers = {
    "nav_home": lambda: go_to_page(PAGE_01),
    "nav_library": lambda: go_to_page(PAGE_05),
    "nav_stats": lambda: None,
    "nav_settings": lambda: go_to_page(PAGE_02),
}

main(update_callback=update_display, touch_handler=_handle_touch, action_handlers=action_handlers)
