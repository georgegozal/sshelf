"""Snippet picker for in-session CLI use.

Two entry points:
    pick_snippet_palette(snippets, db, conn_id)   Ctrl-G: fuzzy palette
    pick_snippet_typed(snippets, db, conn_id)     Ctrl-X: type name/# picker

Both return (command_text | None, updated_snippet_list).

- If command_text is not None it should be inserted into the SSH channel
  WITHOUT a trailing newline (user presses Enter to run).
- If None, the user cancelled.

prompt_toolkit is used for the palette when available; falls back to a
plain numbered menu that works on any terminal (including Windows cmd).
"""

from __future__ import annotations

from typing import Optional

_HAS_PTK = False
try:
    import prompt_toolkit  # noqa: F401
    _HAS_PTK = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _reload_snippets(db, conn_id: Optional[int]) -> list[dict]:
    return db.all_snippets(conn_id)


def _add_new_snippet(db, conn_id: Optional[int]) -> tuple[Optional[str], list[dict]]:
    """Prompt the user to add a snippet, save it, return (command, updated_list)."""
    print()
    try:
        title = input("  Snippet title: ").strip()
        command = input("  Command      : ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None, _reload_snippets(db, conn_id)

    if not command:
        print("  (no command entered — cancelled)")
        return None, _reload_snippets(db, conn_id)

    db.save_snippet(title, command, conn_id)
    scope = f"for connection #{conn_id}" if conn_id else "(global)"
    print(f"  ✓ Snippet '{title}' saved {scope}.")
    return command, _reload_snippets(db, conn_id)


# ---------------------------------------------------------------------------
# prompt_toolkit palette
# ---------------------------------------------------------------------------

def _palette_ptk(
    snippets: list[dict],
    db,
    conn_id: Optional[int],
) -> tuple[Optional[str], list[dict]]:
    """Fuzzy-search palette powered by prompt_toolkit."""
    from prompt_toolkit.shortcuts import radiolist_dialog

    _ADD = "__add_new__"
    choices: list[tuple[str, str]] = [
        (s["command"], f"{s['title']:<30} {s['command']}")
        for s in snippets
    ]
    choices.append((_ADD, "➕  Add new snippet…"))

    try:
        result = radiolist_dialog(
            title="Snippets  (↑↓ navigate · Enter select · Esc cancel)",
            text="",
            values=choices,
        ).run()
    except (KeyboardInterrupt, EOFError):
        return None, snippets

    if result is None:
        return None, snippets
    if result == _ADD:
        return _add_new_snippet(db, conn_id)
    return result, snippets


# ---------------------------------------------------------------------------
# Numbered-menu fallback (no extra dependencies)
# ---------------------------------------------------------------------------

def _palette_menu(
    snippets: list[dict],
    db,
    conn_id: Optional[int],
) -> tuple[Optional[str], list[dict]]:
    """Simple numbered menu — works everywhere."""
    print()
    print("  ── Snippets ──────────────────────────────────────────")
    for i, s in enumerate(snippets, 1):
        scope_tag = f"  [conn #{s['conn_id']}]" if s["conn_id"] else ""
        print(f"   {i:>2})  {s['title']:<28}  {s['command']}{scope_tag}")
    print(f"   {'N':>2})  ➕  Add new snippet…")
    print(f"   {'0':>2})  ✗   Cancel")

    try:
        raw = input("\n  Pick # (or N/0): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None, snippets

    if not raw or raw == "0":
        return None, snippets
    if raw.lower() == "n":
        return _add_new_snippet(db, conn_id)

    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(snippets):
            return snippets[idx]["command"], snippets

    print("  (invalid selection — cancelled)")
    return None, snippets


# ---------------------------------------------------------------------------
# Typed-escape mode (Ctrl-X)
# ---------------------------------------------------------------------------

def _typed_menu(
    snippets: list[dict],
    db,
    conn_id: Optional[int],
) -> tuple[Optional[str], list[dict]]:
    """Quick typed picker: user types a title substring or # to select."""
    print()
    print("  ── Snippets (type title or # · N=add · blank=cancel) ──")
    for i, s in enumerate(snippets, 1):
        print(f"   {i:>2})  {s['title']}")
    print()

    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return None, snippets

    if not raw:
        return None, snippets
    if raw.lower() == "n":
        return _add_new_snippet(db, conn_id)

    # Numeric pick
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(snippets):
            return snippets[idx]["command"], snippets
        return None, snippets

    # Title substring search (case-insensitive)
    raw_lower = raw.lower()
    matches = [s for s in snippets if raw_lower in s["title"].lower()]

    if len(matches) == 1:
        return matches[0]["command"], snippets

    if len(matches) > 1:
        print("  Multiple matches — pick one:")
        for i, s in enumerate(matches, 1):
            print(f"   {i})  {s['title']}")
        try:
            sub = input("  # ").strip()
            if sub.isdigit():
                idx = int(sub) - 1
                if 0 <= idx < len(matches):
                    return matches[idx]["command"], snippets
        except (EOFError, KeyboardInterrupt):
            pass
        return None, snippets

    print("  (no match — cancelled)")
    return None, snippets


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pick_snippet_palette(
    snippets: list[dict],
    db,
    conn_id: Optional[int],
) -> tuple[Optional[str], list[dict]]:
    """Ctrl-G: open the snippet palette.

    Uses prompt_toolkit fuzzy dialog when available, plain numbered menu
    otherwise. Returns (command | None, refreshed_snippet_list).
    """
    if not snippets:
        print("\n  (no snippets yet — opening add dialog)")
        return _add_new_snippet(db, conn_id)
    if _HAS_PTK:
        return _palette_ptk(snippets, db, conn_id)
    return _palette_menu(snippets, db, conn_id)


def pick_snippet_typed(
    snippets: list[dict],
    db,
    conn_id: Optional[int],
) -> tuple[Optional[str], list[dict]]:
    """Ctrl-X: open the typed snippet picker.

    Returns (command | None, refreshed_snippet_list).
    """
    if not snippets:
        print("\n  (no snippets yet — opening add dialog)")
        return _add_new_snippet(db, conn_id)
    return _typed_menu(snippets, db, conn_id)
