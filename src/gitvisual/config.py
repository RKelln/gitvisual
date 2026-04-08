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
    model: str = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
    api_key_env: str = "OPENROUTER_API_KEY"
    api_base: str | None = None
    max_tokens: int = 1500  # set to 0 (or negative) to omit max_tokens and let the model decide
    max_tokens_grouping: int = 4096  # set to 0 (or negative) to omit max_tokens for grouping
    timeout: int = 30
    timeout_grouping: int = 120
    json_response_format: bool = True  # set to false for models that don't support response_format=json_object (e.g. many free-tier models)


class RenderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Canvas — width fixed; height expands to fit content
    card_width: int = 1200
    min_card_height: int = 0
    padding: int = 72
    background_opacity: float = 0.3  # PNG alpha for background (0.0-1.0)

    # Typography — see DESIGN.md for rationale
    title_size: int = 88  # date hero
    heading_size: int = 22  # commit messages + stats bar
    text_size: int = 28  # summary body
    small_text_size: int = 16  # repo label, commit meta, file paths
    line_height: int = 44  # summary text line height only

    # Compact vs detailed
    style: str = "compact"  # "compact" | "detailed"
    max_files_shown: int = 12
    max_groups_shown: int = 10

    # Header visibility
    show_date: bool = True  # show the large date hero
    show_repo_name: bool = True  # show repo name; becomes hero when show_date=False

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
model = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"  # prefix tells litellm which provider to use
api_key_env = "OPENROUTER_API_KEY"               # name of the env var holding your key
max_tokens = 1500  # set to 0 to omit max_tokens and let the model decide its own limit
max_tokens_grouping = 4096  # set to 0 to omit max_tokens for the grouping turn
timeout = 30
timeout_grouping = 120  # grouping turn can be slow; give it more time
json_response_format = true  # set to false for models that don't support response_format=json_object (many free-tier models)

[render]
card_width = 1200
min_card_height = 0
padding = 72
background_opacity = 0.3   # 0.0 = fully transparent, 1.0 = fully opaque
style = "compact"        # "compact" | "detailed"
max_files_shown = 12
max_groups_shown = 10    # max commit groups shown; excess rendered as "…and N more groups"
show_date = true         # show the large date hero
show_repo_name = true    # show repo name; becomes hero when show_date = false

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
