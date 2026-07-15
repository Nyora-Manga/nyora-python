"""Shared Nyora colour schemes — the single source of truth for the TUI themes
*and* the CLI palette, so ``nyora-cli`` always matches the reader's chosen theme.

Each scheme (ported from nyora-web) is a Material accent with a light and a dark
variant. The accent carries the scheme's identity; the CLI derives its whole
look from it. A persisted theme id is the scheme id, suffixed ``-light`` for the
light appearance (e.g. ``"totoro"`` or ``"sakura-light"``) — the same value the
TUI writes to config via :func:`nyora.config.set_config_theme`.
"""

from __future__ import annotations

#: ``(id, display name, light accent, dark accent)`` — order defines the picker.
SCHEMES: list[tuple[str, str, str, str]] = [
    ("sakura", "Sakura", "#8C4A60", "#FFB1C8"),
    ("totoro", "Totoro", "#3C6090", "#A6C8FF"),
    ("miku", "Miku", "#00696D", "#6FDDE2"),
    ("asuka", "Asuka", "#904A40", "#FFB4A8"),
    ("mion", "Mion", "#3B693A", "#A1D39A"),
    ("rikka", "Rikka", "#68548D", "#D3BBFD"),
    ("mamimi", "Mamimi", "#465D91", "#AFC6FF"),
    ("kanade", "Kanade", "#353543", "#EDEDF2"),
    ("itsuka", "Itsuka", "#974800", "#FFBA8F"),
    ("yuki", "Yuki", "#43474A", "#3B3F42"),
]

DEFAULT_SCHEME = "sakura"

_ACCENTS: dict[str, tuple[str, str]] = {sid: (light, dark) for sid, _n, light, dark in SCHEMES}


def scheme_of(theme_id: str) -> str:
    """The scheme id from a theme id (``"totoro-light"`` -> ``"totoro"``)."""
    return theme_id[:-6] if theme_id.endswith("-light") else theme_id


def is_light(theme_id: str) -> bool:
    """Whether a theme id names the light appearance."""
    return theme_id.endswith("-light")


def accent_for(theme_id: str | None) -> str:
    """Resolve a persisted theme id to its accent hex (falls back to the default).

    Honours the appearance: the light variant for ``*-light`` ids, else the dark
    variant — so the CLI accent tracks exactly what the reader picked.
    """
    tid = theme_id or DEFAULT_SCHEME
    light, dark = _ACCENTS.get(scheme_of(tid), _ACCENTS[DEFAULT_SCHEME])
    return light if is_light(tid) else dark


def _hx(component: float) -> str:
    return f"{max(0, min(255, round(component))):02x}"


def mix(color: str, other: str, t: float) -> str:
    """Blend two ``#rrggbb`` colours: ``t=0`` -> ``color``, ``t=1`` -> ``other``."""
    a, b = color.lstrip("#"), other.lstrip("#")
    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return "#" + _hx(ar + (br - ar) * t) + _hx(ag + (bg - ag) * t) + _hx(ab + (bb - ab) * t)
