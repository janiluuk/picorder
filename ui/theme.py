"""Theme settings for the modern 320x240 UI."""

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
TOP_BAR_HEIGHT = 28
NAV_BAR_HEIGHT = 52

PADDING_X = 10
PADDING_Y = 8
CORNER_RADIUS = 10

BG = (10, 12, 16)
PANEL = (20, 24, 32)
OUTLINE = (40, 52, 68)
ACCENT = (235, 84, 84)
ACCENT_ALT = (96, 196, 124)
TEXT = (232, 238, 244)
MUTED = (140, 150, 165)
MUTED_DARK = (96, 104, 120)

SMALL_FONT_SIZE = 16
MEDIUM_FONT_SIZE = 20
LARGE_FONT_SIZE = 34

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
