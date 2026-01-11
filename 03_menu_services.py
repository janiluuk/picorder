#!/usr/bin/env python3
from menu_settings import *
from ui import theme, primitives, icons, nav

################################################################################

services = ["transmission-daemon"]
service_labels = ["Transmission"]


def _toggle_service():
    c = toggle_service(services[0])
    return c


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


def _layout_rect():
    content_y = theme.TOP_BAR_HEIGHT
    content_h = theme.SCREEN_HEIGHT - theme.TOP_BAR_HEIGHT - theme.NAV_BAR_HEIGHT
    padding = theme.PADDING_X
    rect = (padding, content_y + padding, theme.SCREEN_WIDTH - padding * 2, content_h - padding * 2)
    return rect


def _handle_touch(pos):
    nav_tab = nav.nav_hit_test(pos[0], pos[1])
    if nav_tab:
        return f"nav_{nav_tab}"

    rect = _layout_rect()
    x, y, w, h = rect
    if x <= pos[0] <= x + w and y <= pos[1] <= y + h:
        return "toggle"
    return None


def update_display():
    global screen
    fonts = theme.get_fonts()
    screen.fill(theme.BG)
    _draw_status_bar(screen, "System", get_date())

    rect = _layout_rect()
    is_running = check_service(services[0])
    status = "ON" if is_running else "OFF"
    fill = theme.ACCENT_ALT if is_running else theme.PANEL

    primitives.rounded_rect(screen, rect, 12, fill, outline=theme.OUTLINE, width=2)
    icon_cx = rect[0] + 30
    icon_cy = rect[1] + rect[3] // 2
    icons.draw_icon_list(screen, icon_cx, icon_cy, 20)

    label_surface = fonts["medium"].render(service_labels[0], True, theme.TEXT)
    screen.blit(label_surface, (rect[0] + 60, rect[1] + 20))

    status_surface = fonts["small"].render(f"Status: {status}", True, theme.TEXT)
    screen.blit(status_surface, (rect[0] + 60, rect[1] + 54))

    nav.draw_nav(screen, "settings")
    pygame.display.update()


screen = init()
update_display()

action_handlers = {
    "nav_home": lambda: go_to_page(PAGE_01),
    "nav_library": lambda: go_to_page(PAGE_05),
    "nav_stats": lambda: go_to_page(PAGE_04),
    "nav_settings": lambda: go_to_page(PAGE_02),
    "toggle": lambda: (_toggle_service(), update_display()),
}

main(update_callback=update_display, touch_handler=_handle_touch, action_handlers=action_handlers)
