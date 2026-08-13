"""
Matematica della timeline: dove inizia e dove finisce ogni segmento.

Modulo puro, senza MoviePy. Serve a due clienti diversi:
  - `builder.py`, per posizionare i clip nel tempo;
  - il comando `render --check`, che stampa il riepilogo del montaggio senza
    importare MoviePy (l'import costa un paio di secondi e qui non serve).

Tenere il calcolo in un posto solo e' importante: garantisce che il riepilogo
mostri esattamente le stesse cifre del render, e permette di testare la
matematica delle transizioni in millisecondi.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Placement:
    """Posizione finale di un segmento nella timeline montata."""

    index: int
    start: float
    end: float
    overlap: float   # sovrapposizione effettiva con il segmento precedente

    @property
    def duration(self) -> float:
        """Durata del segmento cosi' come e' stato piazzato."""
        return self.end - self.start


def clamp_overlap(requested: float, prev_duration: float, duration: float) -> float:
    """
    Riduce la sovrapposizione richiesta a un valore sostenibile.

    Una transizione consuma tempo da entrambi i clip coinvolti: se durasse piu'
    della meta' del piu' corto, quel clip non si vedrebbe mai "pieno" e la
    dissolvenza successiva partirebbe prima che la precedente sia finita.
    Il limite a meta' clip e' una convenzione prudente, non una legge fisica.
    """
    return max(0.0, min(requested, prev_duration / 2.0, duration / 2.0))


def plan(durations: Sequence[float], overlaps: Sequence[float]) -> list[Placement]:
    """
    Calcola l'inizio e la fine di ogni segmento sulla timeline.

    `durations[i]` e' la durata del segmento i.
    `overlaps[i]` e' la sovrapposizione RICHIESTA in entrata sul segmento i
    (`overlaps[0]` viene ignorato: il primo segmento non ha nulla che lo preceda).

    Ogni segmento parte a `fine del precedente - sovrapposizione`: e' questa
    anticipazione che fa coesistere i due clip nel tempo, condizione necessaria
    perche' una dissolvenza incrociata abbia qualcosa su cui dissolvere.
    Le transizioni che non sovrappongono nulla (taglio netto, dissolvenza
    attraverso il nero) passano semplicemente overlap = 0.
    """
    if len(durations) != len(overlaps):
        raise ValueError("durations e overlaps devono avere la stessa lunghezza")
    if not durations:
        raise ValueError("Nessun segmento da posizionare")

    placements: list[Placement] = []
    cursor = 0.0

    for i, duration in enumerate(durations):
        if i == 0:
            overlap = 0.0
        else:
            overlap = clamp_overlap(overlaps[i], durations[i - 1], duration)

        start = cursor - overlap
        end = start + duration
        placements.append(Placement(index=i, start=start, end=end, overlap=overlap))
        cursor = end

    return placements


def total_duration(placements: Sequence[Placement]) -> float:
    """Durata del montaggio finale: la fine dell'ultimo segmento piazzato."""
    return placements[-1].end if placements else 0.0
