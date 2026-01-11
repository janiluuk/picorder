"""Theme settings for the modern 320x240 UI."""

# Base dimensions for Raspberry Pi TFT display (320x240)
BASE_SCREEN_WIDTH = 320
BASE_SCREEN_HEIGHT = 240
BASE_TOP_BAR_HEIGHT = 28
BASE_NAV_BAR_HEIGHT = 52
BASE_PADDING_X = 10
BASE_PADDING_Y = 8
BASE_CORNER_RADIUS = 10
BASE_SMALL_FONT_SIZE = 16
BASE_MEDIUM_FONT_SIZE = 20
BASE_LARGE_FONT_SIZE = 34

# Detect if running on desktop (not Raspberry Pi)
def _is_desktop():
    """Detect if running on desktop (not Raspberry Pi)"""
    try:
        import os
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return not ('Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo)
    except (OSError, IOError):
        return True  # Assume desktop if can't detect

# Scale factor for desktop mode (2.5x makes it much bigger but still reasonable)
DESKTOP_SCALE = 2.5 if _is_desktop() else 1.0

# Scaled dimensions
SCREEN_WIDTH = int(BASE_SCREEN_WIDTH * DESKTOP_SCALE)
SCREEN_HEIGHT = int(BASE_SCREEN_HEIGHT * DESKTOP_SCALE)
TOP_BAR_HEIGHT = int(BASE_TOP_BAR_HEIGHT * DESKTOP_SCALE)
NAV_BAR_HEIGHT = int(BASE_NAV_BAR_HEIGHT * DESKTOP_SCALE)

PADDING_X = int(BASE_PADDING_X * DESKTOP_SCALE)
PADDING_Y = int(BASE_PADDING_Y * DESKTOP_SCALE)
CORNER_RADIUS = int(BASE_CORNER_RADIUS * DESKTOP_SCALE)

BG = (10, 12, 16)
PANEL = (20, 24, 32)
OUTLINE = (40, 52, 68)
ACCENT = (235, 84, 84)
ACCENT_ALT = (96, 196, 124)
TEXT = (232, 238, 244)
MUTED = (140, 150, 165)
MUTED_DARK = (96, 104, 120)

# Navigation button colors (for up/down arrows, etc.)
BUTTON_NAV_BG = (120, 60, 20)  # Dark orange background
BUTTON_NAV_BORDER = (160, 80, 30)  # Slightly lighter border
BUTTON_NAV_ARROW = (200, 150, 100)  # Light orange/beige for arrows

SMALL_FONT_SIZE = int(BASE_SMALL_FONT_SIZE * DESKTOP_SCALE)
MEDIUM_FONT_SIZE = int(BASE_MEDIUM_FONT_SIZE * DESKTOP_SCALE)
LARGE_FONT_SIZE = int(BASE_LARGE_FONT_SIZE * DESKTOP_SCALE)

# Icon sizes (scaled for desktop)
BASE_ICON_SIZE_SMALL = 18
BASE_ICON_SIZE_MEDIUM = 20
ICON_SIZE_SMALL = int(BASE_ICON_SIZE_SMALL * DESKTOP_SCALE)
ICON_SIZE_MEDIUM = int(BASE_ICON_SIZE_MEDIUM * DESKTOP_SCALE)

_fonts_cache = None


def get_fonts():
    """Return cached font objects for small/medium/large text."""
    global _fonts_cache
    if _fonts_cache is not None:
        return _fonts_cache

    import pygame
    if not pygame.font.get_init():
        pygame.font.init()

    _fonts_cache = {
        "small": pygame.font.Font(None, SMALL_FONT_SIZE),
        "medium": pygame.font.Font(None, MEDIUM_FONT_SIZE),
        "large": pygame.font.Font(None, LARGE_FONT_SIZE),
    }
    return _fonts_cache
