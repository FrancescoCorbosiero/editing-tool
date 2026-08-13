"""
Movimento sulle immagini fisse: l'effetto Ken Burns.

Uno slideshow di foto immobili e' morto: l'occhio si stacca dopo un secondo.
La soluzione classica - dal documentarista Ken Burns, che la usava per animare
fotografie d'archivio - e' far muovere lentamente l'inquadratura sull'immagine:
una carrellata (pan) o una lenta chiusura (zoom). Il movimento deve essere
appena percepibile: se lo noti, e' troppo.

Come per le transizioni, questo e' un registry `nome -> funzione`, e MoviePy si
importa dentro le funzioni perche' `models.py` importa il modulo per validare i
nomi senza pagare l'import (vedi il docstring di transitions.py).

COME FUNZIONA
-------------
L'immagine viene ingrandita oltre il canvas e poi mossa (o riscalata) sotto una
"finestra" delle dimensioni del canvas. L'eccedenza e' lo spazio disponibile per
il movimento: `amount: 0.2` significa "ingrandisci del 20%, e usa quel 20% come
corsa". Senza eccedenza il movimento scoprirebbe i bordi neri.

COSTO
-----
Un pan e' gratis: l'immagine viene ingrandita una volta sola e poi si ritaglia
una finestra diversa a ogni fotogramma, che per numpy e' una fetta di array.
Uno zoom invece deve riscalare l'immagine a OGNI fotogramma - un'interpolazione
PIL su milioni di pixel, trenta volte al secondo - e triplica il tempo di export.
Le cifre misurate sono nel README, sezione "Quanto costa il movimento".
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from inspect import cleandoc


@dataclass(frozen=True)
class MotionContext:
    """Parametri del movimento per un singolo segmento."""

    amount: float              # quanto ingrandire, in frazione (0.2 = 20%)
    size: tuple[int, int]      # dimensioni del canvas di output
    duration: float            # durata del segmento: il movimento la copre tutta


@dataclass(frozen=True)
class Motion:
    """Una voce del registry."""

    name: str
    apply: Callable            # (clip, ctx) -> clip delle dimensioni del canvas
    doc: str = ""


REGISTRY: dict[str, Motion] = {}


def register(name: str):
    """Decoratore che iscrive una funzione nel registry dei movimenti."""

    def decorator(fn: Callable) -> Callable:
        REGISTRY[name] = Motion(
            name=name, apply=fn, doc=cleandoc(fn.__doc__ or "").split("\n\n")[0]
        )
        return fn

    return decorator


def names() -> tuple[str, ...]:
    return tuple(REGISTRY)


def get(name: str) -> Motion:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Movimento sconosciuto: '{name}'. Disponibili: {', '.join(names())}"
        ) from None


# --------------------------------------------------------------------------
# Geometria
# --------------------------------------------------------------------------

def even_up(value: float) -> int:
    """
    Arrotonda al numero pari maggiore o uguale.

    Due motivi, entrambi concreti. Primo: libx264 rifiuta larghezze o altezze
    dispari, e un clip ridimensionato a mano potrebbe finire dritto in un export.
    Secondo, meno ovvio: un clip di larghezza dispari centrato su un canvas di
    larghezza pari cade a meta' pixel, e l'arrotondamento cambia da un fotogramma
    all'altro - si vede come un tremolio. Arrotondando per eccesso si evita anche
    di scendere sotto le dimensioni del canvas, cioe' di scoprire i bordi.
    """
    ceiling = math.ceil(value - 1e-9)
    return ceiling + (ceiling % 2)


def cover_size(source: tuple[int, int], target: tuple[float, float]) -> tuple[int, int]:
    """
    Dimensioni a cui portare `source` perche' copra interamente `target`.

    Si usa sempre la logica "cover" (riempi, semmai ritaglia): il fit `contain`
    non ha senso con il movimento, perche' muoverebbe anche le bande nere.
    """
    src_w, src_h = source
    scale = max(target[0] / src_w, target[1] / src_h)
    return even_up(src_w * scale), even_up(src_h * scale)


def _ramp(t: float, duration: float) -> float:
    """Avanzamento da 0 a 1 lungo il segmento, con i bordi tenuti dentro."""
    if duration <= 0:
        return 1.0
    return min(max(t / duration, 0.0), 1.0)


# --------------------------------------------------------------------------
# I movimenti
# --------------------------------------------------------------------------

def _zoom(clip, ctx: MotionContext, first: float, last: float):
    """Zoom generico: il fattore di scala va da `first` a `last`."""
    from moviepy import CompositeVideoClip

    base_w, base_h = cover_size(clip.size, ctx.size)
    duration = ctx.duration

    def size_at(t: float) -> tuple[int, int]:
        factor = first + (last - first) * _ramp(t, duration)
        return even_up(base_w * factor), even_up(base_h * factor)

    # `resized` accetta una funzione del tempo: e' qui che si paga il costo,
    # perche' ogni fotogramma viene ricampionato da capo.
    moving = clip.resized(size_at).with_position("center")
    return CompositeVideoClip([moving], size=ctx.size).with_duration(duration)


@register("zoom_in")
def zoom_in(clip, ctx: MotionContext):
    """Lenta chiusura sull'immagine: l'inquadratura si stringe."""
    return _zoom(clip, ctx, first=1.0, last=1.0 + ctx.amount)


@register("zoom_out")
def zoom_out(clip, ctx: MotionContext):
    """Lenta apertura: si parte stretti e si scopre il resto dell'immagine."""
    return _zoom(clip, ctx, first=1.0 + ctx.amount, last=1.0)


