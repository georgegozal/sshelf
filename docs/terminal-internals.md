# Terminal internals

## Stack

```
Raw SSH bytes
     │
     ▼
pyte.ByteStream  ──feeds──►  _Screen (pyte.HistoryScreen)
                                    │
                          QTimer (16 ms poll)
                                    │
                             _render() decides strategy
                            /                        \
               Alt-screen mode                  Normal mode
            (vim / htop / less)              (plain shell)
                    │                               │
          Full document clear              Append history rows
          + redraw live buffer             + replace live section
                    │                               │
                    └──────────► QPlainTextEdit document
```

---

## _Screen — the patched pyte HistoryScreen

`_Screen` subclasses `pyte.HistoryScreen` and adds two fixes:

### Fix 1: SGR private kwarg crash

pyte's byte stream dispatcher calls `select_graphic_rendition(*attrs, private=True)` for DEC private CSI sequences ending in `m` (e.g. `\x1b[?1m`). pyte's base `Screen` does not accept the `private` keyword → `TypeError`. The fix accepts and ignores it:

```python
def select_graphic_rendition(self, *attrs: int, private: bool = False) -> None:
    if not private:
        super().select_graphic_rendition(*attrs)
```

### Fix 2: Alt-screen detection

The `in_alt_screen` boolean is set/cleared when the stream processes DECSET/DECRST mode 1049 (the "save cursor and switch to alternate screen" escape used by vim, htop, less, nano, etc.):

```python
def set_mode(self, *modes, private=False):
    super().set_mode(*modes, private=private)
    if private and 1049 in modes:
        self.in_alt_screen = True

def reset_mode(self, *modes, private=False):
    super().reset_mode(*modes, private=private)
    if private and 1049 in modes:
        self.in_alt_screen = False
```

---

## Rendering strategies

### Normal mode (plain shell output)

pyte's `HistoryScreen` keeps a ring buffer of scrolled-off lines in `screen.history.top`. The render loop:

1. **History rows** — appended to the `QPlainTextEdit` document once and never touched again. `_rendered_history` tracks how many have already been written.
2. **Live screen section** — the bottom `screen.lines` rows of the document are replaced on every frame.

This means that terminal output "accumulates" upwards naturally, just like a real terminal.

### Alt-screen mode (vim / htop / less)

When `in_alt_screen` is True, the render loop:

1. Clears the **entire** document.
2. Redraws only the current `screen.buffer` (the 50-line live view).

History rows are never written in this mode, so TUI applications that repeatedly redraw their frames cannot cause frame stacking.

When the application exits alt-screen (e.g. you quit vim), `in_alt_screen` becomes False again and normal incremental rendering resumes.

---

## Row rendering (`_render_row`)

Each terminal row is rendered as a series of **runs** — adjacent cells with identical formatting merged into a single `QTextCharFormat` insertion. This minimises the number of format objects created per frame.

Colour resolution order for each cell:

1. `pyte` colour value → `_pyte_color()`:
   - `"default"` → `_DEFAULT_FG` / `_DEFAULT_BG`
   - Named colour (e.g. `"red"`) → One Dark palette entry
   - Integer → xterm-256 index → `_xterm256()`
   - 3-tuple `(r, g, b)` → direct RGB
   - 6-char hex string → `#RRGGBB`
2. Reverse video (`cell.reverse`) → swap FG and BG
3. Cursor position → `_CURSOR_BG` highlight

---

## PTY resize

`resizeEvent()` calls `_sync_pty_size()`, which:

1. Measures character cell size via `QFontMetrics`.
2. Divides the viewport dimensions to get `cols` and `rows`.
3. Calls `screen.resize(rows, cols)` to update the pyte buffer.
4. Emits `resize_pty(cols, rows)` → `TerminalWidget._on_resize_pty` → `SSHWorker.resize` → paramiko channel `resize_pty`.

This ensures the remote shell always receives an accurate TIOCSWINSZ.

---

## Keyboard handling

`event()` overrides `ShortcutOverride` for all `Ctrl`/`Meta` combinations so Qt's shortcut system doesn't consume them before they reach `keyPressEvent`.

Priority order in `keyPressEvent`:

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | `Cmd+C` / `Ctrl+Shift+C` | Copy selection to clipboard |
| 2 | `Cmd+V` / `Ctrl+Shift+V` | Paste clipboard to SSH channel |
| 3 | `Cmd+=` / `Cmd++` | Font zoom +1pt |
| 4 | `Cmd+-` | Font zoom -1pt |
| 5 | `Cmd+0` | Font zoom reset |
| 6 | `Ctrl+[A-Z]` | Send control byte (`\x01`–`\x1a`) |
| 7 | Arrow / F-keys / etc. | Send VT sequence from `_KEY_MAP` |
| 8 | Enter / Backspace / Tab / Esc | Send their byte equivalents |
| 9 | Printable text | UTF-8 encode and send |

`Ctrl+C` reaches priority 6 and sends `\x03` (SIGINT) to the remote process — this is the correct terminal behaviour. To copy text, use `Cmd+C` (macOS) or `Ctrl+Shift+C`.

---

## Scrollback

`_HISTORY = 2000` lines of scrollback are kept in `pyte.HistoryScreen.history.top`. These are written once to the `QPlainTextEdit` document and are never redrawn, so scrolling through long output is cheap.

In alt-screen mode, scrollback is not accessible (same behaviour as real terminals — vim's output is not in your scrollback).

---

## Font zoom

`_zoom_font(delta)` changes the `QFont` point size and immediately calls `_sync_pty_size()` so the PTY dimensions update to reflect the new character size. Range: 6–36pt. Default: 13pt.
