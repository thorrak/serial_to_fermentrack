"""API module for BrewPi-Serial-REST."""

from .client import FermentrackClient, APIError

__all__ = ["FermentrackClient", "APIError"]