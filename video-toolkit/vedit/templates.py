"""
Template audio: un montaggio riutilizzabile, con i media come parametri.

L'IDEA
------
Un video di riferimento contiene due cose separabili. Da una parte **i media**:
le riprese, le foto, quello che si vede. Dall'altra la **struttura**: la musica,
il tempo, gli istanti in cui si stacca, le transizioni, il formato. La prima
parte e' irripetibile - sono i tuoi filmati - la seconda no: quella e' una
ricetta, e si puo' applicare a materiale completamente diverso.

Un template e' quella seconda parte. Si estrae da un video (`vedit extract`) e
si applica ai propri media (`vedit apply`).

PERCHE' SI CHIAMA "AUDIO" TEMPLATE
----------------------------------
Perche' la traccia audio non e' un accessorio, e' la struttura portante. Gli
istanti dei tagli sono i battiti DI QUELLA musica: staccarli da lei li
renderebbe numeri a caso. Per questo il template si porta dietro il file audio
e ci vive dentro. E' la stessa cosa che fa CapCut quando riusi un "suono": non
stai prendendo in prestito una canzone, stai prendendo in prestito un montaggio
che su quella canzone funziona.

Conseguenza pratica: un template dura quanto la sua traccia, e ha un numero
fisso di posti da riempire.

I POSTI
-------
Uno **slot** e' un posto nel montaggio: comincia a un istante preciso e finisce
quando comincia il successivo. Non sa cosa ci finira' dentro - un video, una
foto, un altro video - sa solo quando comincia, come entra in scena e, se
capitasse una foto, come muoverla.

Modulo senza MoviePy: qui si legge e si scrive YAML e si costruisce un Project,
che e' il formato che il builder gia' sa montare. Un template non e' un secondo
motore di rendering: e' un generatore di progetti.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# `_require` e' privato di models, e viene riusato qui apposta: un campo che
# manca deve produrre lo stesso messaggio in un progetto e in un template, e due
# implementazioni gemelle divergerebbero alla prima correzione.
from .models import FIT_MODES, ConfigError, Project, _require
from .motion import names as motion_names
from .timeline import clamp_overlap, durations_from_positions
from .transitions import DIRECTIONS, normalize_direction
from .transitions import names as transition_names

# Nome del file che descrive un template dentro la sua cartella.
MANIFEST = "template.yaml"

# Estensioni trattate come immagini: tutto il resto si apre come video.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic")
VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg")

# Sotto questa velocita' un video rallentato per riempire uno slot non sembra
# piu' un rallentatore, sembra un fermo immagine che scatta.
MIN_SPEED = 0.25


class TemplateError(ConfigError):
    """Errore in un file di template o nella sua applicazione."""


def media_kind(path: Path) -> str:
    """`image` o `video`, dedotto dall'estensione."""
    return "image" if path.suffix.lower() in IMAGE_SUFFIXES else "video"


def is_media(path: Path) -> bool:
    """True se il file sembra un media utilizzabile in un montaggio."""
    return path.suffix.lower() in IMAGE_SUFFIXES + VIDEO_SUFFIXES


@dataclass
class MediaRef:
    """
    Un media assegnato a uno slot, con il punto da cui prenderlo.

    La sintassi `riprese.mp4@12.5` significa "questo file, a partire dal secondo
    12.5": e' il modo piu' rapido di dire quale pezzo di una ripresa lunga si
    vuole, senza aprire un editor per ritagliarla prima.
    """

    path: Path
    start: float = 0.0

    @classmethod
    def parse(cls, value: str) -> MediaRef:
        text = str(value)
        head, sep, tail = text.rpartition("@")
        if sep and head:
            try:
                return cls(path=Path(head).expanduser(), start=float(tail))
            except ValueError:
                # Non e' un numero: la chiocciola fa parte del nome del file.
                pass
        return cls(path=Path(text).expanduser())

    @property
    def kind(self) -> str:
        return media_kind(self.path)

    def describe(self) -> str:
        return f"{self.path.name}@{self.start:g}" if self.start else self.path.name


