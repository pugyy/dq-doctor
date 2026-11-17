"""dq-doctor: one command to profile tables, fix a data quality contract,
and gate new data batches.

Single source of truth for the version is package metadata (pyproject.toml).
"""
from __future__ import annotations

from importlib import metadata

__version__: str
try:
    __version__ = metadata.version("dq-doctor")
except metadata.PackageNotFoundError:  # running from a source checkout without install
    __version__ = "0.0.0.dev0"
