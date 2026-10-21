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
from .templates import (
    MANIFEST,
    AudioTrack,
    Slot,
    Template,
    TemplateError,
    TemplateStyle,
    default_text_style,
)

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
# centesimi di secondo. La soglia sta appena sotto il mezzo battito di una
# canzone veloce (0.2s a 150 BPM, 0.18s a 170): i montaggi a tempo usano
# spesso due stacchi da mezzo battito di fila, e sono proprio quelli che si
# sentono. Un valore piu' alto li fondeva, e il template perdeva i battiti.
MIN_SLOT = 0.15

# Un movimento su uno slot piu' corto di cosi' non si legge come movimento, si
# legge come un tremolio: le foto piu' brevi restano ferme.
MOTION_MIN_SLOT = 0.6

# Sotto questa durata non vale la pena dire cosa c'era nel riferimento: in un
# lampo va bene qualsiasi cosa, video o foto. Un battito intero invece conta
# gia' (0.54s a 111 BPM): un montaggio di sole riprese e uno di sole foto
# sulla stessa canzone sono due video diversi.
HINT_MIN_SLOT = 0.45

# Una dissolvenza al nero finisce in un fotogramma quasi nero (luminosita' media
# sotto questa soglia, su 255) e lo raggiunge per gradi: un salto di luce piu'
# grande di MAX_FADE_STEP fra due fotogrammi e' un taglio, non una dissolvenza.
DARK = 12.0
MAX_FADE_STEP = 8.0
MIN_FADE = 0.2

# Quante inquadrature con le bande servono per dire che il riferimento mostra
# i media interi (`contain`): la maggioranza, non tutte, perche' basta una foto
# gia' verticale per riempire il quadro da sola.
CONTAIN_SHARE = 0.6

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


def detect_fade_out(brightness: list[float], fps: float) -> float:
    """
    Quanti secondi dura la dissolvenza al nero con cui finisce il video (0 = nessuna).

    Si parte dall'ultimo fotogramma, che deve essere quasi nero, e si torna
    indietro finche' la luce non scende e non salta di colpo (un salto e' un
    taglio). Si arriva cosi' all'inizio dell'ultima inquadratura, e dentro di
    lei la dissolvenza comincia dove la luce si stacca dal suo livello pieno:
    prima, l'immagine era semplicemente accesa.
    """
    if fps <= 0 or len(brightness) < 3 or brightness[-1] > DARK:
        return 0.0
    fine = len(brightness) - 1
    i = fine
    while i > 0:
        salita = brightness[i - 1] - brightness[i]
        if salita < -0.5 or salita > MAX_FADE_STEP:
            break
        i -= 1

    pieno = brightness[i]
    buio = brightness[-1]
    escursione = pieno - buio
    if escursione < 2 * DARK:
        return 0.0

    # L'inizio si ricava dalla PENDENZA della discesa, misurata nel suo tratto
    # centrale (fra il 75% e il 25% della luce) e prolungata all'indietro fino
    # al livello pieno. Cercare il primo fotogramma "meno luminoso" sbaglierebbe
    # di qualche fotogramma: all'inizio la discesa si confonde con il rumore
    # di compressione.
    alto = next(j for j in range(i, fine + 1) if brightness[j] <= buio + 0.75 * escursione)
    basso = next(j for j in range(alto, fine + 1) if brightness[j] <= buio + 0.25 * escursione)
    if basso > alto:
        pendenza = (brightness[alto] - brightness[basso]) / (basso - alto)
        inizio = max(float(i), alto - (pieno - brightness[alto]) / pendenza)
    else:
        inizio = float(alto)
    # Fino alla fine dell'ultimo fotogramma, cioe' alla fine del video: e' la
    # stessa misura che usa il builder per applicare la dissolvenza.
    durata = (fine + 1 - inizio) / fps
    return round(durata, 2) if durata >= MIN_FADE else 0.0


def detect_fade_in(brightness: list[float], fps: float) -> float:
    """Quanti secondi dura la dissolvenza dal nero con cui comincia il video (0 = nessuna)."""
    return detect_fade_out(list(reversed(brightness)), fps)


def detect_fit(shots: scenes.ShotList) -> tuple[str, tuple[int, int, int]]:
    """
    Come il riferimento mostra i media: interi con le bande (`contain`) o a
    tutto schermo (`cover`), e il colore delle bande.

    Conta il tempo, non il numero di inquadrature: un'apertura di quattro
    secondi pesa piu' di un lampo di due decimi.
    """
    totale = sum(shot.duration for shot in shots.shots)
    con_bande = [shot for shot in shots.shots if shot.bands is not None]
    if not totale or sum(s.duration for s in con_bande) / totale < CONTAIN_SHARE:
        return "cover", (0, 0, 0)

    # Il colore piu' frequente, pesato per durata: di solito il nero.
    pesi: dict[tuple[int, int, int], float] = {}
    for shot in con_bande:
        colore = tuple(round(c / 16) * 16 for c in shot.bands)  # type: ignore[union-attr]
        pesi[colore] = pesi.get(colore, 0.0) + shot.duration    # type: ignore[index]
    colore = max(pesi, key=pesi.__getitem__)
    return "contain", tuple(min(255, c) for c in colore)  # type: ignore[return-value]


