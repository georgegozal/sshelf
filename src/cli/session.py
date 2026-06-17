"""Interactive SSH session for the CLI.

Connects to a saved connection using the headless paramiko layer (ssh_core)
and runs a raw passthrough loop between the local terminal and the remote
shell. Features:
  - Local terminal title set to [connection-name]
  - Connect banner printed once
  - Best-effort PS1 tag injected into the remote shell prompt
  - Ctrl-G → snippet palette (prompt_toolkit or menu fallback)
  - Ctrl-X → typed snippet picker
  - Both pickers insert the command WITHOUT a trailing newline — user presses Enter
  - SIGWINCH handler (POSIX) keeps remote PTY size in sync with the local terminal
"""

from __future__ import annotations

import os
import signal
import sys
import time

import paramiko

from src.cli.commands import resolve_connection
from src.cli.ptyio import (
    channel_ready,
    exit_raw,
    pause_raw,
    raw_terminal,
    read_stdin_byte,
    resume_raw,
    set_terminal_title,
    write_stdout,
)
from src.protocols import ssh_core
from src.storage.database import Database

# Hotkeys (raw bytes / single character)
_CTRL_G = b"\x07"  # Ctrl-G → palette picker
_CTRL_X = b"\x18"  # Ctrl-X → typed picker


