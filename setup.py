"""Setup script for Serial-to-Fermentrack."""

from setuptools import setup, find_packages
import re

# Read version from __init__.py
with open("bpr/__init__.py", "r") as f:
    version_match = re.search(r'__version__ = "(.*?)"', f.read())
    version = version_match.group(1) if version_match else "0.0.0"

# Read requirements from requirements.txt
with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="serial-to-fermentrack",
    version=version,
    description="Fermentrack REST API client for serial-connected BrewPi devices",
    author="Thorrak",
    author_email="...",
    url="https://github.com/thorrak/brewpi_serial_rest",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "serial_to_fermentrack=bpr.brewpi_rest:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
)
