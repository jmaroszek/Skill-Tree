"""Color math for the app's muted palette, in OKLCH, a perceptually even space.

Lightness and chroma there mean the same thing at every hue, so a treatment
worked out on one color reads alike on another.
"""
import math
import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")

# White text stays on every badge, so a color can only get so light.
MAX_LIGHTNESS = 0.72


def _to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _from_linear(channel):
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def hex_to_oklch(color):
    """(lightness, chroma, hue in radians) of a hex color, or None if it isn't one."""
    match = _HEX.match((color or "").strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    r, g, b = (_to_linear(int(digits[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l_cone = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_cone = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_cone = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    lightness = 0.2104542553 * l_cone + 0.7936177850 * m_cone - 0.0040720468 * s_cone
    a = 1.9779984951 * l_cone - 2.4285922050 * m_cone + 0.4505937099 * s_cone
    b_axis = 0.0259040371 * l_cone + 0.7827717662 * m_cone - 0.8086757660 * s_cone
    return lightness, math.hypot(a, b_axis), math.atan2(b_axis, a)


def _oklch_to_linear(lightness, chroma, hue):
    a, b = chroma * math.cos(hue), chroma * math.sin(hue)
    l_cone = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_cone = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_cone = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l_cone - 3.3077115913 * m_cone + 0.2309699292 * s_cone,
            -1.2684380046 * l_cone + 2.6097574011 * m_cone - 0.3413193965 * s_cone,
            -0.0041960863 * l_cone - 0.7034186147 * m_cone + 1.7076147010 * s_cone)


def oklch_to_hex(lightness, chroma, hue):
    """A hex color, losing chroma rather than hue when sRGB can't show it."""
    lightness = min(max(lightness, 0.0), 1.0)
    for _ in range(32):
        rgb = _oklch_to_linear(lightness, chroma, hue)
        if all(-0.0005 <= channel <= 1.0005 for channel in rgb):
            break
        chroma *= 0.95
    channels = (min(max(_from_linear(max(channel, 0.0)), 0.0), 1.0) for channel in rgb)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in channels)


def muted_like(color, default, curated):
    """``color``, given the treatment that turned ``default`` into ``curated``.

    So ``default`` comes back as exactly ``curated``, and a color near it comes
    back near it. A value that isn't a color gets ``curated``.
    """
    if (color or "").strip().lower() == default.lower():
        return curated
    picked = hex_to_oklch(color)
    if picked is None:
        return curated
    from_l, from_c, from_h = hex_to_oklch(default)
    to_l, to_c, to_h = hex_to_oklch(curated)
    lightness, chroma, hue = picked
    return oklch_to_hex(
        min(lightness + to_l - from_l, max(MAX_LIGHTNESS, to_l)),
        chroma * (to_c / from_c if from_c else 1.0),
        hue + to_h - from_h,
    )
