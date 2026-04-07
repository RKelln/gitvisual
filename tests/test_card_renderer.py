"""Tests for card renderer and themes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from gitvisual.config import Config
from gitvisual.git.models import DaySummary
from gitvisual.render.card import CardRenderer
from gitvisual.render.themes import Palette, _hex_to_rgb, resolve_font_paths
from tests.conftest import make_commit, make_day_summary

# ---------------------------------------------------------------------------
# Theme tests
# ---------------------------------------------------------------------------


class TestHexToRgb:
    @pytest.mark.parametrize(
        "hex_val,expected",
        [
            ("#1e1e28", (30, 30, 40)),
            ("#ffffff", (255, 255, 255)),
            ("#000000", (0, 0, 0)),
            ("#64c8ff", (100, 200, 255)),
            ("#fff", (255, 255, 255)),  # 3-char shorthand
        ],
    )
    def test_conversion(self, hex_val: str, expected: tuple[int, int, int]) -> None:
        assert _hex_to_rgb(hex_val) == expected


class TestPalette:
    def test_from_default_theme(self) -> None:
        config = Config()
        palette = Palette.from_theme(config.theme)
        assert len(palette.background) == 4
        assert palette.background[3] == 255  # fully opaque
        assert palette.added[1] > palette.added[0]  # green: G > R

    def test_background_matches_config(self) -> None:
        config = Config()
        palette = Palette.from_theme(config.theme)
        r, g, b = _hex_to_rgb(config.theme.background)
        assert palette.background[:3] == (r, g, b)


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


def make_renderer(config: Config | None = None) -> CardRenderer:
    cfg = config or Config()
    palette = Palette.from_theme(cfg.theme)
    fonts = resolve_font_paths()  # will use bundled if they exist, else fallback
    return CardRenderer(config=cfg.render, palette=palette, fonts=fonts)


class TestCardRendererOutput:
    def test_render_returns_image(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_image_width_matches_config(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        img = renderer.render(day)
        assert img.width == renderer.config.card_width

    def test_image_min_height_respected(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        img = renderer.render(day)
        assert img.height >= renderer.config.min_card_height

    def test_render_empty_day(self, empty_day: DaySummary) -> None:
        renderer = make_renderer()
        img = renderer.render(empty_day)
        assert isinstance(img, Image.Image)
        assert img.width == renderer.config.card_width

    def test_render_with_summary(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path, summary="Did some great work today.")
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_render_many_commits(self, tmp_path: Path) -> None:
        commits = [make_commit(hash=f"{i:016x}", message=f"commit {i}") for i in range(10)]
        renderer = make_renderer()
        day = make_day_summary(commits=commits, tmp_path=tmp_path)
        img = renderer.render(day)
        # More commits = taller image
        single_day = make_day_summary(tmp_path=tmp_path, commits=[make_commit()])
        single_img = renderer.render(single_day)
        assert img.height >= single_img.height

    def test_render_to_file_creates_png(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        out_path = tmp_path / "output" / "card.png"
        result = renderer.render_to_file(day, out_path)
        assert result == out_path
        assert out_path.exists()
        # Verify it's a valid image
        img = Image.open(out_path)
        assert img.format == "PNG"

    def test_render_to_file_creates_parent_dirs(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        out_path = tmp_path / "deep" / "nested" / "card.png"
        renderer.render_to_file(day, out_path)
        assert out_path.exists()

    def test_detailed_style_renders(self, tmp_path: Path) -> None:
        config = Config()
        render_cfg = config.render.model_copy(update={"style": "detailed"})
        from gitvisual.config import Config as Cfg

        cfg = Cfg(render=render_cfg)
        renderer = make_renderer(cfg)
        day = make_day_summary(tmp_path=tmp_path)
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_image_mode_is_rgba(self, tmp_path: Path) -> None:
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        img = renderer.render(day)
        assert img.mode == "RGBA"
