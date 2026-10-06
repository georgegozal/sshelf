"""Verify PyGObject and GTK4/VTE are available before importing gtkui."""

from __future__ import annotations

import sys


def require_gtk_runtime() -> None:
    """Exit with a clear message if the GTK4 build cannot run in this Python."""
    try:
        import gi  # noqa: F401
    except ModuleNotFoundError:
        _die(
            "PyGObject (the Python module `gi`) is not visible to this interpreter.\n"
            "\n"
            "The GTK build uses system packages, not pip. On Debian/Ubuntu/MX install:\n"
            "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91\n"
            "\n"
            "If you use the install.sh venv, re-run install.sh from a fresh clone or\n"
            "recreate the venv with:  python3 -m venv --system-site-packages .venv\n"
            "(You have GTK3 bindings if you only installed gir1.2-gtk-3.0 — sshelf\n"
            "needs GTK 4: gir1.2-gtk-4.0, not the GTK3 typelib.)"
        )

    import gi

    try:
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # noqa: F401
    except ValueError:
        _die(
            "GTK 4 is not available to PyGObject (Gtk 4.0 typelib missing).\n"
            "\n"
            "Install the GTK4 GObject bindings, e.g. on Debian/Ubuntu/MX:\n"
            "  sudo apt install gir1.2-gtk-4.0\n"
            "\n"
            "libgtk-4 alone is not enough — you need the `gir1.2-gtk-4.0` package."
        )

    try:
        gi.require_version("Vte", "3.91")
        from gi.repository import Vte  # noqa: F401
    except ValueError:
        _die(
            "VTE for GTK4 is not installed (Vte 3.91 typelib missing).\n"
            "\n"
            "On Debian/Ubuntu/MX:\n"
            "  sudo apt install gir1.2-vte-3.91\n"
            "\n"
            "The older gir1.2-vte-2.91 / Vte-2.91 package is for GTK3 terminals only."
        )


def _die(msg: str) -> None:
    print(f"[sshelf] {msg}", file=sys.stderr)
    sys.exit(1)
