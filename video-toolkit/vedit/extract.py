"""
Estrarre un template da un video di riferimento.

Mette insieme quello che sanno fare gli altri moduli e ne ricava una ricetta:

    beats.py    ->  dove cade il battito
    scenes.py   ->  dove cambia l'inquadratura
    ffmpeg      ->  la traccia audio, copiata cosi' com'e'
    qui         ->  la parte che conta: mettere d'accordo le prime due

L'ALLINEAMENTO
--------------
I tagli rilevati non cadono MAI esattamente sul battito, nemmeno in un montaggio
fatto benissimo: fra il fotogramma in cui l'immagine cambia e l'istante teorico
del battito ci sono sempre alcuni millisecondi, per come e' fatto il video (a
30 fps un fotogramma dura 33 ms) e per come l'ha montato chi l'ha montato.

Se si scrivessero nel template i tagli grezzi, ci si porterebbe dietro quegli
scarti per sempre: il template sarebbe "quel montaggio li', imperfezioni
comprese". Avvicinandoli invece al battito piu' vicino si ottiene una griglia
pulita, che su un'altra canzone dello stesso tempo continua a funzionare.

Il riallineamento e' prudente: sposta un taglio solo se era gia' vicino
(`tolerance`). Un taglio a meta' strada fra due battiti non e' un taglio
sbagliato, e' un taglio in levare - una scelta - e va lasciato dov'e'.

Modulo senza MoviePy: analisi e ffmpeg, nessuna composizione.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import beats, scenes
from .ffmpeg_tools import FFmpegError, ensure_ffmpeg, probe
from .templates import MANIFEST, AudioTrack, Slot, Template, TemplateError

# Suddivisioni su cui si puo' allineare un taglio.
#   beat    = solo sui battiti          (montaggio lento, un'immagine per battito)
#   half    = anche a meta' battito     (il caso normale: molti stacchi in levare)
#   quarter = anche sui quarti          (montaggi fittissimi)
#   off     = nessun allineamento       (si tengono i tagli come sono stati misurati)
GRIDS = {"beat": 1, "half": 2, "quarter": 4, "off": 0}

# Quanto puo' essere spostato un taglio per finire sulla griglia, in frazione
# della suddivisione. 0.25 = solo se era gia' nel quarto piu' vicino.
TOLERANCE = 0.25

# Sotto questa durata uno slot non e' un posto in cui mettere un media: e' un
# lampo. Meglio unirlo al precedente che chiedere all'utente una foto per 8
# centesimi di secondo.
MIN_SLOT = 0.25

# Un movimento su uno slot piu' corto di cosi' non si legge come movimento, si
# legge come un tremolio: le foto piu' brevi restano ferme.
MOTION_MIN_SLOT = 0.6

# Quanto movimento per ogni secondo di slot. Il movimento va misurato in
# velocita', non in quantita': lo stesso 15% percorso in quattro secondi e' una
# lenta chiusura da documentario, percorso in mezzo secondo e' uno scatto.
MOTION_PER_SECOND = 0.05
MOTION_RANGE = (0.05, 0.25)


@dataclass
class Extraction:
    """Il risultato di `vedit extract`: il template e come ci si e' arrivati."""

    template: Template
    grid: str = "half"
    snapped: int = 0                 # quanti tagli sono stati riallineati
    merged: int = 0                  # quanti slot troppo corti sono stati fusi
    shift: float = 0.0               # spostamento medio dei tagli riallineati, in secondi
    beat_grid: beats.BeatGrid | None = None
    shots: scenes.ShotList | None = None
    warnings: list[str] = field(default_factory=list)


