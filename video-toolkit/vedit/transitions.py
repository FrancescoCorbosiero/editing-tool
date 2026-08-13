"""
Le transizioni fra un segmento e il successivo, in un registry nome -> funzione.

Aggiungere una transizione significa scrivere una funzione qui e decorarla con
`@register(...)`: il builder la trova da solo, models.py accetta il nuovo nome
in validazione, `--check` lo mostra nel riepilogo. Nessun altro file da toccare.

PERCHE' MOVIEPY SI IMPORTA DENTRO LE FUNZIONI
---------------------------------------------
Questo modulo e' importato da `models.py`, che per contratto non deve tirarsi
dietro MoviePy (l'import costa secondi e serve solo a chi renderizza davvero).
Tenendo `from moviepy import ...` dentro le funzioni, il registry - cioe' i nomi
e le loro proprieta' - resta consultabile a costo zero da validazione, CLI e
riepilogo, mentre il codice che costruisce i clip si carica solo al render.
Python mette in cache i moduli: dalla seconda chiamata l'import e' gratis.

VOCABOLARIO
-----------
Una transizione puo' essere di due famiglie:

- **con sovrapposizione** (`overlaps=True`): i due clip coesistono nel tempo per
  la durata della transizione, e si vedono entrambi. La dissolvenza incrociata e'
  l'esempio classico: senza sovrapposizione dissolverebbe dal nero, non dal clip
  precedente. Costo: il montaggio si accorcia della durata della sovrapposizione.
- **senza sovrapposizione** (`overlaps=False`): i clip restano in fila e la
  transizione si consuma dentro di essi (lo stacco netto, o la dissolvenza
  attraverso il nero, in cui il primo clip si spegne e il secondo si accende).

`direction` indica sempre **il bordo da cui arriva il nuovo clip**:
`left` = entra da sinistra e si muove verso destra.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import cleandoc

# Direzioni ammesse, con gli alias piu' naturali da scrivere in un YAML.
DIRECTIONS = ("left", "right", "top", "bottom")
DIRECTION_ALIASES = {"up": "top", "down": "bottom", "su": "top", "giu": "bottom",
                     "sinistra": "left", "destra": "right"}


@dataclass(frozen=True)
class TransitionContext:
    """Tutto quello che serve a una transizione per fare il suo lavoro."""

    duration: float            # durata gia' limitata a meta' del clip piu' corto
    direction: str             # uno di DIRECTIONS
    size: tuple[int, int]      # dimensioni del canvas di output


@dataclass(frozen=True)
class TransitionRequest:
    """Come un segmento chiede la sua transizione in entrata."""

    duration: float = 0.0
    type: str = "crossfade"
    direction: str = "left"


@dataclass(frozen=True)
class Transition:
    """Una voce del registry."""

    name: str
    apply: Callable            # (prev_clip, current_clip, ctx) -> (prev_clip, current_clip)
    overlaps: bool             # i due clip coesistono nel tempo?
    directional: bool          # usa il campo `direction`?
    doc: str = ""


REGISTRY: dict[str, Transition] = {}


def register(name: str, *, overlaps: bool, directional: bool = False):
    """Decoratore che iscrive una funzione nel registry delle transizioni."""

    def decorator(fn: Callable) -> Callable:
        REGISTRY[name] = Transition(
            name=name,
            apply=fn,
            overlaps=overlaps,
            directional=directional,
            doc=cleandoc(fn.__doc__ or "").split("\n\n")[0],
        )
        return fn

    return decorator


def names() -> tuple[str, ...]:
    """I nomi disponibili, in ordine di registrazione."""
    return tuple(REGISTRY)


def get(name: str) -> Transition:
    """La transizione registrata con questo nome."""
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Transizione sconosciuta: '{name}'. Disponibili: {', '.join(names())}"
        ) from None


def normalize_direction(value: str) -> str:
    """Riporta gli alias (`up`, `giu`, `destra`...) ai quattro nomi canonici."""
    key = str(value).strip().lower()
    return DIRECTION_ALIASES.get(key, key)


# --------------------------------------------------------------------------
# Le transizioni
# --------------------------------------------------------------------------

@register("crossfade", overlaps=True)
def crossfade(prev, current, ctx: TransitionContext):
    """
    Dissolvenza incrociata: il nuovo clip appare mentre il precedente e' ancora li'.

    E' la transizione "invisibile", quella che non si nota: usala quando vuoi
    legare due inquadrature senza commentare il passaggio.
    """
    from moviepy import vfx

    # CrossFadeIn agisce sulla maschera alpha: se il clip non ne ha una,
    # gliela diamo opaca, altrimenti l'effetto non ha su cosa agire.
    if current.mask is None:
        current = current.with_mask()
    return prev, current.with_effects([vfx.CrossFadeIn(ctx.duration)])


@register("fade_through_black", overlaps=False)
def fade_through_black(prev, current, ctx: TransitionContext):
    """
    Il primo clip si spegne nel nero, il secondo si accende dal nero.

    In gergo "dip to black". A differenza della dissolvenza incrociata qui i due
    clip non si vedono mai insieme: il nero in mezzo e' una pausa, e il pubblico
    la legge come uno stacco di tempo o di luogo. Per questo NON si sovrappone
    nulla: la durata totale del montaggio non cambia, la transizione si consuma
    meta' sulla coda del primo clip e meta' sulla testa del secondo.
    """
    from moviepy import vfx

    half = ctx.duration / 2.0
    return (
        prev.with_effects([vfx.FadeOut(half)]),
        current.with_effects([vfx.FadeIn(half)]),
    )


@register("slide", overlaps=True, directional=True)
def slide(prev, current, ctx: TransitionContext):
    """
    Il nuovo clip entra scorrendo dal bordo indicato da `direction`.

    Movimento esplicito, che si nota: funziona bene fra sezioni diverse dello
    stesso video (un titolo che spinge via il capitolo precedente), male dentro
    una scena continua.
    """
    from moviepy import vfx

    # SlideIn funziona solo dentro un CompositeVideoClip e solo se il clip ha le
    # dimensioni della composizione: i nostri segmenti sono gia' tutti adattati
    # al canvas, quindi la condizione e' sempre soddisfatta.
    return prev, current.with_effects([vfx.SlideIn(ctx.duration, ctx.direction)])


@register("wipe", overlaps=True, directional=True)
def wipe(prev, current, ctx: TransitionContext):
    """
    Una linea attraversa lo schermo e "scopre" il nuovo clip sotto al precedente.

    Il clip non si muove: si muove il confine fra i due. Si realizza con una
    maschera animata, cioe' un'immagine in scala di grigi grande quanto il
    fotogramma in cui 0 = trasparente e 1 = opaco; muovendo il bordo fra le due
    zone si rivela progressivamente il clip che sta sopra.
    """
    return prev, current.with_mask(
        _wipe_mask(ctx.size, ctx.duration, ctx.direction, current.duration)
    )


def _wipe_mask(size: tuple[int, int], duration: float, direction: str, clip_duration: float):
    """
    Costruisce la maschera animata usata da `wipe`.

    Il bordo non e' netto ma sfumato su pochi pixel (`feather`): una linea dura
    contro il pixel produce un effetto scalettato e "digitale", qualche pixel di
    sfumatura la fa leggere come un taglio pulito.
    """
    import numpy as np
    from moviepy import VideoClip

    width, height = size
    span = width if direction in ("left", "right") else height
    feather = max(2, round(span * 0.015))
    axis = np.arange(span, dtype=float)

    def frame_function(t: float):
        progress = 1.0 if duration <= 0 else min(max(t / duration, 0.0), 1.0)
        # Il bordo parte fuori dallo schermo (-feather) e arriva fuori dall'altra
        # parte (span + feather): cosi' a inizio transizione la maschera e' tutta
        # trasparente e alla fine tutta opaca, sfumatura compresa.
        edge = progress * (span + 2 * feather) - feather
        if direction in ("left", "top"):
            line = np.clip((edge - axis) / feather, 0.0, 1.0)
        else:
            line = np.clip((axis - (span - edge)) / feather, 0.0, 1.0)

        if direction in ("left", "right"):
            return np.broadcast_to(line, (height, width)).copy()
        return np.broadcast_to(line[:, None], (height, width)).copy()

    return VideoClip(frame_function=frame_function, is_mask=True, duration=clip_duration)


@register("cut", overlaps=False)
def cut(prev, current, ctx: TransitionContext):
    """
    Stacco netto: nessuna transizione.

    E' il taglio piu' usato al mondo e il piu' sottovalutato da chi inizia, che
    tende a dissolvere tutto. Serve per restare dentro la stessa scena senza
    suggerire un salto di tempo.
    """
    return prev, current
