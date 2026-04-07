"""TOML-based configuration loading with defaults."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CONFIG_DIR = Path("~/.config/gitvisual").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"


class ThemeColors(BaseModel):
    model_config = ConfigDict(frozen=True)

    background: str = "#1e1e28"
    text: str = "#dcdce6"
    heading: str = "#64c8ff"
    added: str = "#64c864"
    removed: str = "#ff6464"
    accent: str = "#b48cff"
    muted: str = "#969696"
    subheading: str = "#c8a0ff"


class LLMConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "openrouter"
    model: str = "openrouter/liquid/lfm-2.5-1.2b-thinking:free"
    api_key_env: str = "OPENROUTER_API_KEY"
    api_base: str | None = None
    max_tokens: int = 1500
    timeout: int = 30


class RenderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Soft 1:1 target; height expands with content
    card_width: int = 1200
    min_card_height: int = 1200
    padding: int = 60
    line_height: int = 28

    # Typography sizes
    title_size: int = 36
    heading_size: int = 22
    text_size: int = 18
    small_text_size: int = 14

    # Compact vs detailed
    style: str = "compact"  # "compact" | "detailed"
    max_files_shown: int = 12

    # Font overrides (None = use bundled fonts)
    font_regular: str | None = None
    font_mono: str | None = None


class ReposConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    scan_dirs: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(
        default_factory=lambda: ["node_modules", "vendor", ".cache", "dist", "build"]
    )


class DefaultsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    output_dir: str = "."
    theme: str = "dark"
    summarize: bool = False  # opt-in to avoid accidental LLM calls


class Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    repos: ReposConfig = Field(default_factory=ReposConfig)
    theme: ThemeColors = Field(default_factory=ThemeColors)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> Config:
    """Load config from TOML file, merging with defaults.

    Falls back gracefully to defaults if the config file doesn't exist.
    """
    path = config_path or CONFIG_PATH

    if not path.exists():
        return Config()

    with open(path, "rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    # Build defaults dict and merge user values on top
    defaults = Config().model_dump()
    merged = _deep_merge(defaults, raw)
    return Config.model_validate(merged)


def get_config_path() -> Path:
    """Return the default config file path."""
    return CONFIG_PATH


def write_example_config(path: Path) -> None:
    """Write an example config.toml to path."""
    content = """\
[defaults]
output_dir = "."
theme = "dark"
summarize = false

[llm]
provider = "openrouter"
model = "openrouter/liquid/lfm-2.5-1.2b-thinking:free"  # prefix tells litellm which provider to use
api_key_env = "OPENROUTER_API_KEY"               # name of the env var holding your key
max_tokens = 1500  # thinking models consume tokens on reasoning before output; needs room
timeout = 30

[render]
card_width = 1200
min_card_height = 1200
padding = 60
style = "compact"        # "compact" | "detailed"
max_files_shown = 12

[repos]
scan_dirs = []
exclude = ["node_modules", "vendor", ".cache", "dist", "build"]

[theme]
background = "#1e1e28"
text      = "#dcdce6"
heading   = "#64c8ff"
added     = "#64c864"
removed   = "#ff6464"
accent    = "#b48cff"
muted     = "#969696"
subheading = "#c8a0ff"
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
