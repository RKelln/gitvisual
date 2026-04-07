"""Phase 1 card renderer: polished dark-themed data cards via Pillow.

Layout and design rationale live in DESIGN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gitvisual.config import RenderConfig
from gitvisual.git.models import Commit, DaySummary
from gitvisual.render.components import (
    draw_horizontal_rule,
    load_font,
    text_width,
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

# ---------------------------------------------------------------------------
# Spacing constants — see DESIGN.md §Spacing Reference
# ---------------------------------------------------------------------------
_REPO_LABEL_GAP = 8  # repo label bottom → date top
_DATE_GAP = 26  # date bottom → summary (or stats if no summary)
_SUMMARY_GAP = 20  # last summary line → stats bar
_STATS_GAP = 16  # stats bar → separator region
_RULE_THICKNESS = 2
_RULE_PAD = 14  # breathing room each side of the rule
_COMMIT_MSG_EXTRA = 6  # last message line → meta line
_COMMIT_GAP = 18  # between commit blocks


@dataclass
class FontSet:
    title: _FontT  # Inter Bold, title_size      — date hero
    heading: _FontT  # Inter Bold, heading_size    — commit messages
    text: _FontT  # Inter Regular, text_size    — summary body
    mono: _FontT  # JetBrains Mono, text_size   — aggregate stats bar
    small: _FontT  # JetBrains Mono, small_size  — repo label, commit meta, file paths


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

    # ------------------------------------------------------------------
    # Height calculation — must stay in sync with _draw
    # ------------------------------------------------------------------

    def _calc_height(self, day: DaySummary, fnt: FontSet) -> int:
        cfg = self.config
        pad = cfg.padding
        lh = cfg.line_height
        inner_w = cfg.card_width - 2 * pad

        y = pad

        # Repo label
        y += cfg.small_text_size + _REPO_LABEL_GAP
        # Date hero
        y += cfg.title_size + _DATE_GAP

        # Summary block
        if day.summary:
            lines = wrap_text(day.summary, fnt.text, inner_w)
            y += len(lines) * lh + _SUMMARY_GAP

        # Aggregate stats bar
        y += cfg.heading_size + _STATS_GAP

        # Separator (pad + rule + pad)
        y += _RULE_PAD + _RULE_THICKNESS + _RULE_PAD

        if day.is_empty:
            y += cfg.text_size + 8
        else:
            for i, commit in enumerate(day.commits):
                meta_h = cfg.small_text_size + 8
                # Message lines
                msg_lh = cfg.heading_size + 4
                msg_lines = wrap_text(commit.message, fnt.heading, inner_w)
                y += max(len(msg_lines), 1) * msg_lh + _COMMIT_MSG_EXTRA
                # Meta line
                y += meta_h
                # File list — detailed mode only
                if cfg.style == "detailed":
                    shown = min(len(commit.files), cfg.max_files_shown)
                    y += shown * (cfg.small_text_size + 4)
                    if len(commit.files) > cfg.max_files_shown:
                        y += cfg.small_text_size + 4
                # Gap between commits (not after the last one)
                if i < len(day.commits) - 1:
                    y += _COMMIT_GAP

        y += pad
        return max(y, cfg.min_card_height)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, draw: ImageDraw.ImageDraw, day: DaySummary, fnt: FontSet) -> None:
        cfg = self.config
        pal = self.palette
        pad = cfg.padding
        lh = cfg.line_height
        inner_w = cfg.card_width - 2 * pad

        y = pad

        # --- Repo label (small, muted, uppercase) ---
        draw.text((pad, y), day.repo_name.upper(), font=fnt.small, fill=pal.muted)
        y += cfg.small_text_size + _REPO_LABEL_GAP

        # --- Date hero ---
        date_text = day.date.strftime("%-d %B %Y")
        draw.text((pad, y), date_text, font=fnt.title, fill=pal.heading)
        y += cfg.title_size + _DATE_GAP

        # --- Summary body ---
        if day.summary:
            for line in wrap_text(day.summary, fnt.text, inner_w):
                draw.text((pad, y), line, font=fnt.text, fill=pal.text)
                y += lh
            y += _SUMMARY_GAP

        # --- Aggregate stats bar (bold Inter, muted — subordinate to date) ---
        n = len(day.commits)
        stats_parts: list[tuple[str, tuple[int, int, int, int]]] = [
            (f"{n} commit{'s' if n != 1 else ''}", pal.text),
            ("  ·  ", pal.muted),
            (f"{day.total_files_changed} files", pal.text),
            ("  ·  ", pal.muted),
            (f"+{day.total_insertions}", pal.muted),
            ("  ", pal.muted),
            (f"-{day.total_deletions}", pal.muted),
        ]
        x = pad
        for part_text, color in stats_parts:
            draw.text((x, y), part_text, font=fnt.heading, fill=color)
            x += text_width(part_text, fnt.heading)
        y += cfg.heading_size + _STATS_GAP

        # --- Separator ---
        y += _RULE_PAD
        draw_horizontal_rule(draw, pad, y, inner_w, pal.accent, thickness=_RULE_THICKNESS)
        y += _RULE_THICKNESS + _RULE_PAD

        # --- Commits ---
        if day.is_empty:
            draw.text((pad, y), "No commits on this date.", font=fnt.text, fill=pal.muted)
        else:
            for i, commit in enumerate(day.commits):
                y = self._draw_commit(draw, commit, fnt, y)
                if i < len(day.commits) - 1:
                    y += _COMMIT_GAP

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
        inner_w = cfg.card_width - 2 * pad
        msg_lh = cfg.heading_size + 4

        # --- Message (dominant: full width, bold) ---
        for line in wrap_text(commit.message, fnt.heading, inner_w):
            draw.text((pad, y), line, font=fnt.heading, fill=pal.text)
            y += msg_lh
        y += _COMMIT_MSG_EXTRA

        # --- Meta: +ins -del · N files (small, mono, de-emphasised) ---
        x = pad
        parts: list[tuple[str, tuple[int, int, int, int]]] = [
            (f"+{commit.insertions}", pal.added),
            ("  ", pal.muted),
            (f"-{commit.deletions}", pal.removed),
            ("  ·  ", pal.muted),
            (f"{commit.files_changed} file{'s' if commit.files_changed != 1 else ''}", pal.muted),
        ]
        for part_text, color in parts:
            draw.text((x, y), part_text, font=fnt.small, fill=color)
            x += text_width(part_text, fnt.small)
        y += cfg.small_text_size + 8

        # --- File list (detailed mode only) ---
        if cfg.style == "detailed":
            shown = commit.files[: cfg.max_files_shown]
            for fc in shown:
                sym = _STATUS_SYMBOL.get(fc.status, "?")
                sym_color: tuple[int, int, int, int] = {
                    "+": pal.added,
                    "-": pal.removed,
                    "~": pal.subheading,
                    ">": pal.accent,
                    "*": pal.muted,
                }.get(sym, pal.muted)
                path_text = fc.path[:90] + ("…" if len(fc.path) > 90 else "")
                draw.text((pad + 20, y), sym, font=fnt.small, fill=sym_color)
                sym_w = text_width(sym + " ", fnt.small)
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

        return y

    def render(self, day: DaySummary) -> Image.Image:
        """Render DaySummary to a Pillow Image."""
        fnt = self._load_fonts()
        height = self._calc_height(day, fnt)
        bg = self.palette.background
        alpha = int(self.config.background_opacity * 255)
        bg_with_alpha = (bg[0], bg[1], bg[2], alpha)
        img = Image.new("RGBA", (self.config.card_width, height), bg_with_alpha)
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
