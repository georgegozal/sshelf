#!/usr/bin/env python3
"""sshelf — SSH connection manager for macOS, Linux, and Windows."""

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sshelf",
        description="sshelf — SSH connection manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  sshelf                   # start normally\n"
            "  sshelf -n Work           # custom window title\n"
            "  sshelf --upgrade         # pull latest version and update deps\n"
        ),
    )
    parser.add_argument(
        "-n", "--name",
        metavar="NAME",
        default=None,
        help="set a custom window title suffix (e.g. 'Work', 'Personal')",
    )
    parser.add_argument(
        "-u", "--upgrade",
        action="store_true",
        help="pull the latest version from GitHub and update dependencies, then exit",
    )
    return parser


def _do_upgrade() -> None:
    import subprocess
    from pathlib import Path

    repo = Path(__file__).parent

    print("[sshelf] Pulling latest changes...")
    r = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only"])
    if r.returncode != 0:
        print("[sshelf] git pull failed.", file=sys.stderr)
        sys.exit(r.returncode)

    print("[sshelf] Updating dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "-r",
         str(repo / "requirements.txt")]
    )
    if r.returncode != 0:
        print("[sshelf] pip install failed.", file=sys.stderr)
        sys.exit(r.returncode)

    print("[sshelf] Upgrade complete.")


def main() -> None:
    parser = _build_parser()
    # parse_known_args so Qt's own flags (-style, -display, …) pass through
    args, qt_args = parser.parse_known_args()

    if args.upgrade:
        _do_upgrade()
        return

    # Remove our custom flags before handing argv to Qt
    sys.argv = [sys.argv[0]] + qt_args

    from src.app import Application
    app = Application(sys.argv, name=args.name)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