def extract_audio(source: Path, destination: Path) -> Path:
    """
    Copia la traccia audio del video in un file a se'.

    Si prova prima la copia senza ricodifica (`-c:a copy`): e' istantanea e non
    perde niente, perche' i campioni sono esattamente quelli del file originale.
    Se il codec non e' incapsulabile in un .m4a si ripiega sull'AAC, che tutti
    leggono.
    """
    ensure_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)

    copia = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn", "-c:a", "copy",
         str(destination)],
        capture_output=True, text=True,
    )
    if copia.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
        return destination

    ricodifica = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn",
         "-c:a", "aac", "-b:a", "192k", str(destination)],
        capture_output=True, text=True,
    )
    if ricodifica.returncode != 0:
        raise FFmpegError(
            f"Non sono riuscito a estrarre l'audio da {source.name}.\n"
            f"{ricodifica.stderr[-500:]}"
        )
    return destination


def snap(cuts: list[float], grid: list[float], step: float,
         tolerance: float = TOLERANCE) -> tuple[list[float], int, float]:
    """
    Avvicina ogni taglio alla suddivisione piu' vicina, se era gia' vicino.

    Restituisce (tagli allineati, quanti ne sono stati spostati, spostamento medio).
    Un taglio piu' lontano di `tolerance * step` resta dov'e': era voluto.
    """
    if not grid or step <= 0:
        return list(cuts), 0, 0.0

    limite = step * tolerance
    allineati: list[float] = []
    spostamenti: list[float] = []

    for cut in cuts:
        vicino = min(grid, key=lambda g: abs(g - cut))
        distanza = abs(vicino - cut)
        if distanza <= limite:
            allineati.append(round(vicino, 4))
            if distanza > 1e-6:
                spostamenti.append(distanza)
        else:
            allineati.append(round(cut, 4))

    # Due tagli diversi possono finire sulla stessa suddivisione: restano uno.
    unici: list[float] = []
    for valore in allineati:
        if not unici or valore > unici[-1]:
            unici.append(valore)

    medio = sum(spostamenti) / len(spostamenti) if spostamenti else 0.0
    return unici, len(spostamenti), medio


def subdivisions(grid: beats.BeatGrid, divisions: int,
                 duration: float) -> tuple[list[float], float]:
    """
    La griglia su cui allineare: i battiti, o le loro suddivisioni.

    Restituisce anche il passo, cioe' quanto dura una suddivisione: serve a
    decidere quanto un taglio puo' essere spostato.
    """
    if not divisions or not grid.bpm:
        return [], 0.0

    step = grid.period / divisions
    if step <= 0:
        return [], 0.0

    inizio = grid.beats[0] if grid.beats else 0.0
    # Si parte da prima del primo battito: un montaggio comincia spesso mezzo
    # battito prima, sull'attacco.
    tempo = inizio - grid.period
    valori: list[float] = []
    while tempo <= duration:
        if tempo >= 0:
            valori.append(round(tempo, 4))
        tempo += step
    return valori, step


def drop_short(cuts: list[float], duration: float, minimum: float) -> tuple[list[float], int]:
    """
    Toglie i tagli che creerebbero slot troppo corti per metterci qualcosa.

    Si scarta il taglio che CHIUDE lo slot corto, non quello che lo apre: cosi'
    lo slot breve viene assorbito da quello successivo e l'inizio - che quasi
    sempre e' quello sul battito - resta dov'era.
    """
    tenuti: list[float] = []
    scartati = 0
    precedente = 0.0

    for cut in cuts:
        if cut - precedente < minimum:
            scartati += 1
            continue
        tenuti.append(cut)
        precedente = cut

    # Anche l'ultimo slot, che finisce con la traccia, deve essere lungo abbastanza.
    while tenuti and duration - tenuti[-1] < minimum:
        tenuti.pop()
        scartati += 1

    return tenuti, scartati


