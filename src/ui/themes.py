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
    "Tokyo Night": Theme(
        "Tokyo Night", "#1a1b26", "#c0caf5", "#c0caf5", "#16161e",
        "#15161e", "#f7768e", "#9ece6a", "#e0af68",
        "#7aa2f7", "#bb9af7", "#7dcfff", "#a9b1d6",
        "#414868", "#f7768e", "#9ece6a", "#e0af68",
        "#7aa2f7", "#bb9af7", "#7dcfff", "#c0caf5",
    ),
    "Catppuccin Mocha": Theme(
        "Catppuccin Mocha", "#1e1e2e", "#cdd6f4", "#f5e0dc", "#181825",
        "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
        "#89b4fa", "#cba6f7", "#89dceb", "#bac2de",
        "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af",
        "#89b4fa", "#cba6f7", "#89dceb", "#a6adc8",
    ),
    "Monokai": Theme(
        "Monokai", "#272822", "#f8f8f2", "#f8f8f2", "#1e1f1c",
        "#272822", "#f92672", "#a6e22e", "#f4bf75",
        "#66d9e8", "#ae81ff", "#a1efe4", "#f8f8f2",
        "#75715e", "#f92672", "#a6e22e", "#f4bf75",
        "#66d9e8", "#ae81ff", "#a1efe4", "#f9f8f5",
    ),
    "Palenight": Theme(
        "Palenight", "#292d3e", "#a6accd", "#80cbc4", "#252837",
        "#292d3e", "#f07178", "#c3e88d", "#ffcb6b",
        "#82aaff", "#c792ea", "#89ddff", "#d0d0d0",
        "#676e95", "#f07178", "#c3e88d", "#ffcb6b",
        "#82aaff", "#c792ea", "#89ddff", "#ffffff",
    ),
    "Ayu Dark": Theme(
        "Ayu Dark", "#0d1017", "#bfbdb6", "#e6b450", "#131721",
        "#0d1017", "#f07178", "#aad94c", "#ffb454",
        "#59c2ff", "#d2a6ff", "#95e6cb", "#c7c7c7",
        "#4d5566", "#f07178", "#aad94c", "#ffb454",
        "#59c2ff", "#d2a6ff", "#95e6cb", "#f8f8f2",
    ),
    "Solarized Light": Theme(
        "Solarized Light", "#fdf6e3", "#657b83", "#268bd2", "#eee8d5",
        "#073642", "#dc322f", "#859900", "#b58900",
        "#268bd2", "#d33682", "#2aa198", "#eee8d5",
        "#002b36", "#cb4b16", "#586e75", "#657b83",
        "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
    ),
    "One Light": Theme(
        "One Light", "#fafafa", "#383a42", "#526fff", "#f0f0f0",
        "#383a42", "#e45649", "#50a14f", "#c18401",
        "#0184bc", "#a626a4", "#0997b3", "#fafafa",
        "#4f525d", "#e45649", "#50a14f", "#c18401",
        "#0184bc", "#a626a4", "#0997b3", "#ffffff",
    ),
    "GitHub Light": Theme(
        "GitHub Light", "#ffffff", "#24292e", "#0366d6", "#f6f8fa",
        "#24292e", "#d73a49", "#28a745", "#dbab09",
        "#0366d6", "#6f42c1", "#0598bc", "#6a737d",
        "#959da5", "#cb2431", "#22863a", "#b08800",
        "#005cc5", "#5a32a3", "#3192aa", "#d1d5da",
    ),
}

DEFAULT_THEME = "One Dark"


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def theme_names() -> list[str]:
    return list(THEMES.keys())
