#!/usr/bin/env python3
"""RemminaMac — SSH connection manager for macOS."""

import sys
from src.app import Application


def main() -> None:
    app = Application(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
