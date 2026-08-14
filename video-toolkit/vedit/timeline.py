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


def effective_overlaps(requested: Sequence[float], durations: Sequence[float]) -> list[float]:
    """
    Le durate di transizione richieste, ridotte a quello che i clip sostengono.

    Una sola implementazione per tutti: builder, riepilogo e montaggio a istanti
    devono ridurre allo stesso modo, altrimenti `--check` mostrerebbe una
    transizione da 0.8s e il render ne farebbe una da 0.5s.
    """
    result = [0.0] * len(durations)
    for i in range(1, len(durations)):
        result[i] = clamp_overlap(requested[i], durations[i - 1], durations[i])
    return result


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


def durations_from_positions(positions: Sequence[float], last: float) -> list[float]:
    """
    Da "quando entra ogni segmento" a "quanto dura ogni segmento".

    Un segmento finisce quando comincia il successivo: e' l'unica regola. Serve
    solo la durata dell'ultimo, che non ha nessuno dopo di se' a chiuderlo.
    """
    if not positions:
        return []
    return [positions[i + 1] - positions[i] for i in range(len(positions) - 1)] + [last]


def plan_anchored(positions: Sequence[float], last: float,
                  overlaps: Sequence[float]) -> list[Placement]:
    """
    Posiziona i segmenti su istanti FISSI, con le transizioni che entrano in anticipo.

    E' la variante di `plan()` per il montaggio a istanti (`at`), e serve a
    conciliare due cose che sembrano incompatibili:

    - una dissolvenza incrociata ha bisogno che il clip che entra cominci PRIMA
      della fine del precedente, altrimenti non c'e' niente su cui dissolvere;
    - `at` promette che l'istante dichiarato non si sposta.

    La conciliazione sta nel decidere COSA fissa l'istante. Qui `positions[i]`
    e' il momento in cui il segmento i **ha finito di entrare**: il clip parte
    `overlap` secondi prima e a `positions[i]` e' completamente in scena. Il
    taglio resta dov'e' - sul battito, se ci era stato messo - e la
    sovrapposizione se la mangia la coda del segmento precedente, che sotto
    continua a vedersi.

    In `plan()` invece la sovrapposizione ACCORCIA il montaggio, perche' li' le
    posizioni sono la somma delle durate precedenti: e' esattamente il
    comportamento che rende `plan()` inadatto a un montaggio a tempo di musica.

    `overlaps[i]` e' la sovrapposizione richiesta in entrata sul segmento i
    (`overlaps[0]` viene ignorato) e viene ridotta qui a quello che i segmenti
    sostengono: il valore applicato finisce in `Placement.overlap`, che e' quindi
    l'unica versione buona: chi deve applicare l'effetto legge quella.

    `last` e' quanto MOSTRA l'ultimo segmento - l'unico senza un taglio dopo di
    se' che lo chiuda - cioe' il pezzo di sorgente che gli e' stato ritagliato.
    Se e' entrato in dissolvenza, una parte di quel pezzo se ne va nell'anticipo:
    il tempo che possiede da solo e' quello che resta.
    """
    if not positions:
        return []
    if len(positions) != len(overlaps):
        raise ValueError("positions e overlaps devono avere la stessa lunghezza")

    # Quanto tempo "possiede" ogni segmento: dal suo istante a quello dopo.
    # Per l'ultimo la misura arriva da `last`, e va corretta piu' sotto.
    gaps = durations_from_positions(positions, last)
    ultimo = len(positions) - 1

    placements: list[Placement] = []
    for i, position in enumerate(positions):
        if i == 0:
            overlap = 0.0
        elif i == ultimo:
            # L'anticipo dell'ultimo si misura su quello che mostra, non sul
            # tempo che possiede: quel tempo dipende dall'anticipo, e i due si
            # inseguirebbero. Cosi' invece il conto si chiude in un passaggio.
            overlap = clamp_overlap(overlaps[i], gaps[i - 1], last)
            gaps[i] = last - overlap
        else:
            overlap = clamp_overlap(overlaps[i], gaps[i - 1], gaps[i])

        placements.append(Placement(
            index=i,
            start=position - overlap,
            end=position + gaps[i],
            overlap=overlap,
        ))

    return placements


def total_duration(placements: Sequence[Placement]) -> float:
    """Durata del montaggio finale: la fine dell'ultimo segmento piazzato."""
    return placements[-1].end if placements else 0.0
