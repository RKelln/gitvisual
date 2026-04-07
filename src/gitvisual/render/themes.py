"""Color palettes and typography for card rendering."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gitvisual.config import ThemeColors

# Bundled fonts live in assets/fonts/ relative to the package root
_ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "fonts"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class Palette(BaseModel):
    """Resolved RGBA color palette ready for Pillow."""

    model_config = ConfigDict(frozen=True)

    background: tuple[int, int, int, int]
    text: tuple[int, int, int, int]
    heading: tuple[int, int, int, int]
    added: tuple[int, int, int, int]
    removed: tuple[int, int, int, int]
    accent: tuple[int, int, int, int]
    muted: tuple[int, int, int, int]
    subheading: tuple[int, int, int, int]

    @classmethod
    def from_theme(cls, colors: ThemeColors) -> Palette:
        def rgba(h: str) -> tuple[int, int, int, int]:
            r, g, b = _hex_to_rgb(h)
            return (r, g, b, 255)

        return cls(
            background=rgba(colors.background),
            text=rgba(colors.text),
            heading=rgba(colors.heading),
            added=rgba(colors.added),
            removed=rgba(colors.removed),
            accent=rgba(colors.accent),
            muted=rgba(colors.muted),
            subheading=rgba(colors.subheading),
        )


class FontPaths(BaseModel):
    """Resolved font file paths."""

    model_config = ConfigDict(frozen=True)

    regular: Path  # Inter Regular or user override
    bold: Path  # Inter Bold
    mono: Path  # JetBrains Mono Regular or user override
    mono_bold: Path  # JetBrains Mono Bold


def get_bundled_font_paths() -> FontPaths:
    """Return paths to the bundled Inter + JetBrains Mono fonts."""
    return FontPaths(
        regular=_ASSETS_DIR / "Inter-Regular.ttf",
        bold=_ASSETS_DIR / "Inter-Bold.ttf",
        mono=_ASSETS_DIR / "JetBrainsMono-Regular.ttf",
        mono_bold=_ASSETS_DIR / "JetBrainsMono-Bold.ttf",
    )


def resolve_font_paths(
    font_regular: str | None = None,
    font_mono: str | None = None,
) -> FontPaths:
    """Return FontPaths, using overrides where provided and bundled fonts as fallback."""
    bundled = get_bundled_font_paths()
    return FontPaths(
        regular=Path(font_regular) if font_regular else bundled.regular,
        bold=bundled.bold,
        mono=Path(font_mono) if font_mono else bundled.mono,
        mono_bold=bundled.mono_bold,
    )
