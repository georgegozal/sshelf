from setuptools import setup, find_packages

setup(
    name="remminamac",
    version="0.1.0",
    description="Remmina-inspired SSH connection manager for macOS",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
    install_requires=[
        "PyQt6>=6.4.0",
        "paramiko>=3.3.0",
        "cryptography>=41.0.0",
    ],
    entry_points={
        "console_scripts": [
            "remminamac=main:main",
        ],
    },
)
