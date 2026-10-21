"""
Un edit: un video fatto con un template.

IL TEMPLATE E L'EDIT
--------------------
Il template e' la parte che non cambia: la musica, gli istanti dei tagli, lo
stile. L'edit e' la parte che cambia a ogni video: QUALI media vanno nei posti
e QUALI testi compaiono, dove e quando. Un file `edit.yaml` per video:

    template: ../../templates/raffica
    media:
      - media/apertura.mp4
      - media/grafico.png
    texts:
      - text: "L'ormone della crescita"
        slot: 2
        position: top

Anche l'edit e' un generatore di progetti, come il template: produce un
`timeline.yaml` (si vede con `vedit render edit.yaml --to-yaml`) che il builder
sa gia' montare. I media passano da `templates.bind`; i testi diventano overlay,
con i tempi risolti sugli istanti del template.

I TESTI
-------
Un testo dice tre cose, e solo la prima e' obbligatoria:

- **cosa**: `text`;
- **quando**: `slot: 3` (per tutto il posto 3), `slot: 3-5` (dal 3 alla fine del
  5), oppure `at: 4.2` in secondi. Con `at` dura fino al taglio successivo, a
  meno di scrivere `duration`. Agganciare un testo a un posto invece che ai
  secondi lo fa comparire e sparire sul battito, insieme all'immagine;
- **dove**: `position: top | center | bottom`, oppure un numero fra 0 e 1
  (l'altezza, 0 = in cima) o `[x, y]` in frazioni del quadro. Il testo si
  centra su quel punto, e non esce mai dallo schermo.

Lo stile viene dal template (`text:` nel template.yaml); ogni testo puo'
cambiarne qualsiasi campo (`font_size`, `color`, `bg_color`...). Le misure in
pixel si intendono sul formato del template: se l'edit esporta in un altro
formato, scalano da sole.

Modulo senza MoviePy: legge YAML e costruisce dati.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import FIT_MODES, ConfigError, Project, TextStyle, _raise_all
from .motion import names as motion_names
from .templates import (
    Bound,
    MediaRef,
    Template,
    _relative_to,
    bind,
    describe_bound,
)

# Nome del file che descrive un edit dentro la sua cartella.
MANIFEST = "edit.yaml"

# Dove si puo' mettere un testo senza fare conti: le stesse tre posizioni che
# offre qualsiasi app di montaggio da telefono.
POSITIONS = ("top", "center", "bottom")

# I campi di stile che un testo puo' cambiare rispetto al template.
STYLE_KEYS = ("font", "font_size", "color", "stroke_color", "stroke_width",
              "bg_color", "bg_opacity", "max_width", "align", "padding")

TEXT_KEYS = ("text", "slot", "at", "duration", "position", "fade", *STYLE_KEYS)
MEDIA_KEYS = ("src", "start", "loop", "fit", "motion", "amount")

# Le misure di uno stile che sono in pixel, e quindi vanno scalate se l'edit
# esporta in un formato diverso da quello del template.
PIXEL_KEYS = ("font_size", "stroke_width", "padding")

# Sotto questa durata un testo non si fa in tempo a leggerlo.
MIN_TEXT = 0.1


def _number(item: dict, key: str, where: str) -> float:
    """Un campo numerico, con un errore leggibile se c'e' scritto altro."""
    try:
        return float(item[key])
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: {key} deve essere un numero (trovato '{item[key]}')") from None


def _slot_range(value: Any, count: int, where: str) -> tuple[int, int]:
    """`3` -> (3, 3); `"3-5"` -> (3, 5). I posti si contano da 1, come nel template."""
    if isinstance(value, bool):
        raise ConfigError(f"{where}: slot deve essere un numero (es. 3) o un intervallo (es. 3-5)")
    if isinstance(value, int):
        primo = ultimo = value
    else:
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", str(value))
        if not match:
            raise ConfigError(
                f"{where}: slot '{value}' non si capisce: scrivi un numero (es. 3) "
                "o un intervallo (es. 3-5)"
            )
        primo = int(match.group(1))
        ultimo = int(match.group(2) or primo)
    if not 1 <= primo <= ultimo <= count:
        raise ConfigError(
            f"{where}: slot {value} non esiste: il template ha i posti da 1 a {count}"
        )
    return primo, ultimo


def _position(value: Any, where: str) -> str | dict[str, float]:
    """
    La posizione come la scrive chi compila l'edit, nella forma del progetto.

    Le frazioni diventano `{x, y}` e non una lista, perche' nel progetto una
    lista e' una posizione in PIXEL (l'angolo in alto a sinistra): con due
    forme diverse non c'e' modo di confonderle.
    """
    errore = ConfigError(
        f"{where}: position '{value}' non valida. Usa top, center, bottom, un numero "
        "fra 0 e 1 (l'altezza: 0 in cima, 1 in fondo) oppure [x, y] in frazioni"
    )
    if value is None:
        return "center"
    if isinstance(value, str):
        nome = value.strip().lower()
        if nome not in POSITIONS:
            raise errore
        return nome
    if isinstance(value, bool):
        raise errore
    if isinstance(value, (int, float)):
        coppia = [0.5, float(value)]
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            coppia = [float(v) for v in value]
        except (TypeError, ValueError):
            raise errore from None
    else:
        raise errore
    if not all(0.0 <= v <= 1.0 for v in coppia):
        raise errore
    return {"x": coppia[0], "y": coppia[1]}


@dataclass
class TextCue:
    """Un testo con i tempi gia' risolti in secondi sul montaggio."""

    text: str
    start: float
    end: float
    position: str | dict[str, float] = "center"
    fade: float = 0.0
    style: dict[str, Any] = field(default_factory=dict)   # solo le modifiche al template

    @property
    def duration(self) -> float:
        return self.end - self.start


