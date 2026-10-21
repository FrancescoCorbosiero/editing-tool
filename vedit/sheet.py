"""
Il foglio dei provini: tanti fotogrammi di un video in un'immagine sola.

Nella fotografia su pellicola il "provino a contatto" era il foglio con tutte
le foto di un rullino in piccolo, per scegliere quali stampare. Qui serve allo
stesso scopo: guardare un video intero con un colpo d'occhio, senza riprodurlo.

Serve due volte nel flusso di lavoro:
  - prima di estrarre un template, per vedere com'e' fatto il riferimento
    (`--shots`: un fotogramma per inquadratura);
  - dopo un render, per controllare che ogni posto contenga quello che deve
    (`--slots`: un fotogramma a meta' di ogni posto del template).

Ed e' il modo in cui un assistente che non puo' guardare un video ne controlla
il risultato: un'immagine si guarda, un mp4 no.

Modulo senza MoviePy: ffmpeg per estrarre i fotogrammi, Pillow per comporli.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .ffmpeg_tools import FFmpegError, ensure_ffmpeg, probe
from .models import TextStyle
from .text import render_text

# Quanti provini al massimo quando si campiona a intervalli regolari: oltre,
# le miniature diventano troppo piccole per servire a qualcosa.
MAX_TILES = 48


def tile_height(path: str | Path, width: int) -> int:
    """L'altezza di un provino largo `width`, con le proporzioni del video (pari)."""
    info = probe(path)
    if not info["width"] or not info["height"]:
        raise FFmpegError(f"{path} non ha una traccia video da cui estrarre provini")
    return max(2, round(info["height"] * width / info["width"] / 2) * 2)


def grab(path: str | Path, at: float, width: int, height: int) -> np.ndarray:
    """Un fotogramma all'istante `at`, ridotto a `width` x `height`: array [h, w, 3]."""
    ensure_ffmpeg()
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(at, 0):.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={width}:{height}", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    pixels = width * height * 3
    if result.returncode != 0 or len(result.stdout) < pixels:
        raise FFmpegError(
            f"Non sono riuscito a leggere il fotogramma a {at:.2f}s di {path}.\n"
            f"{result.stderr.decode(errors='replace')[-300:]}"
        )
    return np.frombuffer(result.stdout[:pixels], dtype=np.uint8).reshape(height, width, 3)


def regular_times(duration: float, every: float | None = None) -> list[float]:
    """Istanti a intervalli regolari, a meta' di ogni intervallo."""
    if duration <= 0:
        return []
    if not every or every <= 0:
        every = max(0.5, duration / MAX_TILES)
    count = max(1, min(int(duration / every), MAX_TILES))
    return [round((i + 0.5) * duration / count, 3) for i in range(count)]


def contact_sheet(path: str | Path, times: list[float], labels: list[str],
                  output: str | Path, width: int = 180, columns: int = 6) -> Path:
    """Compone i provini in una griglia, ognuno con la sua etichetta, e la salva."""
    from PIL import Image

    if not times:
        raise FFmpegError(f"Nessun istante da cui estrarre provini per {path}")
    alto = tile_height(path, width)
    tiles = [grab(path, t, width, alto) for t in times]
    margine = 4
    colonne = min(columns, len(tiles))
    righe = (len(tiles) + colonne - 1) // colonne
    foglio = Image.new("RGB", (colonne * (width + margine) + margine,
                               righe * (alto + margine) + margine), (24, 24, 24))

    stile = TextStyle(font_size=max(10, width // 12), color="white",
                      bg_color="black", bg_opacity=0.75, padding=3)
    for i, (tile, label) in enumerate(zip(tiles, labels, strict=True)):
        x = margine + (i % colonne) * (width + margine)
        y = margine + (i // colonne) * (alto + margine)
        foglio.paste(Image.fromarray(tile), (x, y))
        etichetta = Image.fromarray(render_text(label, stile, width))
        foglio.paste(etichetta, (x + 2, y + tile.shape[0] - etichetta.height - 2), etichetta)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    foglio.save(output)
    return output
