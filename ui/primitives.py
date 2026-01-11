"""Drawing primitives for the modern UI."""

import pygame


def rounded_rect(surface, rect, radius, fill, outline=None, width=1):
    """Draw a rounded rectangle with optional outline."""
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    if outline:
        pygame.draw.rect(surface, outline, rect, width, border_radius=radius)


def text(surface, string, pos, font, color):
    """Render text at a position."""
    label = font.render(string, True, color)
    surface.blit(label, pos)
    return label


def elide_text(string, max_px, font):
    """Elide text to fit within max_px using the provided font."""
    if font.size(string)[0] <= max_px:
        return string

    ellipsis = "…"
    available = max_px - font.size(ellipsis)[0]
    if available <= 0:
        return ""

    trimmed = string
    while trimmed and font.size(trimmed)[0] > available:
        trimmed = trimmed[:-1]
    return f"{trimmed}{ellipsis}"