def parse_text(item: Any, template: Template, index: int) -> TextCue:
    """Legge un testo dell'edit e ne risolve i tempi sugli istanti del template."""
    where = f"texts[{index}]"
    if isinstance(item, str):
        raise ConfigError(
            f"{where}: un testo e' una mappa, non solo la scritta. Esempio:\n"
            f"    - text: \"{item}\"\n      slot: 1"
        )
    if not isinstance(item, dict):
        raise ConfigError(f"{where}: ogni testo deve essere una mappa YAML")

    sconosciuti = [k for k in item if k not in TEXT_KEYS]
    if sconosciuti:
        raise ConfigError(
            f"{where}: campi sconosciuti {', '.join(map(str, sconosciuti))}. "
            f"Un testo accetta: {', '.join(TEXT_KEYS)}"
        )
    if item.get("text") in (None, ""):
        raise ConfigError(f"{where}: manca 'text', la scritta da mostrare")

    slots = template.slots
    fini = [slot.at for slot in slots[1:]] + [template.duration]

    if "slot" in item and "at" in item:
        raise ConfigError(f"{where}: scrivi 'slot' oppure 'at', non tutti e due")
    if "slot" in item:
        primo, ultimo = _slot_range(item["slot"], len(slots), where)
        start, end = slots[primo - 1].at, fini[ultimo - 1]
    elif "at" in item:
        start = _number(item, "at", where)
        if not 0 <= start < template.duration:
            raise ConfigError(
                f"{where}: at {start:g} e' fuori dal video, che dura {template.duration:g}s"
            )
        # Senza durata, fino al taglio successivo: il testo cambia sul battito.
        end = next((fine for fine in fini if fine > start + 1e-6), template.duration)
    else:
        raise ConfigError(
            f"{where}: manca QUANDO: scrivi 'slot' (es. 3, oppure 3-5) o 'at' (in secondi)"
        )

    if item.get("duration") is not None:
        durata = _number(item, "duration", where)
        if durata <= 0:
            raise ConfigError(f"{where}: duration deve essere positiva")
        end = start + durata
    end = min(end, template.duration)
    if end - start < MIN_TEXT:
        raise ConfigError(
            f"{where}: il testo durerebbe {end - start:.2f}s, troppo poco per leggerlo"
        )

    fade = _number(item, "fade", where) if item.get("fade") is not None else 0.0
    if fade < 0:
        raise ConfigError(f"{where}: fade non puo' essere negativo")

    style = {key: item[key] for key in STYLE_KEYS if item.get(key) is not None}
    # Lo stile completo si valida subito: un colore o un allineamento sbagliati
    # devono uscire adesso, con il numero del testo, non a meta' render.
    TextStyle.from_dict({**template.text_style, **style}, where)

    return TextCue(
        text=str(item["text"]),
        start=round(start, 3),
        end=round(end, 3),
        position=_position(item.get("position"), where),
        fade=fade,
        style=style,
    )


