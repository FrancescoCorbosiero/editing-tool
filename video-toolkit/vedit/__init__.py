"""vedit - montaggio video dichiarativo in Python (MoviePy 2.x + FFmpeg)."""

__version__ = "0.1.0"

from .models import Project, ConfigError  # noqa: F401

__all__ = ["Project", "ConfigError", "__version__"]
