"""Shared text layout/painting for floating overlays and their live preview.

The overlay does not use child QLabel widgets: everything is painted on one
translucent widget.  That makes it possible to honour per-run colours, a
custom letter spacing and a real transparent background at the same time.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from .models import DisplayConfig
from .theme import color

TOKEN_RE = re.compile(r"(\{bpm\}|\{heart\}|\{name\}|\{battery\}|\{time\})")
EMOJI_CHARS = "❤♥♡💓💗💙💜🖤🤍💛🧡💚💖💘💝💞💕❥"


@dataclass
class Glyph:
    text: str
    x: float
    color: QColor
    is_heart: bool = False
    font: QFont | None = None


@dataclass
class TextLayout:
    glyphs: list[Glyph] = field(default_factory=list)
    font: QFont | None = None
    content_width: float = 0.0
    content_height: float = 0.0
    box_width: float = 0.0
    box_height: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    baseline: float = 0.0
    outline: float = 0.0
    shadow_margin: float = 0.0


def graphemes(text: str):
    """Split text into user-perceived characters (enough for emoji + CJK)."""
    i = 0
    length = len(text)
    while i < length:
        start = i
        i += 1
        # Surrounding combining marks / variation selectors / skin tones.
        while i < length and _is_extend(text[i]):
            i += 1
        # ZWJ emoji sequences: base + ZWJ + base (+ extensions).
        while i < length and text[i] == "\u200d" and i + 1 < length:
            i += 1
            while i < length and _is_extend(text[i]):
                i += 1
            i += 1
            while i < length and _is_extend(text[i]):
                i += 1
        yield text[start:i]


def _is_extend(char: str) -> bool:
    code = ord(char)
    return (
        unicodedata.combining(char) != 0
        or code == 0xFE0E
        or code == 0xFE0F
        or 0x1F3FB <= code <= 0x1F3FF
        or 0xE0020 <= code <= 0xE007F
    )


def resolve_runs(
    cfg: DisplayConfig,
    bpm: int,
    name: str = "",
    battery: int | None = None,
    connected: bool = True,
) -> list[tuple[str, QColor, bool]]:
    template = cfg.template or "{bpm}"
    value = str(bpm) if (connected and bpm and bpm > 0) else "--"
    display_name = (name or "设备").strip()
    if len(display_name) > 18:
        display_name = display_name[:17] + "…"
    battery_text = f"{battery}%" if battery is not None and battery >= 0 else "—"
    now_text = time.strftime("%H:%M:%S")

    runs: list[tuple[str, QColor, bool]] = []
    for part in TOKEN_RE.split(template):
        if not part:
            continue
        if part == "{bpm}":
            runs.append((value, color(cfg.number_color), False))
        elif part == "{heart}":
            runs.append((cfg.heart_text, color(cfg.heart_color), True))
        elif part == "{name}":
            runs.append((display_name, color(cfg.text_color), False))
        elif part == "{battery}":
            runs.append((battery_text, color(cfg.text_color), False))
        elif part == "{time}":
            runs.append((now_text, color(cfg.text_color), False))
        else:
            # A literal heart typed directly into the template should still use
            # the heart colour and the recolourable heart font.
            buffer = ""
            for cluster in graphemes(part):
                if cluster and cluster[0] in EMOJI_CHARS:
                    if buffer:
                        runs.append((buffer, color(cfg.text_color), False))
                        buffer = ""
                    runs.append((cluster, color(cfg.heart_color), True))
                else:
                    buffer += cluster
            if buffer:
                runs.append((buffer, color(cfg.text_color), False))
    if not runs:
        runs.append((value, color(cfg.number_color), False))
    return runs


def make_font(cfg: DisplayConfig) -> QFont:
    font = QFont(cfg.font_family)
    font.setPixelSize(max(8, int(cfg.font_size)))
    font.setBold(bool(cfg.bold))
    font.setItalic(bool(cfg.italic))
    font.setStyleStrategy(QFont.PreferAntialias)
    try:
        font.setFamilies(
            [
                cfg.font_family,
                "Segoe UI Emoji",
                "Segoe UI Symbol",
                "Microsoft YaHei UI",
                "Segoe UI",
            ]
        )
    except Exception:
        pass
    return font


def make_heart_font(cfg: DisplayConfig, for_emoji: bool = False) -> QFont:
    """Dedicated font for the heart run so a plain ❤ can be recoloured.

    Segoe UI Emoji renders ❤ as a fixed-colour bitmap glyph, which ignores the
    user's heart colour.  Segoe UI Symbol has the same heart as an outline and
    honours the painter's pen; actual emoji (💓, 🖤) keep the emoji font.
    """
    families = (
        ["Segoe UI Emoji", "Segoe UI Symbol", "Segoe UI"]
        if for_emoji
        else ["Segoe UI Symbol", "Segoe UI", "Microsoft YaHei UI"]
    )
    font = QFont(families[0])
    font.setPixelSize(max(8, int(cfg.font_size)))
    font.setBold(bool(cfg.bold))
    font.setItalic(bool(cfg.italic))
    font.setStyleStrategy(QFont.PreferAntialias)
    try:
        font.setFamilies(families)
    except Exception:
        pass
    return font


def _is_color_emoji(text: str) -> bool:
    return any(ord(char) >= 0x1F000 for char in text)


def build_layout(
    cfg: DisplayConfig,
    bpm: int,
    name: str = "",
    battery: int | None = None,
    connected: bool = True,
) -> TextLayout:
    cfg = cfg.normalized()
    font = make_font(cfg)
    metrics = QFontMetricsF(font)
    ascent = metrics.ascent()
    descent = metrics.descent()
    outline = float(cfg.outline_width)
    shadow_margin = max(2.0, cfg.font_size * 0.07) if cfg.shadow_enabled else 0.0

    runs = resolve_runs(cfg, bpm, name, battery, connected)
    glyphs: list[Glyph] = []
    x = 0.0
    count = 0
    for run_text, run_color, is_heart in runs:
        if not run_text:
            continue
        use_emoji = is_heart and _is_color_emoji(run_text)
        run_font = make_heart_font(cfg, use_emoji) if is_heart else font
        run_metrics = QFontMetricsF(run_font)
        ascent = max(ascent, run_metrics.ascent())
        descent = max(descent, run_metrics.descent())
        for cluster in graphemes(run_text):
            width = run_metrics.horizontalAdvance(cluster)
            if width <= 0:
                width = max(1.0, cfg.font_size * 0.25)
            glyphs.append(Glyph(cluster, x, run_color, is_heart, run_font))
            x += width + cfg.letter_spacing
            count += 1
    content_width = max(0.0, x - cfg.letter_spacing) if count else 0.0
    if not glyphs:
        content_width = max(8.0, cfg.font_size * 0.5)

    height = ascent + descent
    outer = cfg.padding + outline + shadow_margin
    box_width = content_width + outer * 2
    box_height = height + outer * 2
    return TextLayout(
        glyphs=glyphs,
        font=font,
        content_width=content_width,
        content_height=height,
        box_width=max(1.0, box_width),
        box_height=max(1.0, box_height),
        ascent=ascent,
        descent=descent,
        baseline=outer + ascent,
        outline=outline,
        shadow_margin=shadow_margin,
    )


def paint_display(
    painter: QPainter,
    cfg: DisplayConfig,
    bpm: int,
    name: str = "",
    battery: int | None = None,
    connected: bool = True,
    rect: QRectF | None = None,
    content_scale: float = 1.0,
) -> TextLayout:
    """Paint the widget content; returns the computed layout.

    ``content_scale`` scales the text block (including padding/outline) while
    keeping the background at the full target rect.  Overlay corner resizing
    uses this so the heart-rate text grows/shrinks with the frame.
    """
    cfg = cfg.normalized()
    layout = build_layout(cfg, bpm, name, battery, connected)
    if rect is None:
        rect = QRectF(0, 0, layout.box_width, layout.box_height)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # Background card.
    if cfg.background_opacity > 0:
        painter.setPen(Qt.NoPen)
        painter.setBrush(color(cfg.background_color, cfg.background_opacity))
        radius = min(cfg.radius, rect.width() / 2, rect.height() / 2)
        painter.drawRoundedRect(rect, radius, radius)

    scale = max(0.1, float(content_scale))
    painter.save()
    painter.translate(rect.center())
    painter.scale(scale, scale)
    board = QRectF(
        -layout.box_width / 2,
        -layout.box_height / 2,
        layout.box_width,
        layout.box_height,
    )

    # Centre the text block in the local coordinate system.
    offset_x = board.left()
    offset_y = board.top()
    pad = cfg.padding + layout.outline + layout.shadow_margin
    painter.setFont(layout.font)

    def draw_at(dx: float, dy: float, pen_color: QColor) -> None:
        painter.setPen(pen_color)
        for glyph in layout.glyphs:
            painter.setFont(glyph.font or layout.font)
            painter.drawText(
                QPointF(offset_x + pad + glyph.x + dx, offset_y + layout.baseline + dy),
                glyph.text,
            )

    # Soft drop shadow.
    if cfg.shadow_enabled and cfg.shadow_opacity > 0:
        drop = max(1.5, cfg.font_size * 0.055)
        shadow = color(cfg.shadow_color, cfg.shadow_opacity)
        draw_at(drop * 0.75, drop, shadow)

    # Outline: draw a halo, then fill the glyphs on top.
    if layout.outline > 0:
        outline_color = color(cfg.outline_color)
        radii = [layout.outline]
        if layout.outline > 1.5:
            radii.append(layout.outline * 0.55)
        for radius in radii:
            for step in range(12):
                angle = math.tau * step / 12.0
                draw_at(math.cos(angle) * radius, math.sin(angle) * radius, outline_color)

    painter.setPen(Qt.NoPen)
    for glyph in layout.glyphs:
        painter.setFont(glyph.font or layout.font)
        painter.setPen(glyph.color)
        painter.drawText(
            QPointF(offset_x + pad + glyph.x, offset_y + layout.baseline),
            glyph.text,
        )

    painter.restore()
    painter.restore()
    return layout


def font_preview(cfg: DisplayConfig) -> QFont:
    return make_font(cfg)


def text_pen(color_value: str, width: float = 1.0) -> QPen:
    pen = QPen(QColor(color_value))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    return pen