def parse_media(item: Any, root: Path, index: int) -> MediaRef:
    """Un media dell'edit: un percorso (con `@secondi` facoltativo) o una mappa."""
    where = f"media[{index}]"
    if isinstance(item, str):
        ref = MediaRef.parse(item)
    elif isinstance(item, dict):
        sconosciuti = [k for k in item if k not in MEDIA_KEYS]
        if sconosciuti:
            raise ConfigError(
                f"{where}: campi sconosciuti {', '.join(map(str, sconosciuti))}. "
                f"Un media accetta: {', '.join(MEDIA_KEYS)}"
            )
        if not item.get("src"):
            raise ConfigError(f"{where}: manca 'src', il percorso del file")
        ref = MediaRef.parse(str(item["src"]))
        if item.get("start") is not None:
            ref.start = _number(item, "start", where)
        if item.get("loop") is not None:
            ref.loop = bool(item["loop"])
        if item.get("fit") is not None:
            ref.fit = str(item["fit"]).strip().lower()
            if ref.fit not in FIT_MODES:
                raise ConfigError(f"{where}: fit deve essere uno di {', '.join(FIT_MODES)}")
        if "motion" in item:
            # `motion: none` (o vuoto) toglie il movimento suggerito dal template.
            valore = item["motion"]
            ref.motion = "" if valore in (None, "", "none") else str(valore).strip().lower()
            if ref.motion and ref.motion not in motion_names():
                raise ConfigError(
                    f"{where}: motion '{ref.motion}' non esiste. "
                    f"Disponibili: {', '.join(motion_names())}, oppure none"
                )
        if item.get("amount") is not None:
            ref.amount = _number(item, "amount", where)
    else:
        raise ConfigError(f"{where}: ogni media e' un percorso o una mappa con 'src'")

    if not ref.path.is_absolute():
        ref.path = (root / ref.path).resolve()
    return ref


