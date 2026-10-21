"""
Vedere e cambiare i posti di un template: dove stacca, a orecchio.

PERCHE'
-------
Un template estratto ha i tagli del video di riferimento, e soltanto quelli. Chi
ascolta la canzone pero' puo' sentirne altri: un colpo di basso su cui il
riferimento non cambiava immagine, quattro stacchi al drop dove ce n'erano tre.
Non e' un errore del rilevatore - il riferimento era montato cosi' - e' gusto,
e nessun algoritmo lo puo' indovinare.

Correggere a mano gli `at` del template.yaml funziona, ma obbliga a fare i conti
col battito. Qui le correzioni si dicono come le direbbe chi ascolta:

    --cut 4.45     "a 4.45 c'e' un colpo": un taglio, sul mezzo battito piu' vicino
    --split 4      "il posto 4 in due"   (con --into 4: in quattro)
    --merge 5      "fra il 4 e il 5 non staccare"

COME
----
Ogni modifica e' un'operazione sull'insieme degli istanti dei tagli: si tolgono
quelli dei posti uniti, si aggiungono quelli nuovi, e i posti si ricostruiscono
dagli istanti. Per questo i numeri si riferiscono SEMPRE all'elenco di prima
del comando, anche quando le operazioni sono piu' d'una: `--split 4 --merge 10`
divide il 4 e unisce il 10 di adesso, non il 10 che verrebbe fuori dopo la
divisione.

Un `--cut` si allinea alla griglia del battito del template (`audio.bpm`,
`audio.offset`): un colpo segnato a orecchio cade sempre un po' prima o un po'
dopo, e la griglia rimette il taglio dove lo vuole la musica. Un `--split`
invece divide in parti uguali, senza griglia: un posto lungo un battito diviso
in due da' due mezzi battiti esatti, in tre una terzina.

Modulo senza MoviePy: legge e scrive il template.yaml e disegna i cartelli con
Pillow. Il video dei posti numerati lo monta il builder, chiamato da cli.py.
"""

from __future__ import annotations

import colorsys
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from .edit import MANIFEST as EDIT_MANIFEST
from .extract import GRIDS, HINT_MIN_SLOT, MOTION_MIN_SLOT
from .models import ConfigError, TextStyle
from .templates import MANIFEST, AudioTrack, Slot, Template
from .text import render_text


@dataclass
class Retimed:
    """Il risultato di una modifica: il template nuovo, e che cosa e' cambiato."""

    template: Template
    added: list[float] = field(default_factory=list)     # istanti dei tagli nuovi
    removed: list[float] = field(default_factory=list)   # istanti dei tagli tolti
    # Per ogni posto di prima (da 0), il posto (da 0) in cui si trova adesso: un
    # posto unito finisce in quello che l'ha assorbito.
    numbers: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def parse_time(value: str | float) -> float:
    """
    Un istante scritto come lo scrive una persona: `4.45`, `4,45` o `0:04.45`.

    La virgola perche' in italiano i decimali si scrivono cosi'; i minuti perche'
    e' cosi' che un lettore video mostra il punto in cui si e' fermati.
    """
    if isinstance(value, (int, float)):
        return float(value)
    testo = str(value).strip().replace(",", ".")
    minuti, sep, secondi = testo.rpartition(":")
    try:
        istante = float(secondi)
        if sep:
            istante += 60 * float(minuti or 0)
    except ValueError:
        raise ConfigError(
            f"'{value}' non e' un istante: scrivi i secondi (4.45) o minuti:secondi (0:04.45)"
        ) from None
    return istante


def snap_time(time: float, audio: AudioTrack, divisions: int) -> float:
    """L'istante della griglia piu' vicino: battiti, mezzi o quarti (0 = nessuna griglia)."""
    if not divisions or not audio.bpm:
        return round(time, 3)
    passo = audio.period / divisions
    return round(audio.offset + round((time - audio.offset) / passo) * passo, 3)


