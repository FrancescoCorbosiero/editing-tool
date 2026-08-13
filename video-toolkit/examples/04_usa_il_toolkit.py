"""
ESEMPIO 4 - Usare vedit da codice invece che da riga di comando.

Utile quando devi generare la timeline in modo programmatico:
per esempio uno slideshow costruito ciclando su una cartella di foto.
"""

from pathlib import Path

from vedit.builder import render
from vedit.models import Project

foto = sorted(Path("assets").glob("*.jpg"))

progetto = Project.from_dict({
    "output": {"path": "output/slideshow.mp4", "size": [1920, 1080], "fps": 30},
    "defaults": {"transition": 0.8, "image_duration": 3, "fit": "cover"},
    "timeline": [
        {"type": "image", "src": str(p), "label": p.stem}
        for p in foto
    ],
})
progetto.root = Path(".").resolve()

render(progetto, preview=True)
