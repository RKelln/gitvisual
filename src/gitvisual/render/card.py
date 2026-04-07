"""Phase 1 card renderer: polished dark-themed data cards via Pillow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gitvisual.config import RenderConfig
from gitvisual.git.models import Commit, DaySummary
from gitvisual.render.components import (
    draw_horizontal_rule,
    load_font,
    wrap_text,
)
from gitvisual.render.themes import FontPaths, Palette

_STATUS_SYMBOL = {
    "Added": "+",
    "Modified": "~",
    "Deleted": "-",
    "Renamed": ">",
    "Copied": "*",
}

_FontT = ImageFont.FreeTypeFont | ImageFont.ImageFont


@dataclass
class FontSet:
    title: _FontT
    heading: _FontT
    text: _FontT
    mono: _FontT
    small: _FontT


class CardRenderer:
    """Renders a DaySummary as a PNG card image."""

    def __init__(self, config: RenderConfig, palette: Palette, fonts: FontPaths) -> None:
        self.config = config
        self.palette = palette
        self.fonts = fonts

    def _load_fonts(self) -> FontSet:
        cfg = self.config
        return FontSet(
            title=load_font(self.fonts.bold, cfg.title_size),
            heading=load_font(self.fonts.bold, cfg.heading_size),
            text=load_font(self.fonts.regular, cfg.text_size),
            mono=load_font(self.fonts.mono, cfg.text_size),
            small=load_font(self.fonts.mono, cfg.small_text_size),
        )

    def _calc_height(self, day: DaySummary, fnt: FontSet) -> int:
        """Estimate total card height from content."""
        cfg = self.config
        pad = cfg.padding
        lh = cfg.line_height

        height = pad  # top padding

        # Title
        height += cfg.title_size + lh

        # Summary block
        if day.summary:
            max_w = cfg.card_width - 2 * pad
            lines = wrap_text(day.summary, fnt.text, max_w)
            height += len(lines) * lh + lh

        # Aggregate stats line + separator
        height += lh * 2 + 8

        if day.is_empty:
            height += lh * 2
        else:
            for commit in day.commits:
                # Commit heading (short hash + message)
                max_w = cfg.card_width - 2 * pad
                msg_lines = wrap_text(commit.message, fnt.heading, max_w)
                height += max(len(msg_lines), 1) * lh + 4
                # Stats line
                height += lh
                # Files (capped)
                shown = min(len(commit.files), cfg.max_files_shown)
                height += shown * (cfg.small_text_size + 4)
                if len(commit.files) > cfg.max_files_shown:
                    height += cfg.small_text_size + 4
                height += lh  # spacer between commits

        height += pad  # bottom padding
        return max(height, cfg.min_card_height)

    def _draw(self, draw: ImageDraw.ImageDraw, day: DaySummary, fnt: FontSet) -> None:
        cfg = self.config
        pal = self.palette
        pad = cfg.padding
        lh = cfg.line_height
        inner_w = cfg.card_width - 2 * pad

        y = pad

        # --- Title ---
        title_text = f"{day.repo_name}  ·  {day.date.strftime('%B %-d, %Y')}"
        draw.text((pad, y), title_text, font=fnt.title, fill=pal.heading)
        y += cfg.title_size + lh

        # --- Summary ---
        if day.summary:
            for line in wrap_text(day.summary, fnt.text, inner_w):
                draw.text((pad, y), line, font=fnt.text, fill=pal.text)
                y += lh
            y += lh // 2

        # --- Aggregate stats ---
        n_commits = len(day.commits)
        stats_parts = [
            (f"{n_commits} commit{'s' if n_commits != 1 else ''}", pal.text),
            ("  ·  ", pal.muted),
            (f"{day.total_files_changed} files", pal.text),
            ("  ·  ", pal.muted),
            (f"+{day.total_insertions}", pal.added),
            ("  ", pal.muted),
            (f"-{day.total_deletions}", pal.removed),
        ]
        x = pad
        for text, color in stats_parts:
            draw.text((x, y), text, font=fnt.heading, fill=color)
            bbox = fnt.heading.getbbox(text)
            x += int(bbox[2] - bbox[0])
        y += lh + 8

        # --- Separator ---
        draw_horizontal_rule(draw, pad, y, inner_w, pal.accent, thickness=2)
        y += lh

        # --- Commits ---
        if day.is_empty:
            draw.text((pad, y), "No commits on this date.", font=fnt.text, fill=pal.muted)
        else:
            for commit in day.commits:
                y = self._draw_commit(draw, commit, fnt, y)

    def _draw_commit(
        self,
        draw: ImageDraw.ImageDraw,
        commit: Commit,
        fnt: FontSet,
        y: int,
    ) -> int:
        cfg = self.config
        pal = self.palette
        pad = cfg.padding
        lh = cfg.line_height
        inner_w = cfg.card_width - 2 * pad

        # Short hash + message
        hash_text = commit.short_hash + "  "
        draw.text((pad, y), hash_text, font=fnt.mono, fill=pal.accent)
        hash_w = int(fnt.mono.getbbox(hash_text)[2])

        msg_w = inner_w - hash_w
        msg_lines = wrap_text(commit.message, fnt.heading, msg_w)
        for i, line in enumerate(msg_lines):
            draw.text((pad + hash_w, y + i * lh), line, font=fnt.heading, fill=pal.text)
        y += max(len(msg_lines), 1) * lh + 4

        # Stats inline
        x = pad + 20
        plus_part = f"+{commit.insertions}"
        draw.text((x, y), plus_part, font=fnt.small, fill=pal.added)
        x += int(fnt.small.getbbox(plus_part)[2]) + 8
        minus_part = f"-{commit.deletions}"
        draw.text((x, y), minus_part, font=fnt.small, fill=pal.removed)
        x += int(fnt.small.getbbox(minus_part)[2]) + 8
        files_part = f"{commit.files_changed} file{'s' if commit.files_changed != 1 else ''}"
        draw.text((x, y), files_part, font=fnt.small, fill=pal.muted)
        y += lh

        # File list (if detailed mode or compact with few files)
        if cfg.style == "detailed" or len(commit.files) <= 5:
            shown = commit.files[: cfg.max_files_shown]
            for fc in shown:
                sym = _STATUS_SYMBOL.get(fc.status, "?")
                sym_color = {
                    "+": pal.added,
                    "-": pal.removed,
                    "~": pal.text,
                    ">": pal.accent,
                    "*": pal.muted,
                }.get(sym, pal.muted)
                path_text = fc.path[:90] + ("…" if len(fc.path) > 90 else "")
                draw.text((pad + 20, y), sym, font=fnt.small, fill=sym_color)
                sym_w = fnt.small.getbbox(sym + " ")[2]
                draw.text((pad + 20 + sym_w + 4, y), path_text, font=fnt.small, fill=pal.muted)
                y += cfg.small_text_size + 4
            overflow = len(commit.files) - cfg.max_files_shown
            if overflow > 0:
                draw.text(
                    (pad + 20, y),
                    f"…and {overflow} more",
                    font=fnt.small,
                    fill=pal.muted,
                )
                y += cfg.small_text_size + 4

        y += lh  # spacer between commits
        return y

    def render(self, day: DaySummary) -> Image.Image:
        """Render DaySummary to a Pillow Image."""
        fnt = self._load_fonts()
        height = self._calc_height(day, fnt)
        img = Image.new("RGBA", (self.config.card_width, height), self.palette.background)
        draw = ImageDraw.Draw(img)
        self._draw(draw, day, fnt)
        return img

    def render_to_file(self, day: DaySummary, output_path: Path) -> Path:
        """Render and save as PNG. Returns the output path."""
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = self.render(day)
        img.save(str(output_path), "PNG")
        return output_path
