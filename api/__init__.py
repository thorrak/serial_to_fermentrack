"""API module for BrewPi-Rest."""

from .client import FermentrackClient, APIError

__all__ = ["FermentrackClient", "APIError"]