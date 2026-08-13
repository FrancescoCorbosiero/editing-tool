"""
Modelli dati del progetto: descrivono una timeline in modo dichiarativo.

Un progetto e' un file YAML che viene caricato in un oggetto Project.
Il builder (builder.py) legge il Project e costruisce i clip MoviePy.
Qui NON si tocca MoviePy: questo modulo e' puro parsing e validazione.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Modalita' di adattamento di un'immagine/video al canvas di output
FIT_MODES = ("contain", "cover", "stretch")


class ConfigError(ValueError):
    """Errore di configurazione del progetto (YAML malformato o valori invalidi)."""


def _require(data: dict, key: str, where: str) -> Any:
    if key not in data:
        raise ConfigError(f"Campo obbligatorio mancante: '{key}' in {where}")
    return data[key]


def _as_size(value: Any, where: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"'{where}' deve essere una lista [larghezza, altezza]")
    return int(value[0]), int(value[1])


@dataclass
class OutputSpec:
    """Parametri di esportazione del file finale."""

    path: Path = Path("output/out.mp4")
    size: tuple[int, int] = (1920, 1080)
    fps: int = 30
    codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "medium"       # ultrafast..veryslow: piu' lento = file piu' piccolo
    crf: int = 20                # 18 = alta qualita', 23 = default, 28 = compresso
    background: tuple[int, int, int] = (0, 0, 0)
    threads: int | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "OutputSpec":
        data = data or {}
        spec = cls()
        if "path" in data:
            spec.path = Path(data["path"])
        if "size" in data:
            spec.size = _as_size(data["size"], "output.size")
        for key in ("fps", "crf", "threads"):
            if key in data and data[key] is not None:
                setattr(spec, key, int(data[key]))
        for key in ("codec", "audio_codec", "preset"):
            if key in data:
                setattr(spec, key, str(data[key]))
        if "background" in data:
            bg = data["background"]
            if not isinstance(bg, (list, tuple)) or len(bg) != 3:
                raise ConfigError("output.background deve essere [R, G, B]")
            spec.background = tuple(int(c) for c in bg)  # type: ignore[assignment]
        return spec


@dataclass
class Defaults:
    """Valori applicati ai segmenti che non li specificano."""

    transition: float = 0.0      # durata crossfade fra un segmento e il successivo
    image_duration: float = 4.0  # durata di un'immagine se non indicata
    fit: str = "cover"

    @classmethod
    def from_dict(cls, data: dict | None) -> "Defaults":
        data = data or {}
        d = cls()
        if "transition" in data:
            d.transition = float(data["transition"])
        if "image_duration" in data:
            d.image_duration = float(data["image_duration"])
        if "fit" in data:
            d.fit = str(data["fit"])
        if d.fit not in FIT_MODES:
            raise ConfigError(f"defaults.fit deve essere uno di {FIT_MODES}")
        return d


@dataclass
class Segment:
    """
    Un elemento della timeline principale. I segmenti vengono messi in fila,
    eventualmente sovrapposti fra loro per la durata della transizione.
    """

    type: str                      # "video" | "image" | "color"
    src: Path | None = None
    start: float | None = None     # solo per type=video: taglio IN nel sorgente
    end: float | None = None       # solo per type=video: taglio OUT nel sorgente
    duration: float | None = None  # obbligatorio per image/color
    fit: str | None = None
    transition: float | None = None  # crossfade in ENTRATA su questo segmento
    speed: float = 1.0
    mute: bool = False
    color: tuple[int, int, int] = (0, 0, 0)
    label: str = ""                # solo per leggibilita' nei log

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "Segment":
        where = f"timeline[{index}]"
        seg_type = str(_require(data, "type", where)).lower()
        if seg_type not in ("video", "image", "color"):
            raise ConfigError(f"{where}: type deve essere video, image o color")

        seg = cls(type=seg_type, label=str(data.get("label", "")))

        if seg_type in ("video", "image"):
            seg.src = Path(_require(data, "src", where))

        for key in ("start", "end", "duration", "transition"):
            if data.get(key) is not None:
                setattr(seg, key, float(data[key]))

        if "speed" in data:
            seg.speed = float(data["speed"])
            if seg.speed <= 0:
                raise ConfigError(f"{where}: speed deve essere > 0")

        seg.mute = bool(data.get("mute", False))

        if "fit" in data:
            seg.fit = str(data["fit"])
            if seg.fit not in FIT_MODES:
                raise ConfigError(f"{where}: fit deve essere uno di {FIT_MODES}")

        if "color" in data:
            seg.color = tuple(int(c) for c in data["color"])  # type: ignore[assignment]

        if seg_type == "video" and seg.start is not None and seg.end is not None:
            if seg.end <= seg.start:
                raise ConfigError(f"{where}: end deve essere maggiore di start")

        if seg_type == "color" and seg.duration is None:
            raise ConfigError(f"{where}: un segmento 'color' richiede 'duration'")

        return seg


@dataclass
class Overlay:
    """
    Elemento sovrapposto al montaggio finale (logo, watermark, cartello...).
    Le coordinate sono in pixel sul canvas di output, oppure stringhe
    come "center", "left", "top".
    """

    type: str                      # "image" | "text"
    src: Path | None = None
    text: str = ""
    start: float = 0.0
    duration: float | None = None  # None = fino alla fine del video
    width: int | None = None
    height: int | None = None
    position: Any = "center"       # [x, y] oppure "center" / ["center", "top"]
    fade: float = 0.0              # dissolvenza in entrata e uscita
    opacity: float = 1.0
    font_size: int = 64
    color: str = "white"
    font: str | None = None        # percorso a un .ttf

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "Overlay":
        where = f"overlays[{index}]"
        ov_type = str(_require(data, "type", where)).lower()
        if ov_type not in ("image", "text"):
            raise ConfigError(f"{where}: type deve essere image o text")

        ov = cls(type=ov_type)
        if ov_type == "image":
            ov.src = Path(_require(data, "src", where))
        else:
            ov.text = str(_require(data, "text", where))

        for key in ("start", "duration", "fade", "opacity"):
            if data.get(key) is not None:
                setattr(ov, key, float(data[key]))
        for key in ("width", "height", "font_size"):
            if data.get(key) is not None:
                setattr(ov, key, int(data[key]))
        if "position" in data:
            pos = data["position"]
            ov.position = tuple(pos) if isinstance(pos, list) else pos
        if "color" in data:
            ov.color = str(data["color"])
        if "font" in data:
            ov.font = str(data["font"])

        return ov


@dataclass
class AudioSpec:
    """Traccia audio aggiuntiva (musica di sottofondo o voce fuori campo)."""

    src: Path
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    start: float = 0.0
    replace: bool = False   # True = sostituisce l'audio originale dei segmenti

    @classmethod
    def from_dict(cls, data: dict | None) -> "AudioSpec | None":
        if not data:
            return None
        spec = cls(src=Path(_require(data, "src", "audio")))
        for key in ("volume", "fade_in", "fade_out", "start"):
            if data.get(key) is not None:
                setattr(spec, key, float(data[key]))
        spec.replace = bool(data.get("replace", False))
        return spec


@dataclass
class Project:
    """Il progetto completo, cioe' il contenuto di un file timeline.yaml."""

    output: OutputSpec = field(default_factory=OutputSpec)
    defaults: Defaults = field(default_factory=Defaults)
    timeline: list[Segment] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    audio: AudioSpec | None = None
    root: Path = Path(".")   # i percorsi relativi si risolvono da qui

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Project":
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"File di progetto non trovato: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        project = cls.from_dict(data)
        # I percorsi nel YAML sono relativi alla cartella che contiene il YAML
        project.root = path.parent.resolve()
        return project

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        timeline_data = data.get("timeline") or []
        if not timeline_data:
            raise ConfigError("Il progetto deve avere almeno un segmento in 'timeline'")

        project = cls(
            output=OutputSpec.from_dict(data.get("output")),
            defaults=Defaults.from_dict(data.get("defaults")),
            timeline=[Segment.from_dict(s, i) for i, s in enumerate(timeline_data)],
            overlays=[Overlay.from_dict(o, i) for i, o in enumerate(data.get("overlays") or [])],
            audio=AudioSpec.from_dict(data.get("audio")),
        )
        return project

    def resolve(self, path: Path | str) -> Path:
        """Trasforma un percorso del YAML in percorso assoluto."""
        p = Path(path)
        return p if p.is_absolute() else (self.root / p).resolve()
