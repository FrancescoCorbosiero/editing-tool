"""
Trovare i tagli di un video: dove finisce un'inquadratura e comincia la successiva.

E' il gemello di `beats.py`. Quello risponde a "in quali istanti cade il
battito?", questo a **"in quali istanti cambia l'inquadratura?"**. Messe insieme,
le due risposte dicono se un montaggio e' a tempo di musica - ed e' esattamente
quello che serve per estrarre un template da un video di riferimento.

COME
----
Tre passaggi, nessuna libreria di visione artificiale:

1. **Rimpicciolire.** ffmpeg decodifica il video in fotogrammi da 64x36. Un
   taglio si vede benissimo a quella dimensione, e ridurre di mille volte i
   pixel rende l'analisi immediata anche su un video lungo.

2. **Confrontare i fotogrammi consecutivi.** Non pixel per pixel, ma per
   ISTOGRAMMA - cioe' "quanti pixel scuri, quanti medi, quanti chiari, in
   ognuno dei tre colori". La differenza fra due istogrammi e' quasi insensibile
   al movimento (se la camera fa una panoramica i pixel si spostano ma le
   quantita' restano quelle) mentre esplode quando l'inquadratura cambia
   davvero. E' la proprieta' che distingue un taglio da una ripresa mossa, ed e'
   il motivo per cui il confronto diretto fra pixel qui non basterebbe.

   Il colore serve, e non e' ovvio: la prima versione lavorava in scala di
   grigi, e non vedeva il taglio fra un fotogramma rosso e uno verde scuro,
   perche' hanno **la stessa luminosita'**. Due inquadrature diversissime, un
   istogramma identico. Tre istogrammi, uno per canale, costano tre volte tanto
   su dati minuscoli e tolgono di mezzo un'intera famiglia di tagli mancati.

3. **Soglia adattiva.** Un cartone animato psichedelico cambia colori in
   continuazione, una scena in penombra quasi mai: una soglia fissa troverebbe
   cento tagli nel primo e zero nel secondo. Si guarda quindi quanto ogni
   fotogramma si stacca dalla MEDIANA LOCALE dei vicini, non da un numero
   assoluto.

LIMITI, ONESTAMENTE
-------------------
Trova i tagli netti, che sono la stragrande maggioranza. Una dissolvenza lenta
(mezzo secondo di sfumatura) non produce nessun picco: viene ignorata, o al
massimo segnalata come un taglio nel punto in cui il cambiamento e' piu' rapido.
Un lampo, un flash o un'esplosione possono valere un falso taglio.

Per questo esiste `vedit shots`: si guarda il risultato PRIMA di costruirci
sopra un template, e la sensibilita' si regola.

Modulo senza MoviePy: ffmpeg per decodificare, numpy per i conti.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import numpy as np

from .ffmpeg_tools import FFmpegError, ensure_ffmpeg, probe

# Dimensioni dei fotogrammi di analisi. 64x36 non conserva le proporzioni
# dell'originale, e va benissimo: la deformazione e' la stessa su tutti i
# fotogrammi, quindi non altera nessun confronto.
SAMPLE_WIDTH, SAMPLE_HEIGHT = 64, 36

# Canali di un fotogramma: rosso, verde, blu.
CHANNELS = 3

# Livelli dell'istogramma, per canale. 16 e' il compromesso: con 256 il rumore
# di compressione sposta i pixel da un livello all'altro e sporca il confronto,
# con 4 due inquadrature diverse ma ugualmente scure sembrano identiche.
BINS = 16

# Un'inquadratura piu' corta di cosi' non e' un'inquadratura: e' un lampo. Sotto
# questa soglia i "tagli" sono quasi sempre flash, esplosioni o errori.
MIN_SHOT = 0.2

# Quante volte un fotogramma deve staccarsi dalla mediana locale per essere un
# taglio. Sotto 3 si raccolgono i movimenti bruschi, sopra 6 sfuggono i tagli
# fra due inquadrature simili.
SENSITIVITY = 4.0

# Differenza minima in assoluto (0 = fotogrammi identici, 1 = nessun livello in
# comune). Serve nelle sequenze immobili, dove la mediana locale e' quasi zero e
# qualsiasi respiro supererebbe il rapporto richiesto.
FLOOR = 0.10

# Oltre questo numero di fotogrammi l'analisi rallenta il campionamento invece
# di tenere tutto in memoria: un'ora di video a 30 fps sarebbero 100k fotogrammi,
# e a colori ognuno pesa 7 KB.
MAX_FRAMES = 12_000

# Quanto deve essere marcato uno scorrimento per chiamarlo panoramica, in
# frazione della larghezza (o dell'altezza) del fotogramma.
DRIFT_THRESHOLD = 0.05


@dataclass
class Shot:
    """Un'inquadratura: un pezzo di video fra due tagli."""

    index: int
    start: float
    end: float
    drift: tuple[float, float] = (0.0, 0.0)   # scorrimento del contenuto, in frazione

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def middle(self) -> float:
        """L'istante piu' rappresentativo: a meta' dell'inquadratura."""
        return (self.start + self.end) / 2.0