def drop_inside_fades(cuts: list[float], duration: float,
                      fade_in: float, fade_out: float) -> list[float]:
    """
    Toglie i tagli che cadono dentro una dissolvenza di apertura o chiusura.

    Mentre un'immagine si spegne nel nero i fotogrammi cambiano di continuo, e
    il rilevatore puo' scambiare l'ultimo passo per un taglio: ma una
    dissolvenza e' un'inquadratura sola che si spegne, non due.
    """
    # Due fotogrammi di margine: il taglio che APRE l'ultima inquadratura cade
    # spesso proprio dove comincia la dissolvenza, e quello e' un taglio vero.
    margine = 0.07
    inizio_chiusura = duration - fade_out
    return [
        cut for cut in cuts
        if not (fade_in and cut < fade_in - margine)
        and not (fade_out and cut > inizio_chiusura + margine)
    ]


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
                transition: float = 0.0, transition_type: str = "crossfade",
                fit: str = "cover") -> list[Slot]:
    """
    Da tagli a slot: ogni taglio apre un posto, il primo si apre a zero.

    Di ogni posto si guarda l'inquadratura del riferimento che lo copriva:

    - se il suo contenuto si muoveva, il posto chiede un **video** (`hint`):
      e' li' che il riferimento alternava le riprese alle foto;
    - se la camera scorreva, una foto messa nello stesso punto scorrera' allo
      stesso modo (`motion`). Se era ferma, la foto resta ferma: un movimento
      inventato cambierebbe il video invece di riprodurlo.

    Il movimento si suggerisce solo con `fit: cover`: per muoversi una foto
    deve riempire lo schermo, e in un template che mostra i media interi la
    taglierebbe. Sugli slot brevi non si suggerisce niente, perche' un
    movimento di mezzo secondo si vede come un tremolio.
    """
    istanti = [0.0, *cuts]
    slots: list[Slot] = []

    for i, at in enumerate(istanti):
        fine = istanti[i + 1] if i + 1 < len(istanti) else duration
        durata = fine - at

        # L'inquadratura del riferimento che stava in scena a meta' slot.
        centro = at + durata / 2
        shot = next((s for s in shots.shots if s.start <= centro < s.end), None)

        movimento = None
        if shot is not None and fit == "cover" and durata >= MOTION_MIN_SLOT:
            movimento = scenes.suggest_motion(shot.drift)

        hint = None
        if shot is not None and durata >= HINT_MIN_SLOT:
            hint = "video" if shot.moving else "image"

        # Niente `label`: sarebbe "slot-03" allo slot numero 3, cioe' rumore.
        # Chi vuole dare un nome a un posto ("il ritornello") lo scrive a mano.
        slots.append(Slot(
            at=round(at, 4),
            transition=transition if i > 0 else 0.0,
            transition_type=transition_type if transition else "cut",
            motion=movimento,
            amount=motion_amount(durata),
            hint=hint,
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

    # 2. I tagli. Il rilevatore fonde da solo le inquadrature piu' corte del suo
    #    minimo: se si chiedono slot piu' brevi, deve vederli anche lui,
    #    altrimenti `min_slot` non recupererebbe niente.
    shots = scenes.analyze(source, sensitivity=sensitivity,
                           min_shot=min(scenes.MIN_SHOT, min_slot))
    if not shots.cuts:
        warnings.append(
            "Nessun taglio rilevato: il template avra' un solo slot. Se il video "
            "invece stacca, riprova con --sensitivity piu' bassa"
        )

    # 3. Lo stile: media interi o a tutto schermo, dissolvenze di apertura e
    #    chiusura. I tagli dentro una dissolvenza non sono tagli.
    fit, background = detect_fit(shots)
    fade_in = detect_fade_in(shots.brightness, shots.analysis_fps)
    fade_out = detect_fade_out(shots.brightness, shots.analysis_fps)
    tagli = drop_inside_fades(shots.cuts, duration, fade_in, fade_out)

    # 4. L'allineamento al battito.
    divisions = GRIDS[grid]
    valori, step = subdivisions(beat_grid, divisions, duration)
    allineati, spostati, medio = snap(tagli, valori, step)

    # 5. Via gli slot che nessuno riuscirebbe a riempire.
    puliti, fusi = drop_short(allineati, duration, min_slot)

    # 6. La traccia audio, che da qui in poi e' parte del template.
    destination.mkdir(parents=True, exist_ok=True)
    audio_file = extract_audio(source, destination / "audio.m4a")

    size = (info["width"] or 1080, info["height"] or 1920)
    template = Template(
        name=name or destination.name,
        audio=AudioTrack(
            src=Path(audio_file.name),
            bpm=beat_grid.bpm,
            offset=beat_grid.beats[0] if beat_grid.beats else 0.0,
        ),
        duration=round(duration, 4),
        size=size,
        fps=round(info["fps"] or 30),
        slots=build_slots(puliti, shots, duration, transition, transition_type, fit),
        style=TemplateStyle(fit=fit, background=background,
                            fade_in=fade_in, fade_out=fade_out),
        text=default_text_style(size),
        source={
            "file": source.name,
            "duration": round(duration, 2),
            "extracted": date.today(),
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


def _yaml_value(valore) -> str:
    """Un valore scalare scritto come lo leggerebbe YAML, virgolette solo se servono."""
    import yaml

    testo = yaml.safe_dump(valore, default_flow_style=True, allow_unicode=True)
    # Uno scalare da solo esce come "valore\n...\n": il "..." e' la fine del
    # documento YAML, che dentro un file piu' grande non serve.
    return testo.split("\n...")[0].strip()


def render(template: Template, grid: str = "half") -> str:
    """
    Il `template.yaml`, scritto a mano invece che con yaml.dump.

    Il motivo e' che yaml.dump non sa scrivere commenti, e un template senza
    commenti e' un elenco di numeri: chi lo apre deve poter capire che `at: 4.2`
    e' l'ottavo battito e non una durata, altrimenti non lo correggera' mai.
    """
    audio = template.audio
    style = template.style
    beats_per_slot = template.beats_per_slot
    gaps = template.gaps()

    righe = [
        "# ---------------------------------------------------------------------------",
        f"# TEMPLATE AUDIO: {template.name}",
        "#",
        "# Un montaggio riutilizzabile. La musica, gli istanti dei tagli e lo stile",
        "# sono fissi; i media e i testi no: quelli li mette ogni edit.",
        "#",
        f"#   vedit new edits/mio-video --template templates/{template.name}",
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
        "# Come entrano i media: vale per tutti gli slot.",
        "style:",
        _riga("  fit", style.fit,
              "contain = interi, con le bande; cover = a tutto schermo, tagliando i bordi"),
        _riga("  background", f"[{', '.join(str(c) for c in style.background)}]",
              "colore delle bande"),
        _riga("  fade_in", f"{style.fade_in:g}", "secondi di dissolvenza dal nero all'inizio"),
        _riga("  fade_out", f"{style.fade_out:g}", "secondi di dissolvenza al nero alla fine"),
        "",
        "# Lo stile dei testi che metterai negli edit. Ogni testo puo' cambiarlo.",
        "text:",
    ]
    for chiave, valore in template.text_style.items():
        righe.append(f"  {chiave}: {_yaml_value(valore)}")
    righe.append("")

    if template.source:
        righe.append("source:                 # da dove e' stato estratto: solo memoria")
        for chiave, valore in template.source.items():
            righe.append(f"  {chiave}: {_yaml_value(valore)}")
        righe.append("")

    righe += [
        "# ---------------------------------------------------------------------------",
        f"# SLOT: {len(template.slots)} posti da riempire, in quest'ordine.",
        "#",
        "# hint dice cosa c'era in quel posto nel video di riferimento: un video",
        "# (contenuto in movimento) o un'immagine ferma. E' un consiglio, non un",
        "# obbligo. motion vale solo se in quello slot finisce una FOTO.",
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
    style = template.style
    aspetto = ("media interi su rgb" + str(style.background) + " (contain)"
               if style.fit == "contain" else f"media a tutto schermo ({style.fit})")
    if style.fade_in:
        aspetto += f", si apre dal nero in {style.fade_in:g}s"
    if style.fade_out:
        aspetto += f", si spegne nel nero in {style.fade_out:g}s"
    lines += [
        f"Formato  : {template.size[0]}x{template.size[1]} @ {template.fps} fps",
        f"Stile    : {aspetto}",
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

    lines += ["", "  #   entra a   dura   battiti  transizione  nel riferimento  movimento"]
    for i, slot in enumerate(template.slots):
        battiti = template.beats_per_slot[i]
        transizione = (f"{slot.transition_type} {slot.transition:g}s"
                       if slot.transition > 0 else "cut")
        lines.append(
            f"{i + 1:3d}  {slot.at:8.2f}  {gaps[i]:5.2f}s  {battiti:7.2f}  "
            f"{transizione:<12} {slot.hint or '-':<16} {slot.motion or '-'}"
        )

    if result.warnings:
        lines += ["", f"Avvisi ({len(result.warnings)}):"]
        lines += [f"  - {w}" for w in result.warnings]

    lines += [
        "",
        f"Servono {len(template.slots)} media (o meno: si ripetono). Un video nuovo:",
        f"  vedit new edits/mio-video --template {Path(destination).as_posix()}",
    ]
    return "\n".join(lines)


def available(root: str | Path) -> list[Path]:
    """I template presenti in una cartella: le sottocartelle con un template.yaml."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.parent for p in root.glob(f"*/{MANIFEST}"))
