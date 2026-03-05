"""Terminal colour themes for RemminaMac."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str; fg: str; cursor: str; header_bg: str
    # 16 ANSI named colours
    black: str; red: str; green: str; yellow: str
    blue: str; magenta: str; cyan: str; white: str
    bright_black: str; bright_red: str; bright_green: str; bright_yellow: str
    bright_blue: str; bright_magenta: str; bright_cyan: str; bright_white: str


THEMES: dict[str, Theme] = {
    "One Dark": Theme(
        "One Dark", "#1e1e1e", "#d4d4d4", "#528bff", "#2b2b2b",
        "#282c34", "#e06c75", "#98c379", "#e5c07b",
        "#61afef", "#c678dd", "#56b6c2", "#abb2bf",
        "#5c6370", "#e06c75", "#98c379", "#e5c07b",
        "#61afef", "#c678dd", "#56b6c2", "#ffffff",
    ),
    "Dracula": Theme(
        "Dracula", "#282a36", "#f8f8f2", "#f8f8f2", "#21222c",
        "#21222c", "#ff5555", "#50fa7b", "#f1fa8c",
        "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
        "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5",
        "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
    ),
    "Solarized Dark": Theme(
        "Solarized Dark", "#002b36", "#839496", "#268bd2", "#073642",
        "#073642", "#dc322f", "#859900", "#b58900",
        "#268bd2", "#d33682", "#2aa198", "#eee8d5",
        "#002b36", "#cb4b16", "#586e75", "#657b83",
        "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
    ),
    "Nord": Theme(
        "Nord", "#2e3440", "#d8dee9", "#88c0d0", "#3b4252",
        "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b",
        "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
        "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b",
        "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
    ),
    "Gruvbox Dark": Theme(
        "Gruvbox Dark", "#282828", "#ebdbb2", "#d4be98", "#3c3836",
        "#282828", "#cc241d", "#98971a", "#d79921",
        "#458588", "#b16286", "#689d6a", "#a89984",
        "#928374", "#fb4934", "#b8bb26", "#fabd2f",
        "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
    ),
}

DEFAULT_THEME = "One Dark"


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def theme_names() -> list[str]:
    return list(THEMES.keys())
