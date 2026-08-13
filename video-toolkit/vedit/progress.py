"""
Barra di avanzamento leggibile durante l'export.

MoviePy, di suo, stampa barre tqdm: una per l'audio, una per il video, piu'
un messaggio per ogni chunk. Su un export lungo il terminale diventa un muro
di testo in cui l'informazione utile - a che punto siamo e quanto manca - si
perde. La soluzione non e' spegnere e basta la barra (`logger=None`), ma
sostituirla: `write_videofile` accetta un logger proglog qualsiasi, quindi
possiamo intercettare gli aggiornamenti e disegnarci una riga sola.

proglog arriva insieme a MoviePy (ne e' una dipendenza), quindi usarlo non
aggiunge nulla allo stack.
"""

from __future__ import annotations

import sys
import time
from typing import IO, ClassVar

from proglog import ProgressBarLogger


def format_duration(seconds: float) -> str:
    """Durata in forma compatta: `45s`, `2m 05s`, `1h 12m`."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _pick_glyphs(stream: IO[str]) -> tuple[str, str]:
    """Blocchi Unicode dove il terminale li supporta, ASCII altrove."""
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "█·".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return "#", "-"
    return "█", "·"


class RenderProgress(ProgressBarLogger):
    """
    Logger proglog che disegna una riga di avanzamento con la stima del residuo.

    MoviePy aggiorna due "barre": `chunk` mentre scrive l'audio e `frame_index`
    mentre scrive i fotogrammi. Le trattiamo separatamente, ognuna con il suo
    cronometro, perche' le loro velocita' non sono confrontabili: l'audio si
    scrive in un attimo, i fotogrammi sono il 99% del tempo di export.
    """

    # `t` e' il nome usato dalle versioni piu' vecchie di MoviePy 2.x.
    LABELS: ClassVar[dict[str, str]] = {
        "frame_index": "video", "t": "video", "chunk": "audio",
    }

    def __init__(
        self,
        stream: IO[str] | None = None,
        min_interval: float = 0.2,
        width: int = 26,
        milestone: int = 10,
    ) -> None:
        # logged_bars=None: senza questo proglog accumula in memoria una riga
        # di log per ogni aggiornamento, e gli aggiornamenti sono migliaia.
        super().__init__(logged_bars=None)
        self.stream = stream if stream is not None else sys.stderr
        self.min_interval = min_interval
        self.width = width
        self.milestone = milestone
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.full, self.empty = _pick_glyphs(self.stream)
        self._started: dict[str, float] = {}
        self._milestones: dict[str, int] = {}
        self._last_draw = 0.0
        self._line_open = False

    # -- callback chiamata da proglog ------------------------------------

    def bars_callback(self, bar: str, attr: str, value, old_value=None) -> None:
        if attr != "index":
            return

        # Indice che torna indietro (o barra mai vista) = una nuova fase:
        # riparte il cronometro, altrimenti l'ETA erediterebbe i tempi della
        # fase precedente.
        if bar not in self._started or (old_value is not None and value < old_value):
            self._started[bar] = time.monotonic()
            self._milestones[bar] = -1

        total = self.bars[bar].get("total") or 0
        if total <= 0:
            return

        fraction = min(max(value / total, 0.0), 1.0)
        done = value >= total
        now = time.monotonic()
        if not done and now - self._last_draw < self.min_interval:
            return
        self._last_draw = now

        elapsed = now - self._started[bar]
        # Sotto il 2% la stima e' rumore puro; a lavoro finito non ha senso.
        eta = (elapsed / fraction - elapsed) if 0.02 < fraction < 1.0 else None
        self._draw(bar, fraction, elapsed, eta, done)

    # -- disegno ----------------------------------------------------------

    def _line(self, bar: str, fraction: float, elapsed: float, eta: float | None) -> str:
        filled = round(fraction * self.width)
        gauge = self.full * filled + self.empty * (self.width - filled)
        label = self.LABELS.get(bar, bar)
        text = f"  {label:<5} [{gauge}] {fraction * 100:3.0f}%  {format_duration(elapsed)}"
        if eta is not None:
            text += f" · ~{format_duration(eta)} rimanenti"
        return text

    def _draw(self, bar: str, fraction: float, elapsed: float, eta: float | None,
              done: bool) -> None:
        if self.tty:
            # \r riscrive sempre la stessa riga; il padding cancella la coda
            # della riga precedente quando questa si accorcia (l'ETA sparisce).
            self.stream.write("\r" + self._line(bar, fraction, elapsed, eta).ljust(90))
            if done:
                self.stream.write("\n")
                self._line_open = False
            else:
                self._line_open = True
            self.stream.flush()
            return

        # Fuori da un terminale (CI, log su file) il ritorno carrello non
        # cancella niente: si stampa una riga ogni `milestone` percento.
        step = int(fraction * 100) // self.milestone
        if done or step > self._milestones.get(bar, -1):
            self._milestones[bar] = step
            self.stream.write(self._line(bar, fraction, elapsed, eta) + "\n")
            self.stream.flush()

    def close_line(self) -> None:
        """Chiude la riga aperta, se ce n'e' una: da chiamare prima di stampare altro."""
        if self._line_open:
            self.stream.write("\n")
            self.stream.flush()
            self._line_open = False