def motion_amount(duration: float) -> float:
    """
    Quanto movimento dare a uno slot lungo `duration`.

    Proporzionale alla durata, non fisso: quello che conta per l'occhio e' la
    velocita' con cui l'inquadratura si muove, e un ingrandimento del 15% dura
    quattro secondi su uno slot lungo e mezzo secondo su uno corto - stessa
    quantita', due effetti diversi. Gli estremi tengono il risultato fra
    "impercettibile" e "vistoso".
    """
    minimo, massimo = MOTION_RANGE
    return round(min(max(duration * MOTION_PER_SECOND, minimo), massimo), 3)


def build_slots(cuts: list[float], shots: scenes.ShotList, duration: float,
                transition: float = 0.0, transition_type: str = "crossfade") -> list[Slot]:
    """
    Da tagli a slot: ogni taglio apre un posto, il primo si apre a zero.

    Il movimento suggerito viene dall'inquadratura del riferimento che copriva
    quel pezzo di tempo: se li' la camera scorreva, una foto messa nello stesso
    punto scorrera' allo stesso modo. Sugli slot brevi non si suggerisce niente,
    perche' un movimento di mezzo secondo si vede come un tremolio.
    """
    istanti = [0.0, *cuts]
    slots: list[Slot] = []

    for i, at in enumerate(istanti):
        fine = istanti[i + 1] if i + 1 < len(istanti) else duration
        durata = fine - at

        movimento = None
        quantita = motion_amount(durata)
        if durata >= MOTION_MIN_SLOT:
            # L'inquadratura del riferimento che stava in scena a meta' slot.
            centro = at + durata / 2
            shot = next((s for s in shots.shots if s.start <= centro < s.end), None)
            # Alternare le chiusure e le aperture evita che dieci foto di fila
            # zoomino tutte nello stesso verso, che si nota e stanca.
            ripiego = "zoom_in" if len(slots) % 2 == 0 else "zoom_out"
            movimento = scenes.suggest_motion(shot.drift, ripiego) if shot else ripiego

        # Niente `label`: sarebbe "slot-03" allo slot numero 3, cioe' rumore.
        # Chi vuole dare un nome a un posto ("il ritornello") lo scrive a mano.
        slots.append(Slot(
            at=round(at, 4),
            transition=transition if i > 0 else 0.0,
            transition_type=transition_type if transition else "cut",
            motion=movimento,
            amount=quantita,
        ))

    return slots


