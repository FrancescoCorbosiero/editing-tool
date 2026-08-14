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

# transitions.py e motion.py sono registry senza dipendenze pesanti: importarli
# qui non viola il confine "models non conosce MoviePy" (vedi i loro docstring).
from .motion import names as motion_names
from .transitions import DIRECTIONS, TransitionRequest, normalize_direction
from .transitions import get as get_transition
from .transitions import names as transition_names


def transition_overlaps(name: str) -> bool:
    """True se quella transizione fa coesistere i due clip nel tempo."""
    return get_transition(name).overlaps

# Movimento massimo accettato: oltre il 200% quasi certamente e' un errore di
# battitura (amount: 20 invece di 0.20), e il render diventerebbe lentissimo.
MAX_MOTION_AMOUNT = 2.0

# Modalita' di adattamento di un'immagine/video al canvas di output
FIT_MODES = ("contain", "cover", "stretch")

# Estensioni riconosciute come file di font: un `font` che finisce cosi' e' un
# percorso da verificare, qualsiasi altra stringa e' un nome di font di sistema.
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".woff", ".woff2")


def _looks_like_font_file(value: str) -> bool:
    return Path(value).suffix.lower() in FONT_SUFFIXES


def _even_down(value: float) -> int:
    """Arrotonda al pari inferiore: libx264 rifiuta le dimensioni dispari."""
    n = int(value)
    return max(2, n - n % 2)


def _scale_position(position: Any, factor: float) -> Any:
    """Riscala una posizione, lasciando stare le parole ('center', 'top'...)."""
    if isinstance(position, (list, tuple)):
        return tuple(
            round(p * factor) if isinstance(p, (int, float)) else p
            for p in position
        )
    if isinstance(position, (int, float)):
        return round(position * factor)
    return position


def _scale_style(style: TextStyle, factor: float) -> None:
    """Riscala corpo, contorno e riempimento di uno stile di testo."""
    style.font_size = max(1, round(style.font_size * factor))
    style.padding = round(style.padding * factor)
    style.stroke_width = round(style.stroke_width * factor)
    # max_width <= 1 e' una frazione del canvas: si riscala da sola.
    if style.max_width is not None and style.max_width > 1:
        style.max_width = max(1.0, round(style.max_width * factor))


def _validate_transition_type(value: Any, where: str) -> str:
    name = str(value).strip().lower()
    if name not in transition_names():
        raise ConfigError(
            f"{where}: transition_type '{name}' non esiste. "
            f"Disponibili: {', '.join(transition_names())}"
        )
    return name


def _validate_motion(value: Any, where: str) -> str:
    name = str(value).strip().lower()
    if name not in motion_names():
        raise ConfigError(
            f"{where}: motion '{name}' non esiste. Disponibili: {', '.join(motion_names())}"
        )
    return name


def _validate_direction(value: Any, where: str) -> str:
    direction = normalize_direction(value)
    if direction not in DIRECTIONS:
        raise ConfigError(
            f"{where}: direction '{value}' non valida. Usa una di {', '.join(DIRECTIONS)} "
            "(accettati anche up/down)"
        )
    return direction


class ConfigError(ValueError):
    """Errore di configurazione del progetto (YAML malformato o valori invalidi)."""


def _require(data: dict, key: str, where: str) -> Any:
    if key not in data:
        raise ConfigError(f"Campo obbligatorio mancante: '{key}' in {where}")
    return data[key]


def _collect(errors: list[str], fn, *args, **kwargs):
    """
    Esegue `fn` accumulando l'eventuale ConfigError invece di propagarlo.

    Serve a segnalare TUTTI i problemi di un file YAML in un colpo solo:
    correggerne uno alla volta, rilanciando il comando dopo ogni fix, e' il
    modo piu' lento possibile di sistemare un progetto.
    """
    try:
        return fn(*args, **kwargs)
    except ConfigError as exc:
        errors.append(str(exc))
        return None