def retime(template: Template, cuts: list[str] | tuple = (), split: list[int] | tuple = (),
           into: int = 2, merge: list[int] | tuple = (), grid: str = "half") -> Retimed:
    """
    Applica le modifiche e restituisce il template nuovo; quello passato non si tocca.

    Gli errori si raccolgono tutti prima di arrendersi, come nei file YAML: chi
    sbaglia due numeri in un comando deve saperlo una volta sola.
    """
    if grid not in GRIDS:
        raise ConfigError(f"grid deve essere una di {', '.join(GRIDS)}")
    slots = template.slots
    count = len(slots)
    gaps = template.gaps()
    istanti = [slot.at for slot in slots]
    # Due tagli piu' vicini di mezzo fotogramma sono lo stesso taglio: nel video
    # finito cadrebbero sullo stesso fotogramma.
    stesso = 0.5 / template.fps
    errori: list[str] = []
    note: list[str] = []

    nuovi: dict[float, int] = {}      # istante -> posto (da 0) da cui nasce
    if split and into < 2:
        errori.append(f"--into vuole un numero da 2 in su (ricevuto {into})")
    for numero in split:
        if not 1 <= numero <= count:
            errori.append(f"--split {numero}: il template ha i posti da 1 a {count}")
            continue
        i = numero - 1
        for parte in range(1, into):
            nuovi[round(slots[i].at + gaps[i] * parte / into, 3)] = i

    for scritto in cuts:
        try:
            istante = parse_time(scritto)
        except ConfigError as exc:
            errori.append(f"--cut {exc}")
            continue
        if not 0 < istante < template.duration:
            errori.append(
                f"--cut {scritto}: il template va da 0 a {template.duration:.2f}s "
                "(i decimali si scrivono col punto: 4.45)"
            )
            continue
        # Un colpo a ridosso dell'inizio finisce sul taglio che c'e' gia' a 0.
        allineato = max(0.0, snap_time(istante, template.audio, GRIDS[grid]))
        if allineato >= template.duration:
            errori.append(f"--cut {scritto}: sulla griglia cadrebbe a {allineato:.3f}s, "
                          f"oltre la fine del template ({template.duration:.2f}s)")
            continue
        vicino = min(range(count), key=lambda k: abs(istanti[k] - allineato))
        if abs(istanti[vicino] - allineato) < stesso:
            note.append(f"a {allineato:.3f}s c'e' gia' un taglio: "
                        f"e' l'inizio del posto {vicino + 1}")
            continue
        if GRIDS[grid] and template.audio.bpm and abs(allineato - istante) >= 0.001:
            note.append(f"{scritto} -> {allineato:.3f}s, sulla griglia del battito")
        nuovi[allineato] = bisect_right(istanti, allineato) - 1

    tolti: set[int] = set()
    for numero in merge:
        if numero == 1:
            errori.append("--merge 1: il primo posto non ha un posto prima a cui unirsi")
        elif not 2 <= numero <= count:
            errori.append(f"--merge {numero}: il template ha i posti da 1 a {count}")
        else:
            tolti.add(numero - 1)

    if errori:
        raise ConfigError("Non posso cambiare i posti:\n" + "\n".join(f"  - {e}" for e in errori))

    # (istante, slot, posto di prima da cui viene; None = nuovo)
    righe: list[tuple[float, Slot, int | None]] = [
        (slot.at, replace(slot), i) for i, slot in enumerate(slots) if i not in tolti
    ]
    aggiunti: list[float] = []
    for istante in sorted(nuovi):
        if any(abs(istante - riga[0]) < stesso for riga in righe):
            continue
        origine = slots[nuovi[istante]]
        # Un posto nuovo mostra quello che mostrava il posto da cui nasce: nel
        # riferimento li' c'era lo stesso tipo di contenuto. L'etichetta e il
        # movimento invece restano al posto originale, che e' ancora li'.
        righe.append((istante, Slot(at=istante, fit=origine.fit, hint=origine.hint), None))
        aggiunti.append(istante)
    righe.sort(key=lambda riga: riga[0])
    nuovi_slots = [riga[1] for riga in righe]
    nuovi_istanti = [riga[0] for riga in righe]

    # Un posto unito lascia la sua etichetta a quello che lo assorbe, se non ne
    # ha gia' una: `pausa` resta il nome di quel momento, anche se ora comincia prima.
    for i in sorted(tolti):
        dove = bisect_right(nuovi_istanti, slots[i].at) - 1
        erede = nuovi_slots[dove]
        if slots[i].label and not erede.label:
            erede.label = slots[i].label
        elif slots[i].label:
            note.append(f"l'etichetta '{slots[i].label}' del posto {i + 1} si perde: "
                        f"il posto in cui finisce si chiama gia' '{erede.label}'")
        if slots[i].hint and not erede.hint:
            erede.hint = slots[i].hint

    nuovo = replace(template, slots=nuovi_slots)
    nuove_durate = nuovo.gaps()
    durate_prima = {slot.at: gap for slot, gap in zip(slots, gaps, strict=True)}
    corti: list[str] = []
    for k, (slot, durata) in enumerate(zip(nuovi_slots, nuove_durate, strict=True)):
        if durata < 1 / template.fps - 1e-9:
            corti.append(f"il posto {k + 1} ({slot.at:.3f}s) durerebbe {durata * 1000:.0f} ms, "
                         f"meno di un fotogramma a {template.fps} fps: non si vedrebbe")
        if abs(durate_prima.get(slot.at, -1.0) - durata) > 1e-6:
            # Le stesse soglie di `extract`: in un lampo non conta se c'era un
            # video o una foto, e un movimento non fa in tempo a leggersi.
            if durata < HINT_MIN_SLOT:
                slot.hint = None
            if durata < MOTION_MIN_SLOT:
                slot.motion = None
    if corti:
        raise ConfigError("Non posso cambiare i posti:\n" + "\n".join(f"  - {c}" for c in corti))
    nuovo.validate()

    posizione = {riga[2]: k for k, riga in enumerate(righe) if riga[2] is not None}
    numeri = [
        posizione[i] if i in posizione else bisect_right(nuovi_istanti, slots[i].at) - 1
        for i in range(count)
    ]
    return Retimed(template=nuovo, added=aggiunti, removed=[slots[i].at for i in sorted(tolti)],
                   numbers=numeri, notes=note)