def extract(source: str | Path, destination: str | Path, name: str = "",
            grid: str = "half", sensitivity: float = scenes.SENSITIVITY,
            min_slot: float = MIN_SLOT, transition: float = 0.0,
            transition_type: str = "crossfade", force: bool = False) -> Extraction:
    """
    Estrae un template audio da un video: la traccia, il tempo, i tagli, il formato.

    `destination` e' la cartella del template: ci finiscono il `template.yaml` e
    la traccia audio, che da quel momento vive li' dentro. Il video di partenza
    non serve piu' a niente: e' stato spremuto.
    """
    source = Path(source)
    destination = Path(destination)
    if not source.exists():
        raise FileNotFoundError(source)

    if grid not in GRIDS:
        raise TemplateError(
            f"Griglia '{grid}' sconosciuta. Disponibili: {', '.join(GRIDS)}"
        )

    manifest = destination / MANIFEST
    if manifest.exists() and not force:
        raise TemplateError(
            f"Esiste gia' un template in {destination} (usa --force per sovrascriverlo)"
        )

    info = probe(source)
    if not info.get("has_audio"):
        raise TemplateError(
            f"{source.name} non ha una traccia audio. Un template audio e' fatto "
            "attorno alla sua musica: senza, non c'e' niente da riusare"
        )

    duration = float(info["duration"])
    warnings: list[str] = []

    # 1. Il battito. Si legge dal video: ffmpeg ne decodifica l'audio da solo.
    beat_grid = beats.analyze(source)
    if not beat_grid.bpm:
        warnings.append(
            "Nessun battito riconoscibile: gli istanti restano quelli misurati sul "
            "video, senza allineamento. Il template funziona lo stesso, ma su "
            "un'altra musica non avrebbe senso trapiantarlo"
        )

    # 2. I tagli.
    shots = scenes.analyze(source, sensitivity=sensitivity)
    if not shots.cuts:
        warnings.append(
            "Nessun taglio rilevato: il template avra' un solo slot. Se il video "
            "invece stacca, riprova con --sensitivity piu' bassa"
        )

    # 3. L'allineamento al battito.
    divisions = GRIDS[grid]
    valori, step = subdivisions(beat_grid, divisions, duration)
    allineati, spostati, medio = snap(shots.cuts, valori, step)

    # 4. Via gli slot che nessuno riuscirebbe a riempire.
    puliti, fusi = drop_short(allineati, duration, min_slot)

    # 5. La traccia audio, che da qui in poi e' parte del template.
    destination.mkdir(parents=True, exist_ok=True)
    audio_file = extract_audio(source, destination / "audio.m4a")

    template = Template(
        name=name or destination.name,
        audio=AudioTrack(
            src=Path(audio_file.name),
            bpm=beat_grid.bpm,
            offset=beat_grid.beats[0] if beat_grid.beats else 0.0,
        ),
        duration=round(duration, 4),
        size=(info["width"] or 1080, info["height"] or 1920),
        fps=round(info["fps"] or 30),
        slots=build_slots(puliti, shots, duration, transition, transition_type),
        source={
            "file": source.name,
            "duration": round(duration, 2),
            "extracted": date.today().isoformat(),
        },
        root=destination.resolve(),
    )
    template.validate()

    manifest.write_text(render(template, grid=grid), encoding="utf-8")

    return Extraction(
        template=template,
        grid=grid,
        snapped=spostati,
        merged=fusi,
        shift=medio,
        beat_grid=beat_grid,
        shots=shots,
        warnings=warnings,
    )


# --------------------------------------------------------------------------
# Scrittura del template.yaml
# --------------------------------------------------------------------------

def _riga(chiave: str, valore: str, commento: str, colonna: int = 26) -> str:
    """Una riga YAML con il commento incolonnato: si legge come una tabella."""
    testo = f"{chiave}: {valore}"
    return f"{testo.ljust(colonna)}# {commento}" if commento else testo


def render(template: Template, grid: str = "half") -> str:
    """
    Il `template.yaml`, scritto a mano invece che con yaml.dump.

    Il motivo e' che yaml.dump non sa scrivere commenti, e un template senza
    commenti e' un elenco di numeri: chi lo apre deve poter capire che `at: 4.2`
    e' l'ottavo battito e non una durata, altrimenti non lo correggera' mai.
    """
    audio = template.audio
    beats_per_slot = template.beats_per_slot
    gaps = template.gaps()

    righe = [
        "# ---------------------------------------------------------------------------",
        f"# TEMPLATE AUDIO: {template.name}",
        "#",
        "# Un montaggio riutilizzabile. La musica e gli istanti dei tagli sono fissi,",
        "# i media no: quelli li porti tu.",
        "#",
        "#   python -m vedit apply <questa cartella> foto1.jpg riprese.mp4 ... --preview",
        "#",
        "# `at` e' l'istante in cui uno slot entra in scena, misurato sulla traccia",
        "# audio qui sotto. Uno slot finisce quando comincia il successivo, e l'ultimo",
        "# finisce con la traccia: le durate non si scrivono, si deducono.",
        "# ---------------------------------------------------------------------------",
        "",
        f"name: {template.name}",
        _riga("duration", f"{template.duration:g}", "quanto dura il montaggio completo"),
        "",
        "audio:",
        _riga("  src", str(audio.src), "la traccia, che vive dentro questa cartella"),
        _riga("  bpm", f"{audio.bpm:g}",
              f"un battito ogni {audio.period:.3f}s" if audio.bpm else "nessun battito rilevato"),
        _riga("  offset", f"{audio.offset:g}", "dove cade il primo battito"),
        _riga("  volume", f"{audio.volume:g}", "1 = com'e', 0.5 = a meta'"),
        _riga("  fade_out", f"{audio.fade_out:g}", "dissolvenza audio in chiusura"),
        "",
        "format:",
        _riga("  size", f"[{template.size[0]}, {template.size[1]}]",
              "si puo' cambiare quando lo applichi: --size 1080x1920"),
        f"  fps: {template.fps}",
        "",
    ]

    if template.source:
        righe.append("source:                 # da dove e' stato estratto: solo memoria")
        for chiave, valore in template.source.items():
            righe.append(f"  {chiave}: {valore}")
        righe.append("")

    righe += [
        "# ---------------------------------------------------------------------------",
        f"# SLOT: {len(template.slots)} posti da riempire, in quest'ordine.",
        "#",
        "# motion vale solo se in quello slot finisce una FOTO (un video si muove",
        "# gia' per conto suo). Toglilo, o cambialo, se non ti convince.",
        "# ---------------------------------------------------------------------------",
        "slots:",
    ]

    for i, slot in enumerate(template.slots):
        dati = slot.to_dict()
        commento = f"{i + 1:2d})  dura {gaps[i]:.2f}s"
        if audio.bpm:
            commento += f", {beats_per_slot[i]:.2f} battiti"

        prima = True
        for chiave, valore in dati.items():
            prefisso = "  - " if prima else "    "
            righe.append(_riga(f"{prefisso}{chiave}", str(valore),
                               commento if prima else ""))
            prima = False

    righe.append("")
    return "\n".join(righe)


