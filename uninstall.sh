#!/usr/bin/env bash
# RemminaMac uninstaller -- macOS and Linux
# Usage: bash uninstall.sh
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/remminamac"
LAUNCHER="$HOME/.local/bin/remminamac"
DESKTOP_FILE="$HOME/.local/share/applications/remminamac.desktop"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[remminamac]${NC} $*"; }
warn()  { echo -e "${YELLOW}[remminamac]${NC} $*"; }
error() { echo -e "${RED}[remminamac] ERROR:${NC} $*" >&2; exit 1; }

[[ -d "$INSTALL_DIR" ]] || error "RemminaMac does not appear to be installed (expected $INSTALL_DIR)."

read -r -p "Remove RemminaMac from $INSTALL_DIR? [y/N] " confirm
[[ "${confirm,,}" == "y" ]] || { echo "Aborted."; exit 0; }

rm -rf "$INSTALL_DIR"
info "Removed $INSTALL_DIR"

[[ -f "$LAUNCHER" ]] && { rm -f "$LAUNCHER"; info "Removed $LAUNCHER"; }
[[ -f "$DESKTOP_FILE" ]] && {
  rm -f "$DESKTOP_FILE"
  info "Removed $DESKTOP_FILE"
  command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
}

# -- Note about stored data ---------------------------------------------------
warn "Your connection database and preferences are kept at:"
warn "  ~/Library/Application Support/RemminaMac/  (macOS)"
warn "  ~/.local/share/RemminaMac/                 (Linux)"
warn "Delete that directory manually if you want to remove all saved connections."

echo ""
info "RemminaMac uninstalled."