def expand_media(values: list[str]) -> list[MediaRef]:
    """
    Trasforma gli argomenti da riga di comando in una lista di media.

    Una cartella si espande nei file che contiene, in ordine alfabetico: e' il
    caso piu' comune - "prendi le foto della gita" - e ordinarli per nome
    significa, quasi sempre, ordinarli per data.
    """
    refs: list[MediaRef] = []
    for value in values:
        ref = MediaRef.parse(value)
        if ref.path.is_dir():
            trovati = sorted(p for p in ref.path.iterdir() if p.is_file() and is_media(p))
            if not trovati:
                raise TemplateError(f"La cartella {ref.path} non contiene media utilizzabili")
            refs.extend(MediaRef(path=p) for p in trovati)
        else:
            refs.append(ref)
    return refs


@dataclass
class Slot:
    """
    Un posto nel montaggio: quando entra in scena e come.

    `at` e' l'unica misura di tempo che uno slot possiede. La durata non si
    dichiara: uno slot finisce quando comincia il successivo, e l'ultimo finisce
    con la traccia audio. Averla scritta in due posti significherebbe poterla
    scrivere in due modi diversi - e allora quale delle due comanda?
    """

    at: float
    transition: float = 0.0            # durata della transizione in entrata
    transition_type: str = "cut"
    direction: str = "left"
    motion: str | None = None          # suggerito: vale solo se ci finisce una foto
    amount: float = 0.15
    fit: str = "cover"
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict, index: int) -> Slot:
        where = f"slots[{index}]"
        if not isinstance(data, dict):
            raise TemplateError(f"{where}: ogni slot deve essere una mappa YAML")

        slot = cls(at=float(_require(data, "at", where)))
        if slot.at < 0:
            raise TemplateError(f"{where}: at non puo' essere negativo")

        if data.get("transition") is not None:
            slot.transition = float(data["transition"])
        if data.get("transition_type") is not None:
            slot.transition_type = str(data["transition_type"]).strip().lower()
            if slot.transition_type not in transition_names():
                raise TemplateError(
                    f"{where}: transition_type '{slot.transition_type}' non esiste. "
                    f"Disponibili: {', '.join(transition_names())}"
                )
        if data.get("direction") is not None:
            slot.direction = normalize_direction(data["direction"])
            if slot.direction not in DIRECTIONS:
                raise TemplateError(
                    f"{where}: direction '{data['direction']}' non valida. "
                    f"Usa una di {', '.join(DIRECTIONS)}"
                )
        if data.get("motion") is not None:
            slot.motion = str(data["motion"]).strip().lower()
            if slot.motion not in motion_names():
                raise TemplateError(
                    f"{where}: motion '{slot.motion}' non esiste. "
                    f"Disponibili: {', '.join(motion_names())}"
                )
        if data.get("amount") is not None:
            slot.amount = float(data["amount"])
        if data.get("fit") is not None:
            slot.fit = str(data["fit"]).strip().lower()
            if slot.fit not in FIT_MODES:
                raise TemplateError(f"{where}: fit deve essere uno di {FIT_MODES}")
        slot.label = str(data.get("label", "") or "")
        return slot

    def to_dict(self) -> dict[str, Any]:
        """Solo i campi che si discostano dal comportamento predefinito."""
        data: dict[str, Any] = {"at": round(self.at, 3)}
        if self.transition > 0:
            data["transition"] = round(self.transition, 3)
            data["transition_type"] = self.transition_type
            if self.direction != "left":
                data["direction"] = self.direction
        if self.motion:
            data["motion"] = self.motion
            data["amount"] = round(self.amount, 3)
        if self.fit != "cover":
            data["fit"] = self.fit
        if self.label:
            data["label"] = self.label
        return data


