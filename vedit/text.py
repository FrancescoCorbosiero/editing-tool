"""
Disegnare il testo con Pillow, senza passare dal TextClip di MoviePy.

PERCHE' NON TEXTCLIP
--------------------
TextClip ci ha traditi due volte, e in due modi diversi:

- il suo `method="caption"` spezza le righe DENTRO le parole quando il testo
  occupa piu' di due righe (mescola indici assoluti e relativi mentre accumula
  le righe);
- dalla 2.2 il suo `method="label"` calcola male l'altezza: l'ultima riga di
  ogni scritta esce tagliata in basso, e il riquadro di sfondo perde il margine
  inferiore. Nessun errore, nessun avviso: semplicemente il testo e' mozzato.

Il secondo e' il peggiore, perche' dipende dalla versione installata: lo stesso
progetto viene giusto su una macchina e sbagliato su un'altra. Disegnare qui il
testo costa una sessantina di righe e toglie di mezzo il problema per sempre.

COME
----
Il testo diventa un'immagine RGBA grande esattamente quanto serve:

- l'a capo lo calcola `fonts.wrap_text`, alle parole;
- l'altezza di ogni riga viene dalle METRICHE del font (ascendente +
  discendente), non dalle lettere che contiene: "ace" e "pqg" producono righe
  alte uguale, e un riquadro di sfondo non cambia altezza da una scritta
  all'altra;
- in piu' si misura l'inchiostro vero di ogni riga, e l'immagine si allarga se
  qualcosa sporge (un accento su una maiuscola, un contorno spesso): nessun
  pixel di testo puo' restare fuori.

Modulo senza MoviePy: Pillow e numpy. Il builder trasforma l'array in un clip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .fonts import find_font, font_error_message, wrap_text
from .models import ConfigError, TextStyle

# Spazio fra una riga e la successiva, in frazione del corpo. Le metriche del
# font includono gia' ascendenti e discendenti: questo e' solo il respiro.
LINE_GAP = 0.12


def resolve_background(style: TextStyle) -> tuple[int, int, int, int] | None:
    """
    Traduce `bg_color` + `bg_opacity` nel colore RGBA del riquadro.

    Uno sfondo semitrasparente e' il modo piu' affidabile di rendere leggibile
    del testo su un'immagine qualsiasi: il contorno aiuta, ma su uno sfondo
    molto mosso solo un rettangolo uniforme garantisce il contrasto.
    """
    if style.bg_color is None:
        return None
    return (*_rgb(style.bg_color), round(255 * style.bg_opacity))


def _rgb(color: Any) -> tuple[int, int, int]:
    """Un colore come lo scrive chi compila il YAML: nome, `#rrggbb` o [R, G, B]."""
    from PIL import ImageColor

    if isinstance(color, str):
        try:
            return tuple(ImageColor.getrgb(color)[:3])  # type: ignore[return-value]
        except ValueError as exc:
            raise ConfigError(f"Colore non riconosciuto: '{color}'") from exc
    return tuple(int(c) for c in list(color)[:3])  # type: ignore[return-value]


def render_text(text: str, style: TextStyle, canvas_width: int,
                root: Path | None = None) -> np.ndarray:
    """
    Il testo disegnato in un array RGBA [altezza, larghezza, 4].

    `canvas_width` serve a tradurre `max_width` in pixel quando e' una frazione;
    `root` e' la cartella da cui risolvere un percorso di font relativo.
    """
    from PIL import Image, ImageDraw, ImageFont

    font_path = find_font(style.font, root)
    if font_path is None:
        raise ConfigError(font_error_message(style.font))
    font = ImageFont.truetype(str(font_path), style.font_size)

    # Un contorno senza colore non si disegna, e allora non deve nemmeno
    # occupare spazio.
    stroke = style.stroke_width if style.stroke_color else 0

    wrap = style.wrap_width(canvas_width)
    if wrap is not None:
        text = wrap_text(text, font_path, style.font_size, wrap, stroke)
    lines = text.split("\n")

    ascent, descent = font.getmetrics()
    step = ascent + descent + round(style.font_size * LINE_GAP)
    misura = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # L'inchiostro di ogni riga, misurato con l'ancora "la" (sinistra,
    # ascendente): e' la stessa ancora con cui la si disegnera'.
    boxes = [misura.textbbox((0, 0), line, font=font, anchor="la", stroke_width=stroke)
             for line in lines]
    width = max(right - left for left, _, right, _ in boxes)

    # Dove finisce ogni riga, in verticale: almeno la riga "metrica" con il
    # suo contorno, e comunque tutto l'inchiostro.
    top = min(min(box[1], -stroke) + i * step for i, box in enumerate(boxes))
    bottom = max(max(box[3], ascent + descent + stroke) + i * step
                 for i, box in enumerate(boxes))

    pad = style.padding
    size = (width + 2 * pad, bottom - top + 2 * pad)
    image = Image.new("RGBA", size, (0, 0, 0, 0))

    background = resolve_background(style)
    if background is not None:
        # Angoli appena arrotondati: un rettangolo vivo dietro una scritta
        # sembra un errore di impaginazione. Senza padding resta vivo, perche'
        # l'arrotondamento mangerebbe gli angoli delle lettere.
        radius = min(pad, style.font_size // 4)
        ImageDraw.Draw(image).rounded_rectangle(
            (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=background
        )

    # Il testo si disegna su un livello a parte e poi si compone: disegnando
    # direttamente sopra il riquadro semitrasparente, Pillow sostituirebbe i
    # pixel invece di sovrapporli, e i bordi delle lettere resterebbero
    # semitrasparenti come lo sfondo.
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    fill = (*_rgb(style.color), 255)
    stroke_fill = (*_rgb(style.stroke_color), 255) if stroke else None

    for i, (line, (left, _, right, _)) in enumerate(zip(lines, boxes, strict=True)):
        free = width - (right - left)
        offset = {"left": 0, "center": free // 2, "right": free}[style.align]
        draw.text(
            (pad + offset - left, pad + i * step - top),
            line, font=font, anchor="la", fill=fill,
            stroke_width=stroke, stroke_fill=stroke_fill,
        )

    return np.asarray(Image.alpha_composite(image, layer))
