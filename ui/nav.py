"""Bottom navigation bar helpers."""

import pygame

from ui import theme
from ui import icons
from ui import primitives

NAV_TABS = ["home", "library", "stats", "settings"]
NAV_LABELS = {
    "home": "REC",
    "library": "LIB",
    "stats": "STAT",
    "settings": "SET",
}

NAV_RECT_CACHE = None
LABEL_SURFACES = None


def _build_nav_rects():
    width = theme.SCREEN_WIDTH
    height = theme.NAV_BAR_HEIGHT
    button_width = width // len(NAV_TABS)
    rects = {}
    for idx, tab in enumerate(NAV_TABS):
        rects[tab] = (idx * button_width, theme.SCREEN_HEIGHT - height, button_width, height)
    return rects


def nav_rects():
    global NAV_RECT_CACHE
    if NAV_RECT_CACHE is None:
        NAV_RECT_CACHE = _build_nav_rects()
    return NAV_RECT_CACHE


def nav_hit_test(x, y):
    for tab, rect in nav_rects().items():
        rx, ry, rw, rh = rect
        if rx <= x <= rx + rw and ry <= y <= ry + rh:
            return tab
    return None


def _ensure_labels():
    global LABEL_SURFACES
    if LABEL_SURFACES is not None:
        return LABEL_SURFACES

    fonts = theme.get_fonts()
    LABEL_SURFACES = {
        tab: fonts["small"].render(NAV_LABELS[tab], True, theme.MUTED)
        for tab in NAV_TABS
    }
    return LABEL_SURFACES


def draw_nav(surface, active_tab):
    rects = nav_rects()
    labels = _ensure_labels()
    nav_rect = pygame.Rect(0, theme.SCREEN_HEIGHT - theme.NAV_BAR_HEIGHT, theme.SCREEN_WIDTH, theme.NAV_BAR_HEIGHT)
    primitives.rounded_rect(surface, nav_rect, 0, theme.PANEL, outline=theme.OUTLINE, width=1)

    for tab, rect in rects.items():
        rx, ry, rw, rh = rect
        is_active = tab == active_tab
        icon_cx = rx + rw // 2
        icon_cy = ry + rh // 2 - 8
        label_surface = labels[tab]
        label_x = rx + (rw - label_surface.get_width()) // 2
        label_y = ry + rh - label_surface.get_height() - 6

        if is_active:
            pygame.draw.rect(surface, theme.OUTLINE, pygame.Rect(rx + 2, ry + 2, rw - 4, rh - 4), 2, border_radius=8)

        if tab == "home":
            icons.draw_icon_record(surface, icon_cx, icon_cy, 20, active=is_active)
        elif tab == "library":
            icons.draw_icon_list(surface, icon_cx, icon_cy, 20)
        elif tab == "stats":
            icons.draw_icon_chart(surface, icon_cx, icon_cy, 20)
        elif tab == "settings":
            icons.draw_icon_gear(surface, icon_cx, icon_cy, 20)

        surface.blit(label_surface, (label_x, label_y))