@dataclass
class AudioTrack:
    """La traccia che regge il template."""

    src: Path
    bpm: float = 0.0
    offset: float = 0.0          # dove cade il primo battito
    volume: float = 1.0
    fade_out: float = 0.0

    @property
    def period(self) -> float:
        """Secondi fra un battito e il successivo."""
        return 60.0 / self.bpm if self.bpm else 0.0

    def beat_of(self, time: float) -> float:
        """A quale battito corrisponde un istante (puo' essere frazionario)."""
        return (time - self.offset) / self.period if self.period else 0.0

    @classmethod
    def from_dict(cls, data: dict | None) -> AudioTrack:
        if not data:
            raise TemplateError(
                "Il template deve avere una sezione 'audio': e' la traccia su cui "
                "sono stati misurati gli istanti dei tagli, senza di lei sono numeri a caso"
            )
        track = cls(src=Path(_require(data, "src", "audio")))
        for key in ("bpm", "offset", "volume", "fade_out"):
            if data.get(key) is not None:
                setattr(track, key, float(data[key]))
        return track


@dataclass
class Template:
    """Un montaggio riutilizzabile: la traccia, il formato, i posti da riempire."""

    name: str
    audio: AudioTrack
    duration: float                       # quanto dura il montaggio completo
    size: tuple[int, int] = (1080, 1920)
    fps: int = 30
    slots: list[Slot] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)   # da dove viene: documentazione
    root: Path = Path(".")                # la cartella del template.yaml

    # ----------------------------------------------------------------------
    # Lettura
    # ----------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> Template:
        """
        Carica un template. `path` puo' essere il file o la cartella che lo contiene.
        """
        path = Path(path)
        if path.is_dir():
            path = path / MANIFEST
        if not path.exists():
            raise TemplateError(f"Template non trovato: {path}")

        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        template = cls.from_dict(data)
        template.root = path.parent.resolve()
        if not template.name:
            template.name = template.root.name
        return template

    @classmethod
    def from_dict(cls, data: dict) -> Template:
        if not isinstance(data, dict):
            raise TemplateError("Il template deve contenere una mappa YAML")

        slots_data = data.get("slots") or []
        if not slots_data:
            raise TemplateError("Il template deve avere almeno uno slot in 'slots'")

        formato = data.get("format") or {}
        size = formato.get("size") or [1080, 1920]
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise TemplateError("format.size deve essere una lista [larghezza, altezza]")

        template = cls(
            name=str(data.get("name", "") or ""),
            audio=AudioTrack.from_dict(data.get("audio")),
            duration=float(_require(data, "duration", "template")),
            size=(int(size[0]), int(size[1])),
            fps=int(formato.get("fps", 30)),
            slots=[Slot.from_dict(s, i) for i, s in enumerate(slots_data)],
            source=dict(data.get("source") or {}),
        )
        template.validate()
        return template

    def validate(self) -> None:
        """Controlla che gli istanti abbiano senso: crescono, e stanno nel brano."""
        if self.duration <= 0:
            raise TemplateError("La durata del template deve essere positiva")

        istanti = [slot.at for slot in self.slots]
        if istanti[0] != 0:
            raise TemplateError(
                f"slots[0]: il primo slot deve avere at: 0 (trovato {istanti[0]:g}). "
                "Il montaggio comincia dal primo slot, non dal nero"
            )
        for i in range(1, len(istanti)):
            if istanti[i] <= istanti[i - 1]:
                raise TemplateError(
                    f"slots[{i}]: at {istanti[i]:g} non viene dopo slots[{i - 1}] "
                    f"(at {istanti[i - 1]:g}). Gli istanti devono crescere"
                )
        if istanti[-1] >= self.duration:
            raise TemplateError(
                f"slots[{len(istanti) - 1}]: at {istanti[-1]:g} cade oltre la fine del "
                f"template ({self.duration:g}s): quello slot non si vedrebbe mai"
            )

        for i, slot in enumerate(self.slots[1:], start=1):
            spazio = istanti[i] - istanti[i - 1]
            if slot.transition > spazio:
                raise TemplateError(
                    f"slots[{i}]: la transizione dura {slot.transition:g}s ma dal taglio "
                    f"precedente passano {spazio:g}s: non c'e' spazio per farla"
                )

    def resolve(self, path: Path | str) -> Path:
        """I percorsi dentro un template sono relativi alla sua cartella."""
        p = Path(path)
        return p if p.is_absolute() else (self.root / p).resolve()

    # ----------------------------------------------------------------------
    # Misure
    # ----------------------------------------------------------------------

    def gaps(self) -> list[float]:
        """Quanto tempo possiede ogni slot, dal suo istante a quello successivo."""
        istanti = [slot.at for slot in self.slots]
        return durations_from_positions(istanti, self.duration - istanti[-1])

    def spans(self) -> list[float]:
        """
        Quanto materiale serve a ogni slot: il tempo che possiede, piu' l'anticipo.

        Uno slot con una dissolvenza in entrata comincia PRIMA del suo istante
        (vedi timeline.plan_anchored): di media ne serve un pezzo piu' lungo,
        altrimenti la dissolvenza mostrerebbe il vuoto.
        """
        gaps = self.gaps()
        spans = []
        for i, (slot, gap) in enumerate(zip(self.slots, gaps, strict=True)):
            anticipo = 0.0 if i == 0 else clamp_overlap(slot.transition, gaps[i - 1], gap)
            spans.append(gap + anticipo)
        return spans

    @property
    def beats_per_slot(self) -> list[float]:
        """Quanti battiti dura ogni slot: la lettura musicale del montaggio."""
        period = self.audio.period
        return [gap / period if period else 0.0 for gap in self.gaps()]