# --------------------------------------------------------------------------
# Riepiloghi
# --------------------------------------------------------------------------

def describe(template: Template, path: str) -> str:
    """L'elenco dei posti di `vedit slots`, con i comandi per cambiarli."""
    audio = template.audio
    gaps = template.gaps()
    battiti = template.beats_per_slot
    tempo = (f"{audio.bpm:g} BPM, un battito ogni {audio.period:.3f}s"
             if audio.bpm else "senza battito")
    righe = [
        f"{template.name}: {len(template.slots)} posti in {template.duration:.2f}s ({tempo})",
        "",
        "  #  entra a    dura  battiti  nel riferimento  etichetta",
    ]
    for i, (slot, durata) in enumerate(zip(template.slots, gaps, strict=True)):
        quanti = f"{battiti[i]:7.2f}" if audio.bpm else "      -"
        righe.append(f"{i + 1:3d}  {slot.at:6.2f}s  {durata:5.2f}s  {quanti}  "
                     f"{slot.hint or '-':<16} {slot.label}".rstrip())
    # Esempi che esistono in questo template: un "--merge 5" su tre posti
    # insegnerebbe un comando che fallisce.
    count = len(template.slots)
    istante = 4.45 if template.duration > 4.45 else round(template.duration / 2, 2)
    diviso, unito = min(4, count), min(5, count)
    esempi = [
        (f"--cut {istante:g}", "un taglio in piu', sul mezzo battito piu' vicino"),
        (f"--split {diviso}", f"il posto {diviso} diviso in due (--into 4: in quattro)"),
    ]
    if unito >= 2:
        esempi.append((f"--merge {unito}", f"via il taglio fra il posto {unito - 1} e il {unito}"))
    esempi.append(("--video", "i posti numerati sulla musica, da guardare"))
    righe += ["", "Per cambiare i tagli (i numeri sono quelli di questo elenco):"]
    righe += [f"  vedit slots {path} {opzione:<12} {cosa}" for opzione, cosa in esempi]
    return "\n".join(righe)


def _intervals(numbers: list[int], removed: set[int]) -> list[tuple[int, int, int]]:
    """I posti rinumerati, raggruppati: (primo, ultimo, spostamento), da 0."""
    gruppi: list[tuple[int, int, int]] = []
    for i, nuovo in enumerate(numbers):
        delta = nuovo - i
        if i in removed or delta == 0:
            continue
        if gruppi and gruppi[-1][1] == i - 1 and gruppi[-1][2] == delta:
            gruppi[-1] = (gruppi[-1][0], i, delta)
        else:
            gruppi.append((i, i, delta))
    return gruppi


def renumbering(before: Template, result: Retimed) -> list[str]:
    """Come sono cambiati i numeri dei posti, in parole: serve a chi ha gia' degli edit."""
    tolti = {i for i, slot in enumerate(before.slots) if slot.at in result.removed}
    righe = []
    for primo, ultimo, delta in _intervals(result.numbers, tolti):
        if primo == ultimo:
            righe.append(f"il posto {primo + 1} ora e' il {primo + delta + 1}")
        else:
            righe.append(f"i posti dal {primo + 1} al {ultimo + 1} ora sono "
                         f"dal {primo + delta + 1} al {ultimo + delta + 1}")
    return righe


