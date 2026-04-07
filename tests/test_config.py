"""Tests for config loading and defaults."""

from __future__ import annotations

from pathlib import Path

from gitvisual.config import Config, load_config, write_example_config


class TestConfigDefaults:
    def test_default_config_is_valid(self) -> None:
        config = Config()
        assert config.defaults.theme == "dark"
        assert config.defaults.summarize is False
        assert config.llm.provider == "openrouter"
        assert config.render.card_width == 1200
        assert config.render.style == "compact"

    def test_theme_colors_are_hex(self) -> None:
        config = Config()
        for field in ["background", "text", "heading", "added", "removed", "accent", "muted"]:
            value = getattr(config.theme, field)
            assert value.startswith("#"), f"{field} should be hex color"


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.toml")
        assert config == Config()

    def test_partial_override(self, tmp_path: Path) -> None:
        toml = tmp_path / "config.toml"
        toml.write_text('[defaults]\ntheme = "light"\n')
        config = load_config(toml)
        assert config.defaults.theme == "light"
        # Other defaults still intact
        assert config.llm.provider == "openrouter"

    def test_llm_override(self, tmp_path: Path) -> None:
        toml = tmp_path / "config.toml"
        toml.write_text('[llm]\nmodel = "openai/gpt-4o"\nmax_tokens = 500\n')
        config = load_config(toml)
        assert config.llm.model == "openai/gpt-4o"
        assert config.llm.max_tokens == 500
        # Non-overridden keys still default
        assert config.llm.provider == "openrouter"

    def test_render_override(self, tmp_path: Path) -> None:
        toml = tmp_path / "config.toml"
        toml.write_text('[render]\nstyle = "detailed"\ncard_width = 800\n')
        config = load_config(toml)
        assert config.render.style == "detailed"
        assert config.render.card_width == 800

    def test_theme_color_override(self, tmp_path: Path) -> None:
        toml = tmp_path / "config.toml"
        toml.write_text('[theme]\nbackground = "#000000"\n')
        config = load_config(toml)
        assert config.theme.background == "#000000"
        # Other colors unchanged
        assert config.theme.text == Config().theme.text


class TestWriteExampleConfig:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "config.toml"
        write_example_config(path)
        assert path.exists()

    def test_written_config_is_loadable(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_example_config(path)
        config = load_config(path)
        # Should load without errors and match defaults
        assert config.defaults.theme == "dark"
        assert config.llm.provider == "openrouter"