@dataclass
class ShotList:
    """Il risultato dell'analisi di un video."""

    cuts: list[float] = field(default_factory=list)      # istanti dei tagli
    shots: list[Shot] = field(default_factory=list)
    duration: float = 0.0
    fps: float = 0.0
    size: tuple[int, int] = (0, 0)

    @property
    def count(self) -> int:
        return len(self.shots)

    @property
    def average(self) -> float:
        """Durata media di un'inquadratura: il "ritmo" del montaggio."""
        return self.duration / len(self.shots) if self.shots else 0.0


def decode_frames(path, width: int = SAMPLE_WIDTH, height: int = SAMPLE_HEIGHT,
                  rate: float | None = None) -> np.ndarray:
    """
    Decodifica il video in fotogrammi piccoli a colori.

    Restituisce un array [numero di fotogrammi, altezza, larghezza, 3].
    `rate` forza un campionamento piu' rado sui video lunghi: costa precisione
    sui tagli (si sa in che fotogramma, non in quale dei suoi sottomultipli) ma
    evita di tenere in memoria un'ora di video.
    """
    ensure_ffmpeg()
    filters = f"scale={width}:{height},format=rgb24"
    if rate:
        filters = f"fps={rate}," + filters

    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", filters,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise FFmpegError(
            f"Non sono riuscito a leggere i fotogrammi di {path}.\n"
            f"{result.stderr.decode(errors='replace')[-500:]}"
        )

    buffer = np.frombuffer(result.stdout, dtype=np.uint8)
    pixels = width * height * CHANNELS
    frames = len(buffer) // pixels
    return buffer[:frames * pixels].reshape(frames, height, width, CHANNELS)