def cmd_connect(ref: str) -> None:
    """Resolve *ref*, open an interactive SSH session, then block until exit."""
    db   = Database()
    conn = resolve_connection(db, ref)

    if conn.protocol != "ssh":
        print(
            f"[sshelf] '{conn.display_name()}' uses protocol '{conn.protocol}'. "
            "CLI connect only supports SSH.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\n── Connecting to {conn.display_name()} ({conn.host}:{conn.effective_port()}) ──\n")

    # Establish the paramiko connection (credentials auto-loaded from keychain)
    try:
        client = ssh_core.establish(conn)
    except paramiko.AuthenticationException as exc:
        print(f"[sshelf] Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except paramiko.SSHException as exc:
        print(f"[sshelf] SSH error: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"[sshelf] Network error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Detect current terminal size
    try:
        ts = os.get_terminal_size()
        cols, rows = ts.columns, ts.lines
    except OSError:
        cols, rows = 220, 50

    chan = client.invoke_shell(term="xterm-256color", width=cols, height=rows)
    chan.setblocking(False)

    # Set local terminal title and print banner (done before raw mode)
    set_terminal_title(f"[{conn.display_name()}]")
    _print_banner(conn)

    # SIGWINCH handler: keep remote PTY size in sync (POSIX only)
    if sys.platform != "win32":
        def _on_resize(sig, frame):  # noqa: ANN001
            try:
                new_ts = os.get_terminal_size()
                chan.resize_pty(width=new_ts.columns, height=new_ts.lines)
            except OSError:
                pass
        signal.signal(signal.SIGWINCH, _on_resize)

    # Inject PS1 tag into the remote shell (best-effort; POSIX remotes)
    _inject_ps1_tag(chan, conn.display_name())

    # Send startup_command if configured on the connection
    if conn.startup_command:
        chan.sendall((conn.startup_command + "\n").encode("utf-8", errors="replace"))

    # Pre-load snippets (refreshed on every picker open)
    snippets: list[dict] = db.all_snippets(conn.id)

    # Run the main raw passthrough loop
    try:
        with raw_terminal():
            snippets = _passthrough_loop(chan, db, conn.id, snippets)
    finally:
        # Always restore the title and clean up
        set_terminal_title("")
        if sys.platform != "win32":
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)
        try:
            chan.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
        print("\n── Session closed ──\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _print_banner(conn) -> None:
    name  = conn.display_name()
    user  = conn.username or ""
    host  = conn.host
    port  = conn.effective_port()
    width = 60
    bar   = "─" * width
    print(f"\033[1m{bar}\033[0m")
    print(f"  Connected to  \033[1;32m{name}\033[0m")
    print(f"  Host          {user}@{host}:{port}")
    print(f"  Ctrl-G        open snippet palette")
    print(f"  Ctrl-X        type snippet name / # to insert")
    print(f"\033[1m{bar}\033[0m\n")


def _inject_ps1_tag(chan, name: str) -> None:
    """Send a best-effort PS1 modification to the remote shell.

    Waits briefly for the initial shell prompt to appear, then sends an
    export command that prepends [name] to the existing $PS1 / $PROMPT.

    Notes:
    - Works for bash and most zsh configurations.
    - Will be reset by remote .bashrc if the user opens a subshell.
    - Silently ignored if the remote shell does not support $PS1.
    - The command is prepended with a space so HISTCONTROL=ignorespace
      suppresses it from shell history on servers that have that set.
    """
    time.sleep(0.35)  # let the remote shell emit its welcome / MOTD

    # Drain any buffered welcome text — it will be forwarded by _passthrough_loop
    # once the main loop starts; we do not discard it here.
    # (paramiko buffers it internally so nothing is lost.)

    tag = f"[{name}]"
    # The leading space hides the command from bash history on many servers.
    # We set both PS1 (bash) and PROMPT (zsh/fish-ish) and suppress stderr.
    cmd = (
        f" export PS1='{tag} ${{PS1:-\\u@\\h:\\w\\$ }}' 2>/dev/null; "
        f"export PROMPT='{tag} ${{PROMPT:-%%n@%%m:%%~ %% }}' 2>/dev/null\n"
    )
    try:
        chan.sendall(cmd.encode("utf-8", errors="replace"))
    except OSError:
        pass


def _passthrough_loop(
    chan,
    db: Database,
    conn_id: int | None,
    snippets: list[dict],
) -> list[dict]:
    """Raw stdin ↔ channel passthrough with snippet hotkey interception.

    Returns the (possibly updated) snippet list.
    """
    while True:
        # --- Channel → local stdout ---
        if channel_ready(chan):
            try:
                data = chan.recv(4096)
                if not data:
                    break
                write_stdout(data)
            except OSError:
                break

        # --- Check if the remote session has ended ---
        if chan.closed or chan.exit_status_ready():
            _drain_channel(chan)
            break

        # --- Local stdin → channel (with hotkey intercept) ---
        byte = read_stdin_byte()
        if byte is None:
            continue

        if byte == _CTRL_G:
            snippets = _run_picker(chan, db, conn_id, snippets, mode="palette")
            continue

        if byte == _CTRL_X:
            snippets = _run_picker(chan, db, conn_id, snippets, mode="typed")
            continue

        # Forward everything else verbatim
        try:
            chan.sendall(byte)
        except OSError:
            break

    return snippets


def _drain_channel(chan) -> None:
    """Flush any remaining channel output to stdout before closing."""
    while chan.recv_ready():
        try:
            chunk = chan.recv(4096)
            if chunk:
                write_stdout(chunk)
        except OSError:
            break


def _run_picker(
    chan,
    db: Database,
    conn_id: int | None,
    snippets: list[dict],
    mode: str,
) -> list[dict]:
    """Pause raw mode, show snippet picker, inject chosen command, resume.

    Returns the refreshed snippet list (may have grown if user added one).
    """
    # Step out of raw mode so the picker UI can use normal cooked I/O
    pause_raw()
    print()  # blank line separator before picker UI

    from src.cli.palette import pick_snippet_palette, pick_snippet_typed

    if mode == "palette":
        command, snippets = pick_snippet_palette(snippets, db, conn_id)
    else:
        command, snippets = pick_snippet_typed(snippets, db, conn_id)

    print()  # blank line after picker UI

    # Return to raw mode before touching the channel
    resume_raw()

    if command:
        try:
            # Insert without newline — user presses Enter to run
            chan.sendall(command.encode("utf-8", errors="replace"))
        except OSError:
            pass

    return snippets