def describe(result: Extraction, destination: Path) -> str:
    """Il testo del comando `vedit extract`."""
    template = result.template
    audio = template.audio
    gaps = template.gaps()

    lines = [
        f"Template : {template.name}  ->  {destination}",
        f"Traccia  : {audio.src}  ({template.duration:.2f}s)",
    ]
    if audio.bpm:
        lines.append(
            f"Tempo    : {audio.bpm:g} BPM  (un battito ogni {audio.period:.3f}s, "
            f"il primo a {audio.offset:.3f}s)"
        )
    else:
        lines.append("Tempo    : non rilevato")
    lines += [
        f"Formato  : {template.size[0]}x{template.size[1]} @ {template.fps} fps",
        f"Slot     : {len(template.slots)}  "
        f"(il piu' corto {min(gaps):.2f}s, il piu' lungo {max(gaps):.2f}s)",
    ]

    if result.grid != "off" and audio.bpm:
        lines.append(
            f"Griglia  : {result.grid} - {result.snapped} tagli riallineati al battito"
            + (f", in media di {result.shift * 1000:.0f} ms" if result.snapped else "")
        )
    if result.merged:
        lines.append(f"Scartati : {result.merged} tagli troppo ravvicinati per essere slot")

    lines += ["", "  #   entra a   dura   battiti  transizione  movimento"]
    for i, slot in enumerate(template.slots):
        battiti = template.beats_per_slot[i]
        transizione = (f"{slot.transition_type} {slot.transition:g}s"
                       if slot.transition > 0 else "cut")
        lines.append(
            f"{i:3d}  {slot.at:8.2f}  {gaps[i]:5.2f}s  {battiti:7.2f}  "
            f"{transizione:<12} {slot.motion or '-'}"
        )

    if result.warnings:
        lines += ["", f"Avvisi ({len(result.warnings)}):"]
        lines += [f"  - {w}" for w in result.warnings]

    lines += [
        "",
        f"Servono {len(template.slots)} media (o meno: si ripetono). Provalo con:",
        f"  python -m vedit apply {destination} <i tuoi file> --preview",
    ]
    return "\n".join(lines)


def available(root: str | Path) -> list[Path]:
    """I template presenti in una cartella: le sottocartelle con un template.yaml."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.parent for p in root.glob(f"*/{MANIFEST}"))
