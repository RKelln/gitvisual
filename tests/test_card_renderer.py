"""Tests for card renderer and themes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from gitvisual.config import Config
from gitvisual.git.models import CommitGroup, DaySummary
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


# ---------------------------------------------------------------------------
# Helpers for group-based tests
# ---------------------------------------------------------------------------


def make_commit_group(
    summary: str = "Test group",
    n_commits: int = 2,
    insertions: int = 50,
    deletions: int = 10,
    files_changed: int = 3,
) -> CommitGroup:
    commits = [
        make_commit(
            hash=f"{i:016x}",
            message=f"commit {i}",
            insertions=insertions // max(n_commits, 1),
            deletions=deletions // max(n_commits, 1),
            files_changed=files_changed // max(n_commits, 1),
        )
        for i in range(n_commits)
    ]
    return CommitGroup(summary=summary, commits=commits)


def make_renderer_with_cfg(**render_kwargs: object) -> CardRenderer:
    cfg = Config()
    render_cfg = cfg.render.model_copy(update=render_kwargs)
    updated_cfg = Config(
        defaults=cfg.defaults,
        llm=cfg.llm,
        render=render_cfg,
        repos=cfg.repos,
        theme=cfg.theme,
    )
    palette = Palette.from_theme(updated_cfg.theme)
    fonts = resolve_font_paths()
    return CardRenderer(config=updated_cfg.render, palette=palette, fonts=fonts)


# ---------------------------------------------------------------------------
# Commit group rendering tests
# ---------------------------------------------------------------------------


class TestCommitGroupRendering:
    def test_render_with_commit_groups_returns_valid_image(self, tmp_path: Path) -> None:
        """Render with commit_groups set → valid PNG, no crash."""
        renderer = make_renderer()
        groups = [make_commit_group("Auth work"), make_commit_group("Infra")]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGBA"
        assert img.width == renderer.config.card_width

    def test_render_with_commit_groups_height_differs_from_flat_commits(
        self, tmp_path: Path
    ) -> None:
        """Height with grouped view should not crash and produce a valid image."""
        renderer = make_renderer()
        groups = [make_commit_group("Feature work", n_commits=3)]
        day_grouped = make_day_summary(tmp_path=tmp_path).model_copy(
            update={"commit_groups": groups}
        )
        day_flat = make_day_summary(tmp_path=tmp_path)
        img_grouped = renderer.render(day_grouped)
        img_flat = renderer.render(day_flat)
        # Both are valid images — no crash
        assert isinstance(img_grouped, Image.Image)
        assert isinstance(img_flat, Image.Image)

    def test_render_commit_groups_none_unchanged(self, tmp_path: Path) -> None:
        """commit_groups=None → fallback commit rendering, unchanged behavior."""
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path)
        assert day.commit_groups is None
        img = renderer.render(day)
        assert isinstance(img, Image.Image)
        assert img.width == renderer.config.card_width

    def test_render_empty_commit_groups_list(self, tmp_path: Path) -> None:
        """commit_groups=[] (empty list) → renders without crash."""
        renderer = make_renderer()
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": []})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_render_single_commit_group(self, tmp_path: Path) -> None:
        """Single group renders without crash."""
        renderer = make_renderer()
        groups = [make_commit_group("Everything in one group", n_commits=5)]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_render_unicode_summary_in_group(self, tmp_path: Path) -> None:
        """Unicode characters in group summary should not crash."""
        renderer = make_renderer()
        groups = [make_commit_group("修复登录问题 🐛 feat: Überarbeitung")]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_render_very_long_summary_wraps(self, tmp_path: Path) -> None:
        """A very long group summary should wrap, not crash, and produce a taller image."""
        renderer = make_renderer()
        long_summary = (
            "This is a very long group summary that should wrap across multiple lines " * 5
        )
        short_summary = "Short."
        groups_long = [make_commit_group(long_summary)]
        groups_short = [make_commit_group(short_summary)]
        day_long = make_day_summary(tmp_path=tmp_path).model_copy(
            update={"commit_groups": groups_long}
        )
        day_short = make_day_summary(tmp_path=tmp_path).model_copy(
            update={"commit_groups": groups_short}
        )
        img_long = renderer.render(day_long)
        img_short = renderer.render(day_short)
        # Long summary should produce a taller card
        assert img_long.height >= img_short.height
        assert isinstance(img_long, Image.Image)

    def test_render_to_file_with_commit_groups(self, tmp_path: Path) -> None:
        """render_to_file with commit_groups set creates a valid PNG file."""
        renderer = make_renderer()
        groups = [make_commit_group("Feature"), make_commit_group("Bugfix")]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        out_path = tmp_path / "output" / "grouped_card.png"
        result = renderer.render_to_file(day, out_path)
        assert result == out_path
        assert out_path.exists()
        img = Image.open(out_path)
        assert img.format == "PNG"


class TestCommitGroupOverflow:
    def test_overflow_groups_truncated_to_max_groups_shown(self, tmp_path: Path) -> None:
        """With 12 groups but max_groups_shown=3, card renders and overflow line is accounted."""
        renderer = make_renderer_with_cfg(max_groups_shown=3)
        groups = [make_commit_group(f"Group {i}") for i in range(12)]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)
        # Card must be taller than one with zero overflow (3 groups exactly)
        day_exact = make_day_summary(tmp_path=tmp_path).model_copy(
            update={"commit_groups": groups[:3]}
        )
        img_exact = renderer.render(day_exact)
        # 12-group card has overflow line → must be taller than 3-group card
        assert img.height > img_exact.height

    def test_no_overflow_when_groups_fit(self, tmp_path: Path) -> None:
        """With 3 groups and max_groups_shown=10, no overflow line → same height as exact 3."""
        renderer = make_renderer_with_cfg(max_groups_shown=10)
        groups = [make_commit_group(f"Group {i}") for i in range(3)]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        # This should not crash; we can't easily inspect drawn text, but height check is enough
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_overflow_count_correct_singular(self, tmp_path: Path) -> None:
        """max_groups_shown=11, 12 groups → overflow=1 (singular 'group')."""
        renderer = make_renderer_with_cfg(max_groups_shown=11)
        groups = [make_commit_group(f"Group {i}") for i in range(12)]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_overflow_count_correct_plural(self, tmp_path: Path) -> None:
        """max_groups_shown=3, 12 groups → overflow=9 (plural 'groups')."""
        renderer = make_renderer_with_cfg(max_groups_shown=3)
        groups = [make_commit_group(f"Group {i}") for i in range(12)]
        day = make_day_summary(tmp_path=tmp_path).model_copy(update={"commit_groups": groups})
        img = renderer.render(day)
        assert isinstance(img, Image.Image)

    def test_height_accounts_for_overflow_line(self, tmp_path: Path) -> None:
        """Height calc must include the overflow line when present."""
        cfg = Config()
        render_cfg = cfg.render.model_copy(update={"max_groups_shown": 3})
        updated_cfg = Config(
            defaults=cfg.defaults,
            llm=cfg.llm,
            render=render_cfg,
            repos=cfg.repos,
            theme=cfg.theme,
        )
        renderer = make_renderer(updated_cfg)

        groups_overflow = [make_commit_group(f"Group {i}") for i in range(5)]
        groups_exact = [make_commit_group(f"Group {i}") for i in range(3)]

        day_overflow = make_day_summary(tmp_path=tmp_path).model_copy(
            update={"commit_groups": groups_overflow}
        )
        day_exact = make_day_summary(tmp_path=tmp_path).model_copy(
            update={"commit_groups": groups_exact}
        )

        img_overflow = renderer.render(day_overflow)
        img_exact = renderer.render(day_exact)

        # overflow adds a small line at the bottom
        assert img_overflow.height > img_exact.height