@dataclass
class Edit:
    """Un video fatto con un template: i media nei posti, i testi sopra."""

    template: Template
    media: list[MediaRef] = field(default_factory=list)
    texts: list[TextCue] = field(default_factory=list)
    name: str = ""
    output: Path | None = None
    size: tuple[int, int] | None = None
    fps: int | None = None
    keep_audio: bool = False
    volume: float | None = None
    root: Path = Path(".")

    @classmethod
    def from_yaml(cls, path: str | Path) -> Edit:
        """Carica un edit. `path` puo' essere il file o la cartella che lo contiene."""
        path = Path(path)
        if path.is_dir():
            path = path / MANIFEST
        if not path.exists():
            raise ConfigError(f"Edit non trovato: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        root = path.parent.resolve()
        return cls.from_dict(data, root=root, name=root.name)

    @classmethod
    def from_dict(cls, data: dict, root: Path, name: str = "") -> Edit:
        if not isinstance(data, dict):
            raise ConfigError("Un edit deve contenere una mappa YAML")
        if not data.get("template"):
            raise ConfigError(
                "Un edit deve dire su quale template e' costruito: "
                "template: ../../templates/<nome>"
            )
        template_path = Path(str(data["template"])).expanduser()
        if not template_path.is_absolute():
            template_path = root / template_path
        template = Template.from_yaml(template_path)

        media_data = data.get("media") or []
        if not isinstance(media_data, list) or not media_data:
            raise ConfigError(
                f"L'edit non ha media: servono fino a {len(template.slots)} file "
                "nella lista 'media', uno per posto"
            )

        # Come in un progetto, si raccolgono tutti gli errori prima di
        # arrendersi: tre testi sbagliati devono produrre tre messaggi.
        errors: list[str] = []
        media: list[MediaRef] = []
        for i, item in enumerate(media_data):
            try:
                media.append(parse_media(item, root, i))
            except ConfigError as exc:
                errors.append(str(exc))
        texts: list[TextCue] = []
        texts_data = data.get("texts") or []
        if not isinstance(texts_data, list):
            errors.append("texts deve essere una lista di testi")
            texts_data = []
        for i, item in enumerate(texts_data):
            try:
                texts.append(parse_text(item, template, i))
            except ConfigError as exc:
                errors.append(str(exc))
        _raise_all(errors, "L'edit contiene errori")

        edit = cls(template=template, media=media, texts=texts, name=name, root=root)
        if data.get("output"):
            edit.output = Path(str(data["output"]))
        if data.get("size") is not None:
            size = data["size"]
            if not isinstance(size, (list, tuple)) or len(size) != 2:
                raise ConfigError("size deve essere una lista [larghezza, altezza]")
            edit.size = (int(size[0]), int(size[1]))
        if data.get("fps") is not None:
            edit.fps = int(data["fps"])
        edit.keep_audio = bool(data.get("keep_audio", False))
        if data.get("volume") is not None:
            edit.volume = float(data["volume"])
        return edit

    # ----------------------------------------------------------------------
    # Dall'edit al progetto
    # ----------------------------------------------------------------------

    @property
    def output_path(self) -> Path:
        return self.output or Path("output") / f"{self.name or self.template.name}.mp4"

    def bind(self, durations: dict[Path, float] | None = None,
             root: Path | None = None) -> Bound:
        """
        Il progetto completo: i media negli slot (templates.bind), i testi sopra.

        `root` e' la cartella da cui scrivere i percorsi del progetto: quella
        dell'edit, a meno di salvare il progetto altrove con --to-yaml.
        """
        base = Path(root) if root is not None else self.root
        output = self.output_path
        if root is not None and not output.is_absolute():
            output = Path(_relative_to(self.root / output, base))

        bound = bind(
            self.template, self.media,
            output=output, size=self.size, fps=self.fps,
            keep_audio=self.keep_audio, volume=self.volume,
            root=base, durations=durations,
        )
        canvas = tuple(bound.data["output"]["size"])
        bound.data["overlays"] = [self._overlay(cue, canvas) for cue in self.texts]
        bound.warnings.extend(text_warnings(self.texts))
        return bound

    def _overlay(self, cue: TextCue, canvas: tuple[int, int]) -> dict[str, Any]:
        """Un testo come overlay del progetto, con lo stile del template e le sue modifiche."""
        style = {**self.template.text_style, **cue.style}
        # Le misure in pixel sono pensate sul formato del template: se l'edit
        # esporta in un altro formato, il testo deve restare proporzionato.
        fattore = canvas[0] / self.template.size[0]
        if abs(fattore - 1.0) > 1e-6:
            for key in PIXEL_KEYS:
                if style.get(key):
                    style[key] = max(1, round(float(style[key]) * fattore))
            if style.get("max_width") and float(style["max_width"]) > 1:
                style["max_width"] = round(float(style["max_width"]) * fattore)
        overlay: dict[str, Any] = {
            "type": "text",
            "text": cue.text,
            "start": cue.start,
            "duration": round(cue.duration, 3),
            "position": cue.position,
        }
        if cue.fade:
            overlay["fade"] = cue.fade
        overlay.update(style)
        return overlay

    def project(self, durations: dict[Path, float] | None = None) -> Project:
        """Il Project pronto per il builder."""
        return self.bind(durations).project(self.root)

    def describe(self, bound: Bound, texts: bool = True) -> str:
        """Il piano dell'edit: chi va in quale posto, e (se richiesto) quali testi quando."""
        lines = [describe_bound(self.template, bound)]
        if texts and self.texts:
            lines += ["", f"Testi ({len(self.texts)}):", "     dal       al   dove      testo"]
            for cue in self.texts:
                dove = (cue.position if isinstance(cue.position, str)
                        else f"{cue.position['x']:g},{cue.position['y']:g}")
                testo = cue.text.replace("\n", " / ")
                lines.append(f"  {cue.start:7.2f}  {cue.end:7.2f}   {dove:<8}  {testo}")
        return "\n".join(lines)


def text_warnings(texts: list[TextCue]) -> list[str]:
    """Due testi nello stesso posto dello schermo, nello stesso momento, si coprono."""
    avvisi = []
    for i, primo in enumerate(texts):
        for j in range(i + 1, len(texts)):
            secondo = texts[j]
            if primo.position != secondo.position:
                continue
            if primo.start < secondo.end - 1e-6 and secondo.start < primo.end - 1e-6:
                avvisi.append(
                    f"texts[{i}] e texts[{j}] sono nella stessa posizione e si "
                    f"sovrappongono fra {max(primo.start, secondo.start):.2f}s e "
                    f"{min(primo.end, secondo.end):.2f}s: verranno disegnati uno sull'altro"
                )
    return avvisi


def is_edit(data: Any) -> bool:
    """Un YAML e' un edit se dice su quale template e' costruito."""
    return isinstance(data, dict) and "template" in data and "timeline" not in data


# --------------------------------------------------------------------------
# Lo scheletro di un edit nuovo
# --------------------------------------------------------------------------

def skeleton(template: Template, template_path: Path, root: Path, name: str,
             media: list[MediaRef] | None = None) -> str:
    """
    Il testo di un `edit.yaml` nuovo, commentato posto per posto.

    Scritto a mano invece che con yaml.dump per poter mettere accanto a ogni
    media il suo posto: quando entra, quanto dura, cosa c'era nel riferimento.
    E' la tabella che serve per decidere dove mettere un video e dove una foto.
    """
    gaps = template.gaps()
    tempo = f", {template.audio.bpm:g} BPM" if template.audio.bpm else ""
    comando = _relative_to(root / MANIFEST, Path.cwd())
    righe = [
        "# ---------------------------------------------------------------------------",
        f"# EDIT: {name}",
        "#",
        "# Il template decide QUANDO si stacca: la musica, i tagli, lo stile.",
        "# Qui decidi COSA si vede: un media per posto, in ordine, e i testi.",
        "#",
        f"#   vedit render {comando} --check     cosa cade dove",
        f"#   vedit render {comando} --preview   anteprima veloce",
        f"#   vedit render {comando}             il video finale",
        "# ---------------------------------------------------------------------------",
        "",
        f"template: {_quote(_portable(template_path, root))}"
        f"      # {len(template.slots)} posti{tempo}, {template.duration:.2f}s, "
        f"{template.size[0]}x{template.size[1]}",
        "",
        "# Un media per posto, in quest'ordine: immagini, video e GIF vanno bene",
        "# ovunque. Il commento dice quando entra il posto, quanto dura e cosa c'era",
        "# nel video di riferimento. Un video parte dall'inizio; `file.mp4@12.5`",
        "# lo fa partire dal secondo 12.5. Una GIF corta riparte da capo.",
        "media:",
    ]
    for i, slot in enumerate(template.slots):
        if media:
            ref = media[i % len(media)]
            valore = _relative_to(ref.path, root)
            if ref.start:
                valore += f"@{ref.start:g}"
        else:
            estensione = ".mp4" if slot.hint == "video" else ".jpg"
            valore = f"media/{i + 1:02d}{estensione}"
        commento = f"{i + 1:2d})  {slot.at:6.2f}s  dura {gaps[i]:.2f}s"
        if slot.hint:
            commento += f"  {slot.hint}"
        righe.append(f"  - {_quote(valore):<28} # {commento}")

    righe += [
        "",
        "# I testi. QUANDO: slot: 3 (tutto il posto 3), slot: 3-5 (dal 3 alla fine",
        "# del 5) oppure at: 4.2 (secondi; dura fino al taglio dopo, o duration).",
        "# DOVE: position: top, center o bottom, oppure un numero fra 0 e 1",
        "# (l'altezza) o [x, y]. Lo stile e' quello del template; ogni testo puo'",
        "# cambiarlo: font_size, color, stroke_color, bg_color, bg_opacity, align...",
        "texts: []",
        "#  - text: \"Il tuo testo\"",
        "#    slot: 2-4",
        "#    position: top",
        "",
    ]
    return "\n".join(righe)


def _portable(path: Path, root: Path) -> str:
    """
    Il percorso del template visto dall'edit, sempre relativo.

    Per i media vale la regola di `_relative_to` (relativo solo se sta dentro la
    cartella), ma il template e' diverso: sta nel repo come l'edit, e un
    `../../templates/nome` resta giusto su qualsiasi macchina cloni il repo,
    mentre un percorso assoluto vale solo su quella che l'ha scritto.
    """
    try:
        return os.path.relpath(Path(path).resolve(), Path(root).resolve())
    except ValueError:                      # dischi diversi, su Windows
        return str(Path(path).resolve())


def _quote(value: str) -> str:
    """Un percorso come valore YAML: tra virgolette solo se serve."""
    testo = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True)
    return testo.split("\n...")[0].strip()
