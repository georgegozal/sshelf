"""Apply app-wide GTK appearance from preferences (theme, icons)."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from src.storage.database import Database

_LINUX = sys.platform.startswith("linux")


def apply_app_theme(theme: str) -> None:
    """Apply 'system', 'light', or 'dark' to the GTK UI."""
    settings = Gtk.Settings.get_default()
    if theme == "dark":
        settings.set_property("gtk-application-prefer-dark-theme", True)
        # Prefer-dark alone is ignored by some Xfce/MX themes; name a dark variant.
        if _LINUX:
            settings.set_property("gtk-theme-name", "Adwaita-dark")
    elif theme == "light":
        settings.set_property("gtk-application-prefer-dark-theme", False)
        if _LINUX:
            settings.set_property("gtk-theme-name", "Adwaita")
    else:
        for prop in ("gtk-application-prefer-dark-theme", "gtk-theme-name"):
            try:
                settings.reset_property(prop)
            except (TypeError, AttributeError):
                pass


def apply_icon_theme(name: str) -> None:
    """Set freedesktop icon theme (Linux); empty keeps the desktop default."""
    if not _LINUX:
        return
    settings = Gtk.Settings.get_default()
    if name:
        # GTK 4 forbids set_theme_name() on IconTheme.get_for_display().
        settings.set_property("gtk-icon-theme-name", name)
    else:
        try:
            settings.reset_property("gtk-icon-theme-name")
        except (TypeError, AttributeError):
            pass


def apply_from_database(db: Database) -> None:
    apply_app_theme(db.get_pref("app_theme", "system"))
    apply_icon_theme(db.get_pref("icon_theme", ""))
