"""Icon drawing helpers using pygame primitives."""

import pygame


def draw_icon_record(surface, cx, cy, size, active=False):
    radius = size // 2
    if active:
        # Brighter red when recording
        color = (255, 100, 100)
        # Draw outer glow effect when recording
        pygame.draw.circle(surface, (235, 84, 84), (cx, cy), radius + 2)
        pygame.draw.circle(surface, color, (cx, cy), radius)
        # Draw inner circle to indicate recording
        inner_radius = radius // 3
        pygame.draw.circle(surface, (200, 60, 60), (cx, cy), inner_radius)
    else:
        # Darker red when not recording
        color = (200, 60, 60)
        pygame.draw.circle(surface, color, (cx, cy), radius)
    pygame.draw.circle(surface, (30, 30, 30), (cx, cy), radius, 2)


def draw_icon_stop(surface, cx, cy, size):
    half = size // 2
    rect = pygame.Rect(cx - half, cy - half, size, size)
    pygame.draw.rect(surface, (235, 84, 84), rect)
    pygame.draw.rect(surface, (30, 30, 30), rect, 2)


def draw_icon_list(surface, cx, cy, size):
    line_length = size
    gap = size // 3
    start_x = cx - line_length // 2
    for i in range(3):
        y = cy - gap + i * gap
        pygame.draw.line(surface, (232, 238, 244), (start_x, y), (start_x + line_length, y), 3)


def draw_icon_chart(surface, cx, cy, size):
    bar_width = size // 4
    gap = bar_width // 2
    base_y = cy + size // 2
    heights = [size // 3, size // 2, (size * 2) // 3]
    for i, height in enumerate(heights):
        x = cx - size // 2 + i * (bar_width + gap)
        rect = pygame.Rect(x, base_y - height, bar_width, height)
        pygame.draw.rect(surface, (96, 196, 124), rect)


def draw_icon_gear(surface, cx, cy, size):
    radius = size // 2
    pygame.draw.circle(surface, (232, 238, 244), (cx, cy), radius, 2)
    for angle in range(0, 360, 45):
        rad = angle * 3.14159 / 180
        x = cx + int((radius - 2) * pygame.math.Vector2(1, 0).rotate(angle).x)
        y = cy + int((radius - 2) * pygame.math.Vector2(1, 0).rotate(angle).y)
        pygame.draw.circle(surface, (232, 238, 244), (x, y), 2)
    pygame.draw.circle(surface, (232, 238, 244), (cx, cy), radius // 3, 2)


def draw_icon_play(surface, cx, cy, size):
    half = size // 2
    points = [
        (cx - half // 2, cy - half),
        (cx - half // 2, cy + half),
        (cx + half, cy),
    ]
    pygame.draw.polygon(surface, (96, 196, 124), points)


def draw_icon_power(surface, cx, cy, size):
    radius = size // 2
    pygame.draw.circle(surface, (232, 238, 244), (cx, cy), radius, 2)
    pygame.draw.line(surface, (232, 238, 244), (cx, cy - radius), (cx, cy), 2)


def draw_icon_trash(surface, cx, cy, size):
    half = size // 2
    body = pygame.Rect(cx - half, cy - half + 6, size, size - 6)
    lid = pygame.Rect(cx - half + 2, cy - half, size - 4, 6)
    pygame.draw.rect(surface, (232, 238, 244), body, 2)
    pygame.draw.rect(surface, (232, 238, 244), lid, 2)
    pygame.draw.line(surface, (232, 238, 244), (cx - 4, cy - half + 8), (cx - 4, cy + half - 4), 1)
    pygame.draw.line(surface, (232, 238, 244), (cx + 4, cy - half + 8), (cx + 4, cy + half - 4), 1)