def _raise_all(errors: list[str], intro: str) -> None:
    """Solleva un unico ConfigError che elenca tutti i problemi raccolti."""
    if not errors:
        return
    if len(errors) == 1:
        raise ConfigError(errors[0])
    lines = "\n".join(f"  - {e}" for e in errors)
    raise ConfigError(f"{intro} ({len(errors)}):\n{lines}")


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
    def from_dict(cls, data: dict | None) -> OutputSpec:
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

    transition: float = 0.0      # durata della transizione fra un segmento e il successivo
    transition_type: str = "crossfade"
    direction: str = "left"      # bordo di provenienza per slide e wipe
    image_duration: float = 4.0  # durata di un'immagine se non indicata
    fit: str = "cover"

    @classmethod
    def from_dict(cls, data: dict | None) -> Defaults:
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
        if "transition_type" in data:
            d.transition_type = _validate_transition_type(data["transition_type"], "defaults")
        if "direction" in data:
            d.direction = _validate_direction(data["direction"], "defaults")
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
    at: float | None = None        # istante sul MONTAGGIO in cui entra in scena
    fit: str | None = None
    transition: float | None = None       # durata della transizione in ENTRATA
    transition_type: str | None = None    # vedi vedit/transitions.py
    direction: str | None = None          # bordo di provenienza per slide e wipe
    speed: float = 1.0
    mute: bool = False
    color: tuple[int, int, int] = (0, 0, 0)
    motion: str | None = None      # solo per image: vedi vedit/motion.py
    amount: float = 0.15           # quanto movimento: 0.15 = ingrandimento del 15%
    label: str = ""                # solo per leggibilita' nei log

    @classmethod
    def from_dict(cls, data: dict, index: int) -> Segment:
        where = f"timeline[{index}]"
        seg_type = str(_require(data, "type", where)).lower()
        if seg_type not in ("video", "image", "color"):
            raise ConfigError(f"{where}: type deve essere video, image o color")

        seg = cls(type=seg_type, label=str(data.get("label", "")))

        if seg_type in ("video", "image"):
            seg.src = Path(_require(data, "src", where))

        for key in ("start", "end", "duration", "transition", "at"):
            if data.get(key) is not None:
                setattr(seg, key, float(data[key]))

        if seg.at is not None and seg.at < 0:
            raise ConfigError(f"{where}: at non puo' essere negativo")

        if "speed" in data:
            seg.speed = float(data["speed"])
            if seg.speed <= 0:
                raise ConfigError(f"{where}: speed deve essere > 0")

        seg.mute = bool(data.get("mute", False))

        if "fit" in data:
            seg.fit = str(data["fit"])
            if seg.fit not in FIT_MODES:
                raise ConfigError(f"{where}: fit deve essere uno di {FIT_MODES}")

        if data.get("transition_type") is not None:
            seg.transition_type = _validate_transition_type(data["transition_type"], where)

        if data.get("direction") is not None:
            seg.direction = _validate_direction(data["direction"], where)

        if data.get("motion") is not None:
            if seg_type != "image":
                raise ConfigError(
                    f"{where}: motion si applica solo ai segmenti 'image' "
                    f"(questo e' '{seg_type}')"
                )
            seg.motion = _validate_motion(data["motion"], where)

        if data.get("amount") is not None:
            seg.amount = float(data["amount"])
            if not 0 < seg.amount <= MAX_MOTION_AMOUNT:
                raise ConfigError(
                    f"{where}: amount deve stare fra 0 e {MAX_MOTION_AMOUNT:g} "
                    "(e' una frazione: 0.2 = 20%)"
                )

        if "color" in data:
            seg.color = tuple(int(c) for c in data["color"])  # type: ignore[assignment]

        if seg_type == "video" and seg.start is not None and seg.end is not None:
            if seg.end <= seg.start:
                raise ConfigError(f"{where}: end deve essere maggiore di start")

        # `at` rende la durata deducibile - la chiude il taglio successivo -
        # quindi qui si pretende solo quando il montaggio va a durate.
        if seg_type == "color" and seg.duration is None and seg.at is None:
            raise ConfigError(f"{where}: un segmento 'color' richiede 'duration'")

        return seg

    def timeline_duration(
        self, defaults: Defaults, source_duration: float | None = None
    ) -> float | None:
        """
        Quanti secondi occupa questo segmento nella timeline.

        Per un video senza `end` la durata dipende dal file: passa
        `source_duration` (letta con ffprobe) oppure accetta None come risposta.
        Attenzione a `speed`: divide la durata, perche' a velocita' 2x sette
        secondi di sorgente ne occupano tre e mezzo sul montaggio.
        """
        if self.type in ("image", "color"):
            return self.duration if self.duration is not None else defaults.image_duration

        start = self.start or 0.0
        end = self.end if self.end is not None else source_duration
        if end is None:
            return None
        return max(end - start, 0.0) / self.speed

    def transition_request(self, defaults: Defaults) -> TransitionRequest:
        """
        Come questo segmento entra in scena: durata, tipo, direzione.

        Quello che il segmento dichiara vince sul default globale, campo per
        campo: si puo' cambiare solo il tipo e tenere la durata del progetto.
        """
        return TransitionRequest(
            duration=self.transition if self.transition is not None else defaults.transition,
            type=self.transition_type or defaults.transition_type,
            direction=self.direction or defaults.direction,
        )

    def describe(self) -> str:
        """Etichetta breve per log e riepiloghi: label se c'e', altrimenti il file."""
        if self.label:
            return self.label
        if self.src is not None:
            return Path(self.src).name
        return self.type


