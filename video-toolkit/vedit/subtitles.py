"""
Lettura dei file `.srt`, il formato di sottotitoli piu' diffuso.

Un SRT e' testo semplice, a blocchi separati da una riga vuota:

    1
    00:00:01,000 --> 00:00:04,200
    Prima battuta,
    anche su piu' righe

    2
    00:00:05,000 --> 00:00:07,500
    Seconda battuta

Il numero progressivo esiste per comodita' umana e non viene usato: contano solo
i due tempi e il testo. La virgola come separatore dei millisecondi e' storica
(SubRip nasce in Europa); molti file usano il punto, e qui accettiamo entrambi.

Il parsing sta in un modulo suo, senza MoviePy, perche' e' pura manipolazione di
testo: cosi' e' testabile in millisecondi e `--check` puo' contare i sottotitoli
senza costruire nulla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 00:00:01,000  oppure  0:00:01.000  (ore anche a una cifra, virgola o punto)
TIME = re.compile(r"(\d+):([0-5]?\d):([0-5]?\d)[,.](\d{1,3})")
ARROW = re.compile(r"-->")


class SubtitleError(ValueError):
    """File .srt malformato."""


@dataclass(frozen=True)
class Cue:
    """Una battuta: da quando a quando, e cosa c'e' scritto."""

    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


def parse_timestamp(value: str) -> float:
    """`00:01:02,500` -> 62.5 secondi."""
    match = TIME.fullmatch(value.strip())
    if not match:
        raise SubtitleError(f"Tempo non riconosciuto: '{value.strip()}'")
    hours, minutes, seconds, fraction = match.groups()
    # I millisecondi possono essere scritti con meno di tre cifre: '5' = 500ms.
    millis = int(fraction.ljust(3, "0"))
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + millis / 1000.0


def parse_srt(content: str) -> list[Cue]:
    """
    Trasforma il contenuto di un .srt in una lista di battute.

    Tollerante quanto basta: accetta il ritorno a capo di Windows, il BOM che
    ci mette Blocco Note, blocchi senza numero progressivo e le coordinate di
    posizionamento che alcuni programmi appendono alla riga dei tempi.
    """
    content = content.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []

    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        # La riga dei tempi e' la prima che contiene '-->'; quello che viene
        # prima e' il numero progressivo, che ignoriamo.
        timing_index = next((i for i, line in enumerate(lines) if ARROW.search(line)), None)
        if timing_index is None:
            raise SubtitleError(
                f"Blocco senza riga dei tempi (manca '-->'):\n{block[:120]}"
            )

        left, _, right = lines[timing_index].partition("-->")
        # Alcuni file appendono "X1:0 X2:100 Y1:0 Y2:50" dopo il tempo finale.
        right = right.strip().split(" ")[0] if right.strip() else ""
        start, end = parse_timestamp(left), parse_timestamp(right)
        if end < start:
            raise SubtitleError(
                f"Sottotitolo che finisce prima di iniziare: {left.strip()} --> {right}"
            )

        text = "\n".join(lines[timing_index + 1:]).strip()
        if text:
            cues.append(Cue(start=start, end=end, text=text))

    return cues


def load_srt(path: str | Path) -> list[Cue]:
    """Legge un .srt da disco. UTF-8, con ripiego su latin-1 per i file vecchi."""
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # I sottotitoli scaricati anni fa sono spesso in Windows-1252/latin-1.
        content = path.read_text(encoding="latin-1")
    try:
        return parse_srt(content)
    except SubtitleError as exc:
        raise SubtitleError(f"{path.name}: {exc}") from None


def overlaps(cues: list[Cue]) -> list[tuple[Cue, Cue]]:
    """
    Coppie di battute che si sovrappongono nel tempo.

    Non e' un errore - certi film mostrano due righe insieme - ma con lo stile
    predefinito le due si disegnano una sopra l'altra e diventano illeggibili,
    quindi vale un avviso in `--check`.
    """
    ordered = sorted(cues, key=lambda c: c.start)
    return [
        (a, b)
        for a, b in zip(ordered, ordered[1:])
        if b.start < a.end - 1e-6
    ]
