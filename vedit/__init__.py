"""vedit - montaggio video dichiarativo in Python (MoviePy 2.x + FFmpeg)."""

# Unica fonte della versione: pyproject.toml la legge da qui (dynamic version),
# cosi' non ci sono due numeri da tenere allineati.
__version__ = "0.2.0"

from .models import ConfigError, Project

__all__ = ["ConfigError", "Project", "__version__"]