@dataclass
class TextStyle:
    """
    Aspetto di un testo su video, condiviso da overlay e sottotitoli.

    I due mestieri sono lo stesso mestiere: rendere leggibile del testo sopra
    un'immagine che non controlli. Le tre difese, in ordine di efficacia, sono
    il contorno (`stroke`), lo sfondo semitrasparente (`bg_color` + `bg_opacity`)
    e infine il corpo grande.
    """

    font: str | None = None        # percorso a un .ttf/.otf o nome di font installato
    font_size: int = 48
    color: str = "white"
    stroke_color: str | None = None   # contorno: staccalo dallo sfondo
    stroke_width: int = 0
    bg_color: Any = None           # nome ("black") o [R, G, B]; None = nessuno sfondo
    bg_opacity: float = 0.6        # 0 trasparente, 1 pieno
    max_width: float | None = None  # <= 1 frazione del canvas, > 1 pixel
    align: str = "center"          # allineamento delle righe: left | center | right
    padding: int = 0               # spazio fra testo e bordo dello sfondo, in pixel

    @classmethod
    def from_dict(cls, data: dict, where: str, **overrides: Any) -> TextStyle:
        style = cls(**overrides)
        for key in ("font_size", "stroke_width", "padding"):
            if data.get(key) is not None:
                setattr(style, key, int(data[key]))
        for key in ("color", "stroke_color", "font"):
            if data.get(key) is not None:
                setattr(style, key, str(data[key]))
        if data.get("bg_color") is not None:
            style.bg_color = data["bg_color"]
        if data.get("bg_opacity") is not None:
            style.bg_opacity = float(data["bg_opacity"])
        if data.get("max_width") is not None:
            style.max_width = float(data["max_width"])
        if data.get("align") is not None:
            style.align = str(data["align"]).lower()

        if style.align not in ("left", "center", "right"):
            raise ConfigError(f"{where}: align deve essere left, center o right")
        if not 0.0 <= style.bg_opacity <= 1.0:
            raise ConfigError(f"{where}: bg_opacity deve stare fra 0 e 1")
        if style.stroke_width < 0:
            raise ConfigError(f"{where}: stroke_width non puo' essere negativo")
        if style.max_width is not None and style.max_width <= 0:
            raise ConfigError(f"{where}: max_width deve essere positivo")
        return style

    def wrap_width(self, canvas_width: int) -> int | None:
        """
        Larghezza massima in pixel entro cui mandare a capo il testo.

        `max_width: 0.8` significa "l'80% del canvas" e resta valido se domani
        esporti lo stesso progetto in un'altra risoluzione; `max_width: 900`
        e' invece un numero di pixel. La soglia e' 1: nessuno vuole un testo
        largo un pixel.
        """
        if self.max_width is None:
            return None
        if self.max_width <= 1.0:
            return max(1, round(canvas_width * self.max_width))
        return int(self.max_width)


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
    style: TextStyle = field(default_factory=TextStyle)

    @classmethod
    def from_dict(cls, data: dict, index: int) -> Overlay:
        where = f"overlays[{index}]"
        ov_type = str(_require(data, "type", where)).lower()
        if ov_type not in ("image", "text"):
            raise ConfigError(f"{where}: type deve essere image o text")

        ov = cls(type=ov_type)
        if ov_type == "image":
            ov.src = Path(_require(data, "src", where))
        else:
            ov.text = str(_require(data, "text", where))
            # 64px e' un corpo da cartello a tutto schermo; i sottotitoli, che
            # devono farsi dimenticare, partono piu' piccoli.
            ov.style = TextStyle.from_dict(data, where, font_size=64)

        for key in ("start", "duration", "fade", "opacity"):
            if data.get(key) is not None:
                setattr(ov, key, float(data[key]))
        for key in ("width", "height"):
            if data.get(key) is not None:
                setattr(ov, key, int(data[key]))
        if "position" in data:
            pos = data["position"]
            ov.position = tuple(pos) if isinstance(pos, list) else pos

        return ov


