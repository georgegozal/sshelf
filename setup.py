from setuptools import setup, find_packages

setup(
    name="sshelf",
    version="0.1.0",
    description="SSH connection manager for macOS, Linux, and Windows",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
    install_requires=[
        "PyQt6>=6.4.0",
        "paramiko>=3.3.0",
        "cryptography>=41.0.0",
        "keyring>=24.0.0",
        "pyte>=0.8.0",
        "prompt_toolkit>=3.0",
    ],
    entry_points={
        "console_scripts": [
            # `sshelf` covers both CLI and GUI (`sshelf gui`)
            "sshelf=src.cli.app:cli_main",
        ],
    },
)