def histograms(frames: np.ndarray, bins: int = BINS) -> np.ndarray:
    """
    L'istogramma normalizzato di ogni fotogramma: i tre canali uno dopo l'altro.

    Normalizzato significa che i valori sommano a 1: cosi' due fotogrammi si
    confrontano per come DISTRIBUISCONO il colore, non per quanto ne hanno.

    I tre canali stanno in un unico vettore di `bins * 3` numeri, e non in tre
    istogrammi separati, solo perche' cosi' il confronto e' una sottrazione
    sola. Sommano a 1 tutti insieme.
    """
    if frames.size == 0:
        return np.zeros((0, bins * CHANNELS), dtype=np.float32)

    # Lo shift a destra sostituisce una divisione: con 16 livelli, >>4.
    shift = int(np.log2(256 // bins))
    quantized = (frames >> shift).astype(np.int32)
    # Ogni canale occupa la sua fetta del vettore: rosso 0..15, verde 16..31,
    # blu 32..47. Sommando l'offset si conta tutto con un bincount solo.
    quantized += np.arange(CHANNELS, dtype=np.int32) * bins

    counts = np.stack([
        np.bincount(frame.ravel(), minlength=bins * CHANNELS) for frame in quantized
    ]).astype(np.float32)
    return counts / counts.sum(axis=1, keepdims=True)


def differences(hists: np.ndarray) -> np.ndarray:
    """
    Quanto ogni fotogramma differisce dal precedente: 0 identici, 1 nulla in comune.

    E' meta' della distanza L1 fra i due istogrammi, che per due distribuzioni
    normalizzate sta sempre fra 0 e 1 - una scala leggibile, indipendente dal
    numero di livelli.
    """
    if len(hists) < 2:
        return np.zeros(0, dtype=np.float32)
    return np.abs(np.diff(hists, axis=0)).sum(axis=1) / 2.0


def _local_median(values: np.ndarray, window: int) -> np.ndarray:
    """La mediana dei vicini di ogni campione, bordi inclusi."""
    if values.size == 0:
        return values
    window = max(3, window | 1)          # dispari: cosi' la finestra e' centrata
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    # sliding_window_view evita il ciclo Python: su un video lungo si sente.
    windows = np.lib.stride_tricks.sliding_window_view(padded, window)
    return np.median(windows, axis=1)


def detect_cuts(diff: np.ndarray, fps: float, sensitivity: float = SENSITIVITY,
                min_shot: float = MIN_SHOT, floor: float = FLOOR) -> list[float]:
    """
    Gli istanti in cui l'immagine cambia di colpo.

    Due condizioni insieme, e servono entrambe: il fotogramma deve staccarsi
    dalla mediana locale di almeno `sensitivity` volte (cosi' la soglia si
    adatta a materiale calmo o frenetico) e superare comunque `floor` in
    assoluto (cosi' in una sequenza immobile un respiro non diventa un taglio).

    `min_shot` sopprime i doppioni: un taglio duro spesso sporca anche il
    fotogramma successivo, e due tagli a un trentesimo di secondo l'uno
    dall'altro sono sempre lo stesso taglio. Fra due candidati troppo vicini
    vince il piu' netto.
    """
    if diff.size == 0 or fps <= 0:
        return []

    # Finestra di un secondo: abbastanza larga da descrivere "com'e' questo
    # pezzo di video", abbastanza stretta da seguire un cambio di ritmo.
    local = _local_median(diff, round(fps))
    score = diff / (local + 1e-3)

    kept: list[tuple[int, float]] = []
    for index in np.flatnonzero((score > sensitivity) & (diff > floor)):
        # Il taglio e' il fotogramma NUOVO, cioe' quello dopo la differenza.
        frame = int(index) + 1
        if kept and (frame - kept[-1][0]) / fps < min_shot:
            if score[index] > kept[-1][1]:
                kept[-1] = (frame, float(score[index]))
            continue
        kept.append((frame, float(score[index])))

    return [round(frame / fps, 4) for frame, _ in kept]


def estimate_drift(first: np.ndarray, last: np.ndarray) -> tuple[float, float]:
    """
    Di quanto e' scivolato il contenuto fra due fotogrammi, in frazione del quadro.

    Serve a capire se un'inquadratura era ferma o in movimento, per suggerire il
    movimento da dare a una FOTO che finira' in quello stesso slot (vedi
    motion.py: una foto immobile in un montaggio mosso stona).

    Il metodo e' il piu' economico che funzioni: si schiaccia il fotogramma su
    una riga (la somma delle colonne) e su una colonna (la somma delle righe), e
    si cerca di quanti pixel bisogna spostare il secondo profilo per farlo
    coincidere con il primo. Due segnali monodimensionali invece di due immagini.

    Il segno dice dove e' andato il CONTENUTO: positivo = verso destra (o verso
    il basso). La camera si muove al contrario del contenuto.
    """
    # I tre canali si mediano in uno: per capire DOVE si e' spostata una forma
    # basta la sua luminosita', il colore direbbe la stessa cosa tre volte.
    if first.ndim == 3:
        first = first.mean(axis=2)
        last = last.mean(axis=2)

    height, width = first.shape
    # `_best_shift` risponde "di quanto va spostato il primo per ritrovare il
    # secondo", che e' l'opposto di "dove e' andato il contenuto": da qui il meno.
    dx = -_best_shift(first.mean(axis=0), last.mean(axis=0))
    dy = -_best_shift(first.mean(axis=1), last.mean(axis=1))
    return dx / width, dy / height


def _best_shift(a: np.ndarray, b: np.ndarray, max_fraction: float = 0.25) -> float:
    """
    Di quanti campioni va spostato `a` perche' si sovrapponga a `b`.

    Attenzione al verso: se il contenuto si e' spostato verso destra, per
    ritrovarlo bisogna guardare piu' indietro, e il risultato e' NEGATIVO.
    Chi vuole il movimento del contenuto usa `estimate_drift`, che ribalta il
    segno una volta per tutte.

    Si confrontano i profili a media nulla con la correlazione normalizzata, che
    vale 1 per due profili identici a meno di un fattore: cosi' un cambio di
    luminosita' durante l'inquadratura non viene scambiato per un movimento.
    Sotto una correlazione minima si risponde 0: meglio "non lo so" che un
    movimento inventato.
    """
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    limit = max(1, int(len(a) * max_fraction))

    best_shift, best_score = 0, 0.0
    for shift in range(-limit, limit + 1):
        if shift >= 0:
            x, y = a[shift:], b[:len(b) - shift] if shift else b
        else:
            x, y = a[:shift], b[-shift:]
        norm = np.sqrt((x * x).sum() * (y * y).sum())
        if norm <= 1e-9:
            continue
        score = float((x * y).sum() / norm)
        if score > best_score:
            best_shift, best_score = shift, score

    # Sotto 0.6 i due profili non si assomigliano abbastanza perche' lo
    # spostamento voglia dire qualcosa (stacco, dissolvenza, zoom forte).
    return float(best_shift) if best_score > 0.6 else 0.0


def suggest_motion(drift: tuple[float, float], fallback: str) -> str:
    """
    Il movimento da suggerire per uno slot, letto dallo scorrimento misurato.

    Attenzione al ribaltamento, lo stesso di motion.py: se il contenuto scorre
    verso destra e' la camera che va verso SINISTRA. I nomi dei movimenti
    descrivono la camera, come in qualsiasi software di montaggio.
    """
    dx, dy = drift
    if abs(dx) >= abs(dy) and abs(dx) > DRIFT_THRESHOLD:
        return "pan_left" if dx > 0 else "pan_right"
    if abs(dy) > DRIFT_THRESHOLD:
        return "pan_up" if dy > 0 else "pan_down"
    return fallback


def build_shots(cuts: list[float], duration: float) -> list[Shot]:
    """Dai tagli alle inquadrature: ognuna va da un taglio al successivo."""
    starts = [0.0, *cuts]
    ends = [*cuts, duration]
    return [
        Shot(index=i, start=round(s, 4), end=round(e, 4))
        for i, (s, e) in enumerate(zip(starts, ends, strict=True))
        if e > s
    ]


def analyze(path, sensitivity: float = SENSITIVITY, min_shot: float = MIN_SHOT,
            floor: float = FLOOR) -> ShotList:
    """Analisi completa di un video: tagli, inquadrature, movimento di ognuna."""
    info = probe(path)
    duration = float(info.get("duration") or 0.0)
    fps = float(info.get("fps") or 0.0)

    # Sui video lunghi si campiona piu' rado: e' l'unico modo di non tenere in
    # memoria centomila fotogrammi, e su un video di quella lunghezza la
    # precisione al fotogramma non serve comunque a nessuno.
    rate = None
    if fps and duration and fps * duration > MAX_FRAMES:
        rate = max(1.0, round(MAX_FRAMES / duration, 2))

    frames = decode_frames(path, rate=rate)
    if len(frames) < 2:
        return ShotList(duration=duration, fps=fps,
                        size=(info.get("width") or 0, info.get("height") or 0))

    # Il frame rate dell'ANALISI, che con il campionamento rado non e' quello
    # del file. Se ffprobe non lo sa, lo si ricava dai fotogrammi ottenuti.
    analysis_fps = rate or fps or (len(frames) / duration if duration else 0.0)
    if not duration:
        duration = len(frames) / analysis_fps if analysis_fps else 0.0

    cuts = detect_cuts(differences(histograms(frames)), analysis_fps,
                       sensitivity=sensitivity, min_shot=min_shot, floor=floor)
    shots = build_shots(cuts, duration)

    # Il movimento si misura fra il 20% e l'80% dell'inquadratura: agli estremi
    # ci sono i fotogrammi sporchi del taglio, che falserebbero il confronto.
    for shot in shots:
        first = round((shot.start + shot.duration * 0.2) * analysis_fps)
        last = round((shot.start + shot.duration * 0.8) * analysis_fps)
        first = min(max(first, 0), len(frames) - 1)
        last = min(max(last, 0), len(frames) - 1)
        if last > first:
            shot.drift = estimate_drift(frames[first], frames[last])

    return ShotList(
        cuts=cuts,
        shots=shots,
        duration=round(duration, 4),
        fps=fps,
        size=(info.get("width") or 0, info.get("height") or 0),
    )


def describe(result: ShotList, path: str) -> str:
    """Il testo del comando `vedit shots`."""
    if not result.shots:
        return (f"File     : {path}\n"
                "Nessuna inquadratura riconoscibile: il video e' troppo corto "
                "o non si e' riusciti a decodificarlo.")

    lines = [
        f"File     : {path}",
        f"Durata   : {result.duration:.2f}s",
        f"Formato  : {result.size[0]}x{result.size[1]} @ {result.fps:g} fps",
        f"Tagli    : {len(result.cuts)} ({result.count} inquadrature, "
        f"in media {result.average:.2f}s l'una)",
        "",
        "  #   inizio     fine   durata  movimento",
    ]
    for shot in result.shots:
        movimento = suggest_motion(shot.drift, "fermo")
        lines.append(
            f"{shot.index:3d}  {shot.start:7.2f}  {shot.end:7.2f}  {shot.duration:6.2f}s"
            f"  {movimento}"
        )

    lines += [
        "",
        "Il movimento e' quello del CONTENUTO letto sui fotogrammi: serve a "
        "suggerire cosa fare di una foto che finisse in quella posizione.",
    ]
    return "\n".join(lines)