@dataclass
class SubtitlesSpec:
    """
    Sottotitoli caricati da un file .srt e disegnati sopra tutto il montaggio.

    A differenza degli overlay non si dichiarano uno per uno: tempi e testo
    stanno nell'srt, qui si decide solo come appaiono e dove.
    """

    src: Path
    style: TextStyle = field(default_factory=TextStyle)
    margin_bottom: int = 60        # distanza dal bordo inferiore, in pixel
    offset: float = 0.0            # sposta tutti i tempi: per rimettere in sync un srt

    @classmethod
    def from_dict(cls, data: dict | None) -> SubtitlesSpec | None:
        if not data:
            return None
        where = "subtitles"
        spec = cls(src=Path(_require(data, "src", where)))
        # Valori di partenza pensati per essere leggibili su qualsiasi immagine:
        # bianco con contorno nero, larghi al massimo l'80% del canvas.
        spec.style = TextStyle.from_dict(
            data, where,
            font_size=48, color="white", stroke_color="black", stroke_width=2,
            max_width=0.8, align="center", padding=8,
        )
        if data.get("margin_bottom") is not None:
            spec.margin_bottom = int(data["margin_bottom"])
        if data.get("offset") is not None:
            spec.offset = float(data["offset"])
        return spec


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
    def from_dict(cls, data: dict | None) -> AudioSpec | None:
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
    subtitles: SubtitlesSpec | None = None
    root: Path = Path(".")   # i percorsi relativi si risolvono da qui

    @classmethod
    def from_yaml(cls, path: str | Path) -> Project:
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
    def from_dict(cls, data: dict) -> Project:
        if not isinstance(data, dict):
            raise ConfigError("Il file di progetto deve contenere una mappa YAML")

        timeline_data = data.get("timeline") or []
        if not timeline_data:
            raise ConfigError("Il progetto deve avere almeno un segmento in 'timeline'")

        # Si raccolgono tutti gli errori di tutte le sezioni prima di arrendersi:
        # un YAML con tre sbagli deve produrre tre messaggi, non tre esecuzioni.
        errors: list[str] = []
        output = _collect(errors, OutputSpec.from_dict, data.get("output")) or OutputSpec()
        defaults = _collect(errors, Defaults.from_dict, data.get("defaults")) or Defaults()

        segments = [_collect(errors, Segment.from_dict, s, i) for i, s in enumerate(timeline_data)]
        overlays = [
            _collect(errors, Overlay.from_dict, o, i)
            for i, o in enumerate(data.get("overlays") or [])
        ]
        audio = _collect(errors, AudioSpec.from_dict, data.get("audio"))
        subtitles = _collect(errors, SubtitlesSpec.from_dict, data.get("subtitles"))

        _raise_all(errors, "Il progetto contiene errori")

        return cls(
            output=output,
            defaults=defaults,
            timeline=[s for s in segments if s is not None],
            overlays=[o for o in overlays if o is not None],
            audio=audio,
            subtitles=subtitles,
        )

    def resolve(self, path: Path | str) -> Path:
        """Trasforma un percorso del YAML in percorso assoluto."""
        p = Path(path)
        return p if p.is_absolute() else (self.root / p).resolve()

    # ----------------------------------------------------------------------
    # Montaggio a istanti dichiarati (`at`)
    # ----------------------------------------------------------------------

    def cut_positions(self) -> list[float] | None:
        """
        Gli istanti in cui cambia la scena, se il progetto li dichiara con `at`.

        Due modi di scrivere un montaggio, e questo sceglie quale si sta usando:

        - **a durate**: ogni segmento dice quanto dura, e la sua posizione e' la
          somma di quelli prima. Comodo per un racconto, pessimo per la musica:
          allungare il terzo spezzone di un decimo sposta di un decimo TUTTI i
          tagli successivi, che erano a tempo e non lo sono piu'.

        - **a istanti** (`at`): ogni segmento dichiara il momento in cui entra.
          Spostare un taglio muove quel taglio e basta. Le durate si ricavano da
          sole: un segmento finisce quando comincia il successivo.

        Restituisce None se il progetto usa le durate.
        """
        declared = [seg.at for seg in self.timeline]
        if all(value is None for value in declared):
            return None
        return [value if value is not None else 0.0 for value in declared]

    def validate_positions(self) -> None:
        """Controlla che gli istanti dichiarati abbiano senso."""
        declared = [seg.at for seg in self.timeline]
        if all(value is None for value in declared):
            return

        errors: list[str] = []
        for i, value in enumerate(declared):
            if value is None:
                errors.append(
                    f"timeline[{i}]: manca 'at'. In un montaggio a istanti devono "
                    "averlo tutti i segmenti, altrimenti meta' timeline si "
                    "posiziona da sola e meta' no"
                )
        _raise_all(errors, "Il progetto mescola durate e istanti")

        if declared[0] != 0:
            raise ConfigError(
                f"timeline[0]: il primo segmento deve avere at: 0 (trovato {declared[0]:g}). "
                "Il montaggio comincia dal primo segmento, non dal nero"
            )
        for i in range(1, len(declared)):
            if declared[i] <= declared[i - 1]:
                raise ConfigError(
                    f"timeline[{i}]: at {declared[i]:g} non viene dopo "
                    f"timeline[{i - 1}] (at {declared[i - 1]:g}). Gli istanti "
                    "devono crescere: sono momenti sulla stessa linea del tempo"
                )

        # L'ultimo segmento e' l'unico senza un taglio dopo di se' che lo chiuda:
        # deve sapere da solo dove finisce.
        last = self.timeline[-1]
        if last.timeline_duration(self.defaults) is None:
            raise ConfigError(
                f"timeline[{len(self.timeline) - 1}]: l'ultimo segmento deve dire dove "
                "finisce ('end' nel sorgente, oppure 'duration'). Tutti gli altri li "
                "chiude il taglio successivo, lui no"
            )

        # Le transizioni che sovrappongono i clip convivono con `at`, ma solo
        # perche' in questo modo il clip che entra viene tirato indietro e non
        # in avanti (vedi timeline.plan_anchored): l'istante dichiarato e' il
        # momento in cui la transizione ha FINITO di entrare. Resta un limite
        # fisico - una dissolvenza non puo' cominciare prima del taglio
        # precedente - e chi scrive il YAML se lo merita scritto, non troncato
        # in silenzio.
        for i, seg in enumerate(self.timeline):
            if i == 0:
                continue
            request = seg.transition_request(self.defaults)
            if request.duration <= 0 or not transition_overlaps(request.type):
                continue
            spazio = declared[i] - declared[i - 1]
            if request.duration > spazio:
                raise ConfigError(
                    f"timeline[{i}]: la transizione '{request.type}' dura "
                    f"{request.duration:g}s ma fra questo taglio e il precedente ci sono "
                    f"{spazio:g}s. Una dissolvenza non puo' cominciare prima del clip "
                    "da cui dissolve: accorciala, o allontana i due istanti"
                )

    def scale(self, factor: float) -> None:
        """
        Riscala il progetto: canvas, posizioni, corpi del testo, margini.

        Serve all'anteprima. Dimezzare solo il canvas e lasciare le coordinate
        com'erano sposterebbe gli overlay fuori dal quadro - un titolo a
        `y: 820` su un canvas alto 540 semplicemente non si vede - e
        un'anteprima che non mostra dove finisce il testo non serve a niente.

        Le misure espresse in frazione (`max_width: 0.8`) non si toccano:
        sono gia' relative al canvas, ed e' il motivo per cui conviene usarle.
        """
        def px(value: float) -> int:
            return max(1, round(value * factor))

        self.output.size = (_even_down(self.output.size[0] * factor),
                            _even_down(self.output.size[1] * factor))

        for ov in self.overlays:
            ov.position = _scale_position(ov.position, factor)
            if ov.width:
                ov.width = px(ov.width)
            if ov.height:
                ov.height = px(ov.height)
            _scale_style(ov.style, factor)

        if self.subtitles is not None:
            _scale_style(self.subtitles.style, factor)
            self.subtitles.margin_bottom = px(self.subtitles.margin_bottom)

    # ----------------------------------------------------------------------
    # Verifica dei file referenziati
    # ----------------------------------------------------------------------

    def referenced_files(self) -> list[tuple[str, Path]]:
        """
        Tutti i file che il progetto si aspetta di trovare su disco,
        come coppie (descrizione leggibile, percorso assoluto).
        """
        refs: list[tuple[str, Path]] = []

        for i, seg in enumerate(self.timeline):
            if seg.src is not None:
                refs.append((f"timeline[{i}] ({seg.describe()})", self.resolve(seg.src)))

        for i, ov in enumerate(self.overlays):
            if ov.src is not None:
                refs.append((f"overlays[{i}] (immagine)", self.resolve(ov.src)))
            if ov.style.font and _looks_like_font_file(ov.style.font):
                refs.append((f"overlays[{i}] (font)", self.resolve(ov.style.font)))

        if self.audio is not None:
            refs.append(("audio", self.resolve(self.audio.src)))

        if self.subtitles is not None:
            refs.append(("subtitles", self.resolve(self.subtitles.src)))
            font = self.subtitles.style.font
            if font and _looks_like_font_file(font):
                refs.append(("subtitles (font)", self.resolve(font)))

        return refs

    def missing_files(self) -> list[str]:
        """
        Elenca i file referenziati che non esistono, uno per riga.

        Il controllo e' fatto in blocco PRIMA di iniziare il render: scoprire
        al minuto tre di export che manca l'ultima immagine e' il modo peggiore
        di perdere tempo.
        """
        return [
            f"{where}: file non trovato: {path}"
            for where, path in self.referenced_files()
            if not path.exists()
        ]

    def validate_files(self) -> None:
        """Solleva un unico ConfigError che elenca tutti i file mancanti."""
        _raise_all(self.missing_files(), "File referenziati ma non trovati")