# --------------------------------------------------------------------------
# Applicazione: template + media -> progetto
# --------------------------------------------------------------------------

@dataclass
class Binding:
    """L'accoppiamento fra uno slot e il media che lo riempira'."""

    slot: Slot
    media: MediaRef
    span: float                  # quanti secondi di montaggio deve coprire
    speed: float = 1.0           # < 1 = rallentato per arrivare in fondo allo slot


@dataclass
class Bound:
    """Il risultato di `apply`: un progetto pronto, e cosa c'e' da sapere."""

    data: dict[str, Any]                            # il contenuto di un timeline.yaml
    bindings: list[Binding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def project(self, root: Path) -> Project:
        """Il Project corrispondente, pronto per il builder."""
        project = Project.from_dict(self.data)
        project.root = Path(root).resolve()
        return project


def _relative_to(path: Path, base: Path) -> str:
    """
    Il percorso piu' leggibile fra relativo e assoluto.

    Relativo se il file sta dentro la cartella di destinazione (il progetto
    resta spostabile, e leggibile), assoluto altrimenti: una catena di `../..`
    che risale mezzo disco non e' piu' portabile di un percorso assoluto, e' solo
    piu' difficile da capire.
    """
    path = path.resolve()
    base = base.resolve()
    try:
        relativo = Path(os.path.relpath(path, base))
    except ValueError:                      # dischi diversi, su Windows
        return str(path)
    return str(path) if relativo.parts and relativo.parts[0] == ".." else str(relativo)


def assign(template: Template, media: list[MediaRef],
           strict: bool = False) -> tuple[list[MediaRef], list[str]]:
    """
    Distribuisce i media sugli slot, e dice cosa non torna.

    Il numero di slot lo decide il template - cioe' la musica - e quasi mai
    coincide con quanti media si hanno sottomano. Con meno media del necessario
    si ricomincia da capo: e' quello che fa chiunque monti un video da tre
    riprese su una canzone che ne chiederebbe dodici, e produce comunque un
    montaggio guardabile. Con `strict` si pretende invece il numero esatto.
    """
    warnings: list[str] = []
    if not media:
        raise TemplateError("Serve almeno un media da mettere negli slot")

    posti = len(template.slots)
    if len(media) < posti:
        messaggio = (
            f"{len(media)} media per {posti} slot: i media si ripetono "
            f"{posti / len(media):.1f} volte"
        )
        if strict:
            raise TemplateError(messaggio + " (con --strict serve il numero esatto)")
        warnings.append(messaggio)
    elif len(media) > posti:
        messaggio = f"{len(media)} media ma il template ha {posti} slot: gli ultimi restano fuori"
        if strict:
            raise TemplateError(messaggio + " (con --strict serve il numero esatto)")
        warnings.append(messaggio)

    return [media[i % len(media)] for i in range(posti)], warnings


def bind(template: Template, media: list[MediaRef], output: Path | str | None = None,
         size: tuple[int, int] | None = None, fps: int | None = None,
         keep_audio: bool = False, volume: float | None = None, strict: bool = False,
         root: Path | None = None, durations: dict[Path, float] | None = None) -> Bound:
    """
    Applica il template ai media e produce un progetto, cioe' un `timeline.yaml`.

    Il risultato non e' un formato nuovo: e' esattamente quello che si sarebbe
    potuto scrivere a mano, e infatti si puo' salvare e correggere a mano. Il
    template e' un generatore di progetti, non un secondo motore di montaggio.

    `durations` sono le durate dei media gia' misurate (con ffprobe), quando il
    chiamante le ha: servono a capire se un video e' troppo corto per lo slot in
    cui e' finito. Senza, il controllo si salta e il render lo scoprira' da solo.
    """
    scelti, warnings = assign(template, media, strict=strict)
    spans = template.spans()
    base = Path(root) if root is not None else Path.cwd()
    durations = durations or {}

    timeline: list[dict[str, Any]] = []
    bindings: list[Binding] = []

    for i, (slot, ref, span) in enumerate(zip(template.slots, scelti, spans, strict=True)):
        ultimo = i == len(template.slots) - 1
        percorso = ref.path.resolve()
        kind = ref.kind
        speed = 1.0

        segmento: dict[str, Any] = {
            "type": kind,
            "src": _relative_to(percorso, base),
            "at": round(slot.at, 3),
            "label": slot.label or f"slot-{i + 1:02d}",
        }

        if kind == "video":
            segmento["start"] = round(ref.start, 3)
            disponibile = durations.get(percorso)
            if disponibile is not None:
                resta = disponibile - ref.start
                if resta <= 0:
                    raise TemplateError(
                        f"slot {i + 1}: {ref.path.name} dura {disponibile:.2f}s, "
                        f"non c'e' niente dopo il secondo {ref.start:g}"
                    )
                if resta < span - 0.02:
                    # Rallentare per arrivare in fondo allo slot e' quello che
                    # farebbe un montatore: il taglio successivo cade sul
                    # battito, e quel battito non si sposta per fare spazio a un
                    # video corto.
                    # Arrotondata per DIFETTO: al rialzo si chiederebbe al file
                    # qualche millisecondo che non ha, e l'ultimo fotogramma
                    # dello slot resterebbe scoperto.
                    speed = math.floor(resta / span * 1000) / 1000
                    if speed < MIN_SPEED:
                        raise TemplateError(
                            f"slot {i + 1}: servono {span:.2f}s ma {ref.path.name} ne "
                            f"offre {resta:.2f}s dal secondo {ref.start:g}. Ci vorrebbe un "
                            f"rallentatore a {speed:g}x, che e' un fermo immagine: usa un "
                            "media piu' lungo, o parti da un altro punto con file@secondi"
                        )
                    segmento["speed"] = speed
                    warnings.append(
                        f"slot {i + 1} ({ref.path.name}): {resta:.2f}s di sorgente per "
                        f"{span:.2f}s di slot, rallentato a {speed:g}x"
                    )
            if ultimo:
                # L'ultimo slot e' l'unico senza un taglio successivo che lo
                # chiuda: deve dire da solo dove finisce.
                segmento["end"] = round(ref.start + span * speed, 3)
        else:
            if slot.motion:
                segmento["motion"] = slot.motion
                segmento["amount"] = slot.amount
            if ultimo:
                segmento["duration"] = round(span, 3)

        if slot.transition > 0 and i > 0:
            segmento["transition"] = round(slot.transition, 3)
            segmento["transition_type"] = slot.transition_type
            segmento["direction"] = slot.direction

        # Il fit non si applica quando c'e' un movimento: il movimento riempie
        # sempre il canvas da solo (vedi motion.py), e dichiararlo produrrebbe
        # solo un avviso in --check.
        if not segmento.get("motion"):
            segmento["fit"] = slot.fit

        timeline.append(segmento)
        bindings.append(Binding(slot=slot, media=ref, span=span, speed=speed))

    audio_path = template.resolve(template.audio.src)
    if not audio_path.exists():
        raise TemplateError(
            f"La traccia del template non c'e': {audio_path}. Un template audio "
            "senza la sua traccia non e' applicabile"
        )

    destinazione = Path(output) if output else Path("output") / f"{template.name}.mp4"

    data: dict[str, Any] = {
        "output": {
            "path": str(destinazione),
            "size": list(size or template.size),
            "fps": int(fps or template.fps),
        },
        "defaults": {
            "transition": 0.0,
            "transition_type": "cut",
            "fit": "cover",
        },
        "timeline": timeline,
        "audio": {
            "src": _relative_to(audio_path, base),
            "volume": template.audio.volume if volume is None else volume,
            "fade_out": template.audio.fade_out,
            # La traccia del template SOSTITUISCE l'audio dei media: e' il senso
            # di un template audio. Con `keep_audio` le due tracce si sommano
            # invece - serve quando nei sorgenti c'e' qualcosa da sentire (una
            # voce, un rumore), e allora quasi sempre la musica va abbassata.
            "replace": not keep_audio,
        },
    }

    # I sorgenti si silenziano uno per uno, e non con il solo `replace`, perche'
    # cosi' la scelta resta visibile nel YAML generato: chi lo apre vede scritto
    # che l'audio dei suoi video e' stato tolto, e puo' rimetterlo.
    for segmento in data["timeline"]:
        if segmento["type"] == "video":
            segmento["mute"] = not keep_audio

    return Bound(data=data, bindings=bindings, warnings=warnings)


def describe_bound(template: Template, bound: Bound) -> str:
    """
    Chi finisce dove: il piano di montaggio, prima di spendere minuti di export.

    E' la domanda che ci si fa guardando il risultato ("perche' quella foto e'
    finita li'?"), e costa meno rispondere prima.
    """
    lines = [
        f"Template : {template.name}  ({template.duration:.2f}s, "
        f"{len(template.slots)} slot" +
        (f", {template.audio.bpm:g} BPM)" if template.audio.bpm else ")"),
        f"Formato  : {bound.data['output']['size'][0]}x{bound.data['output']['size'][1]} "
        f"@ {bound.data['output']['fps']} fps",
        f"Output   : {bound.data['output']['path']}",
        "",
        "  #   entra a   dura   media",
    ]

    for i, binding in enumerate(bound.bindings):
        dettagli = []
        if binding.speed != 1.0:
            dettagli.append(f"rallentato {binding.speed:g}x")
        if binding.media.kind == "image" and binding.slot.motion:
            dettagli.append(binding.slot.motion)
        if binding.slot.transition > 0 and i > 0:
            dettagli.append(f"{binding.slot.transition_type} {binding.slot.transition:g}s")

        coda = f"   ({', '.join(dettagli)})" if dettagli else ""
        lines.append(
            f"{i:3d}  {binding.slot.at:8.2f}  {binding.span:5.2f}s  "
            f"{binding.media.describe()}{coda}"
        )

    if bound.warnings:
        lines += ["", f"Avvisi ({len(bound.warnings)}):"]
        lines += [f"  - {w}" for w in bound.warnings]

    return "\n".join(lines)


def to_yaml(bound: Bound) -> str:
    """Il progetto come testo YAML, pronto da salvare e da correggere a mano."""
    intestazione = (
        "# Progetto generato da `vedit apply`.\n"
        "# Da qui in poi e' un timeline.yaml come tutti gli altri: correggilo,\n"
        "# cambia i media, sposta un taglio, e renderizzalo con\n"
        "#   python -m vedit render questo-file.yaml --preview\n"
        "#\n"
        "# Gli istanti (`at`) vengono dai battiti della traccia: spostarne uno\n"
        "# sposta solo quel taglio, non tutti quelli che vengono dopo.\n\n"
    )
    return intestazione + yaml.safe_dump(bound.data, sort_keys=False, allow_unicode=True)