def _pan(clip, ctx: MotionContext, horizontal: bool, forward: bool):
    """
    Carrellata generica.

    `forward=True` = l'inquadratura si sposta verso destra (o verso il basso).
    Attenzione al ribaltamento: se l'inquadratura va a destra, l'immagine sullo
    schermo scorre verso SINISTRA. Il nome del movimento descrive la camera,
    non l'immagine, come in qualsiasi software di montaggio.

    L'implementazione sfrutta il fatto che la sorgente e' un'immagine FISSA:
    la si ingrandisce una volta sola, si tiene l'array in memoria e a ogni
    fotogramma se ne ritaglia una finestra grande quanto il canvas. Ritagliare
    e' una fetta di array numpy, cioe' quasi gratis - ed e' il motivo per cui
    un pan costa una frazione di uno zoom, che invece deve riscalare ogni volta.
    """
    from moviepy import VideoClip

    canvas_w, canvas_h = ctx.size
    # Si ingrandisce solo lungo l'asse del movimento: l'eccedenza e' la corsa.
    target = ((canvas_w * (1.0 + ctx.amount), canvas_h) if horizontal
              else (canvas_w, canvas_h * (1.0 + ctx.amount)))
    width, height = cover_size(clip.size, target)

    enlarged = clip.resized((width, height)).get_frame(0)
    travel_x = width - canvas_w
    travel_y = height - canvas_h
    duration = ctx.duration

    def frame_function(t: float):
        progress = _ramp(t, duration)
        offset = progress if forward else 1.0 - progress
        if horizontal:
            x, y = round(travel_x * offset), travel_y // 2
        else:
            x, y = travel_x // 2, round(travel_y * offset)
        return enlarged[y:y + canvas_h, x:x + canvas_w]

    # VideoClip ricava le dimensioni dal primo fotogramma: sono quelle del
    # canvas, quindi il clip e' pronto per il montaggio senza altri passaggi.
    return VideoClip(frame_function=frame_function, duration=duration)


@register("pan_left")
def pan_left(clip, ctx: MotionContext):
    """L'inquadratura scorre verso sinistra (l'immagine sembra andare a destra)."""
    return _pan(clip, ctx, horizontal=True, forward=False)


@register("pan_right")
def pan_right(clip, ctx: MotionContext):
    """L'inquadratura scorre verso destra."""
    return _pan(clip, ctx, horizontal=True, forward=True)


@register("pan_up")
def pan_up(clip, ctx: MotionContext):
    """L'inquadratura sale: utile sulle foto verticali, che il canvas taglia sempre."""
    return _pan(clip, ctx, horizontal=False, forward=False)


@register("pan_down")
def pan_down(clip, ctx: MotionContext):
    """L'inquadratura scende."""
    return _pan(clip, ctx, horizontal=False, forward=True)