def describe_change(before: Template, result: Retimed, path: str) -> str:
    """Cosa ha fatto un `vedit slots` che cambia i tagli, e come tornare indietro."""
    dopo = result.template
    if not result.changed:
        return "\n".join([*result.notes, "Nessun taglio cambiato: il template.yaml resta com'era."])

    righe = [f"{dopo.name}: {len(before.slots)} posti -> {len(dopo.slots)}"]
    righe += [f"  ({nota})" for nota in result.notes]
    istanti = [slot.at for slot in dopo.slots]
    for istante in result.added:
        righe.append(f"  + taglio a {istante:.3f}s: comincia il posto {istanti.index(istante) + 1}")
    for istante in result.removed:
        righe.append(f"  - tolto il taglio a {istante:.3f}s")
    righe += [f"  {riga}" for riga in renumbering(before, result)]

    indietro = []
    if result.added:
        indietro.append("--merge " + " ".join(str(istanti.index(t) + 1) for t in result.added))
    if result.removed:
        indietro.append("--cut " + " ".join(f"{t:g}" for t in result.removed) + " --grid off")
    righe += ["", f"Per tornare indietro: vedit slots {path} {' '.join(indietro)}"]
    return "\n".join(righe)


def edits_using(template: Template, folder: str | Path) -> list[Path]:
    """Gli edit in `folder` costruiti su questo template: quelli da ricontrollare."""
    trovati = []
    for path in sorted(Path(folder).glob(f"*/{EDIT_MANIFEST}")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        valore = data.get("template") if isinstance(data, dict) else None
        if not valore:
            continue
        cartella = (path.parent / str(valore)).resolve()
        if cartella.name == MANIFEST:
            cartella = cartella.parent
        if cartella == template.root.resolve():
            trovati.append(path)
    return trovati


# --------------------------------------------------------------------------
# I cartelli del video dei posti
# --------------------------------------------------------------------------

def card_color(index: int) -> tuple[int, int, int]:
    """
    Il colore del cartello di un posto.

    Le tinte avanzano della sezione aurea, cosi' due posti vicini non si somigliano
    mai, e la luce si alterna: anche chi distingue male i colori vede il cambio.
    """
    tinta = (index * 0.618034) % 1.0
    luce = 0.95 if index % 2 == 0 else 0.55
    r, g, b = colorsys.hsv_to_rgb(tinta, 0.8, luce)
    return round(r * 255), round(g * 255), round(b * 255)


def cards(template: Template, folder: str | Path, width: int = 360) -> list[Path]:
    """
    Un cartello per posto: un colore pieno, il numero grande, quando entra.

    Montati sul template danno il suo scheletro da guardare con la musica: si vede
    e si sente dove cade ogni taglio, e ogni posto si chiama per numero.
    """
    from PIL import Image

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    height = max(2, round(width * template.size[1] / template.size[0] / 2) * 2)
    # Le misure dal lato corto: in un formato orizzontale, o minuscolo, il
    # numero deve stare nel cartello anche in altezza.
    lato = min(width, height)
    numero = TextStyle(font_size=max(12, lato // 3), color="white",
                       stroke_color="black", stroke_width=max(1, lato // 60))
    nota = TextStyle(font_size=max(10, lato // 14), color="white",
                     stroke_color="black", stroke_width=max(1, lato // 120))

    files = []
    for i, slot in enumerate(template.slots):
        card = Image.new("RGBA", (width, height), (*card_color(i), 255))
        grande = Image.fromarray(render_text(str(i + 1), numero, width))
        piccolo = Image.fromarray(render_text(
            f"{slot.at:.2f}s" + (f"  {slot.label}" if slot.label else ""), nota, width))
        y = max(0, (height - grande.height - piccolo.height) // 2)
        for scritta in (grande, piccolo):
            # Pillow non accetta coordinate negative: una scritta piu' larga del
            # cartello si appoggia al bordo sinistro e quello che avanza si perde.
            card.alpha_composite(scritta.crop((0, 0, min(scritta.width, width),
                                               min(scritta.height, height - y))),
                                 (max(0, (width - scritta.width) // 2), y))
            y = min(height - 1, y + scritta.height)
        path = folder / f"{i + 1:03d}.png"
        card.convert("RGB").save(path)
        files.append(path)
    return files
