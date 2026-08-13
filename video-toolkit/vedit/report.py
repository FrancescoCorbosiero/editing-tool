"""
Riepilogo di un progetto senza renderizzarlo (`render --check`).

Risponde a tre domande che ci si pone continuamente mentre si monta:
  - quanto dura il montaggio, e dove cade ogni segmento?
  - i tagli che ho scritto stanno dentro la durata dei file sorgente?
  - le sorgenti sono coerenti fra loro (stessa risoluzione, stesso fps)?

Non importa MoviePy: legge i metadati con ffprobe, che costa millisecondi
contro i secondi di un import di MoviePy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import transitions
from .ffmpeg_tools import FFmpegError, probe
from .models import Project, Segment
from .timeline import Placement, clamp_overlap, plan
from .transitions import TransitionRequest


@dataclass
class SegmentRow:
    """Una riga del riepilogo: un segmento con la sua posizione calcolata."""

    index: int
    kind: str
    label: str
    detail: str
    placement: Placement
    transition: TransitionRequest | None = None   # None sul primo segmento

    def transition_label(self) -> str:
        """Come si legge la transizione in entrata nel riepilogo."""
        if self.transition is None:
            return "-"
        if self.transition.type == "cut" or self.transition.duration <= 0:
            return "cut"
        spec = transitions.get(self.transition.type)
        text = f"{self.transition.type} {self.transition.duration:.2f}s"
        if spec.directional:
            text += f" da {self.transition.direction}"
        return text


@dataclass
class Report:
    project_path: Path
    output_path: Path
    size: tuple[int, int]
    fps: int
    rows: list[SegmentRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    subtitle_count: int = 0

    @property
    def duration(self) -> float:
        return self.rows[-1].placement.end if self.rows else 0.0


def format_time(seconds: float) -> str:
    """Secondi -> `m:ss.cc`, il formato con cui si ragiona su una timeline."""
    if seconds < 0:
        seconds = 0.0
    minutes, rest = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours}:{minutes:02d}:{rest:05.2f}"
    return f"{minutes}:{rest:05.2f}"


def _probe_cached(path: Path, cache: dict[Path, dict | None]) -> dict | None:
    """ffprobe su un file, una volta sola anche se compare in piu' segmenti."""
    if path not in cache:
        try:
            cache[path] = probe(path)
        except (FFmpegError, FileNotFoundError):
            cache[path] = None
    return cache[path]


def _segment_detail(seg: Segment, info: dict | None) -> str:
    """Colonna di destra: sorgente e punti di taglio, se ci sono."""
    if seg.type == "color":
        return f"colore rgb{tuple(seg.color)}"

    parts = [Path(seg.src).name] if seg.src else []
    if seg.motion:
        parts.append(f"{seg.motion} {seg.amount * 100:g}%")
    if seg.type == "video":
        if seg.start is not None or seg.end is not None:
            end = f"{seg.end:g}" if seg.end is not None else "fine"
            parts.append(f"[{seg.start or 0:g} -> {end}]")
        if seg.speed != 1.0:
            parts.append(f"x{seg.speed:g}")
        if seg.mute:
            parts.append("muto")
    if info and info.get("width"):
        parts.append(f"{info['width']}x{info['height']}")
    return "  ".join(parts)


def analyze(project: Project, project_path: Path | str = "") -> Report:
    """Costruisce il riepilogo: durate, posizioni, incoerenze fra le sorgenti."""
    report = Report(
        project_path=Path(project_path),
        output_path=project.resolve(project.output.path),
        size=project.output.size,
        fps=project.output.fps,
    )

    cache: dict[Path, dict | None] = {}
    kinds: dict[Path, str] = {}   # video o image: un jpeg non ha un vero frame rate
    durations: list[float] = []
    requests: list[TransitionRequest] = []
    infos: list[dict | None] = []

    for i, seg in enumerate(project.timeline):
        info = None
        if seg.src is not None:
            source = project.resolve(seg.src)
            kinds[source] = seg.type
            info = _probe_cached(source, cache)
        infos.append(info)

        source_duration = info["duration"] if info else None
        duration = seg.timeline_duration(project.defaults, source_duration)
        if duration is None:
            # Succede solo se ffprobe non e' riuscito a leggere il file:
            # meglio una durata finta che un riepilogo interrotto a meta'.
            report.warnings.append(
                f"timeline[{i}]: durata non determinabile (ffprobe non ha letto il file)"
            )
            duration = 0.0
        durations.append(duration)
        requests.append(seg.transition_request(project.defaults))

        _check_cuts(report, i, seg, info)

        if seg.motion and seg.fit:
            report.warnings.append(
                f"timeline[{i}]: fit '{seg.fit}' viene ignorato perche' c'e' motion "
                f"'{seg.motion}' (il movimento riempie sempre il canvas, altrimenti "
                "muoverebbe anche le bande nere)"
            )

    # Stesso calcolo del builder: la durata effettiva vale per tutti i tipi,
    # la sovrapposizione solo per quelli che la usano (vedi transitions.py).
    effective = [0.0] * len(durations)
    overlaps = [0.0] * len(durations)
    for i in range(1, len(durations)):
        effective[i] = clamp_overlap(requests[i].duration, durations[i - 1], durations[i])
        overlaps[i] = effective[i] if transitions.get(requests[i].type).overlaps else 0.0

    placements = plan(durations, overlaps)

    rows = zip(project.timeline, placements, infos, strict=True)
    for i, (seg, place, info) in enumerate(rows):
        applied = None if i == 0 else TransitionRequest(
            duration=effective[i], type=requests[i].type, direction=requests[i].direction
        )
        report.rows.append(SegmentRow(
            index=i,
            kind=seg.type,
            label=seg.label,
            detail=_segment_detail(seg, info),
            placement=place,
            transition=applied,
        ))
        if i > 0 and effective[i] < requests[i].duration - 1e-6:
            report.warnings.append(
                f"timeline[{i}]: transizione ridotta da {requests[i].duration:g}s a "
                f"{effective[i]:.2f}s (non puo' superare meta' dei clip coinvolti)"
            )

    _check_sources_consistency(report, project, cache, kinds)
    _check_audio(report, project, cache)
    _check_subtitles(report, project)
    return report


def _check_subtitles(report: Report, project: Project) -> None:
    """Legge l'srt e segnala i problemi che si vedrebbero solo a render finito."""
    if project.subtitles is None:
        return

    from .subtitles import SubtitleError, load_srt, overlaps

    spec = project.subtitles
    try:
        cues = load_srt(project.resolve(spec.src))
    except SubtitleError as exc:
        report.warnings.append(f"sottotitoli: {exc}")
        return

    if not cues:
        report.warnings.append("sottotitoli: il file non contiene nessuna battuta")
        return

    report.subtitle_count = len(cues)

    fuori = [c for c in cues if c.start + spec.offset >= report.duration]
    if fuori:
        report.warnings.append(
            f"sottotitoli: {len(fuori)} battute iniziano dopo la fine del montaggio "
            f"({report.duration:.2f}s) e non si vedranno"
        )

    sovrapposte = overlaps(cues)
    if sovrapposte:
        primo = sovrapposte[0][0]
        report.warnings.append(
            f"sottotitoli: {len(sovrapposte)} coppie di battute si sovrappongono nel "
            f"tempo (la prima a {primo.start:.2f}s): verranno disegnate una sull'altra"
        )

    lampo = [c for c in cues if c.duration < 0.5]
    if lampo:
        report.warnings.append(
            f"sottotitoli: {len(lampo)} battute durano meno di mezzo secondo, "
            "il tempo minimo per leggerle"
        )


def _check_cuts(report: Report, index: int, seg: Segment, info: dict | None) -> None:
    """Verifica che i punti di taglio stiano dentro la durata del sorgente."""
    if seg.type != "video" or not info:
        return
    source_duration = info["duration"]
    if seg.start is not None and seg.start >= source_duration:
        report.warnings.append(
            f"timeline[{index}]: start={seg.start:g}s ma il file dura "
            f"{source_duration:.2f}s: il segmento risultera' vuoto"
        )
    elif seg.end is not None and seg.end > source_duration + 0.05:
        report.warnings.append(
            f"timeline[{index}]: end={seg.end:g}s oltre la fine del file "
            f"({source_duration:.2f}s): verra' troncato"
        )


def _check_sources_consistency(
    report: Report, project: Project, cache: dict, kinds: dict[Path, str]
) -> None:
    """
    Avvisa se le sorgenti non parlano la stessa lingua.

    Mescolare risoluzioni o frame rate diversi non e' un errore - il canvas di
    output uniforma tutto - ma e' la causa piu' comune di risultati "strani":
    un 25 fps dentro un montaggio a 30 fps viene ricampionato e i movimenti
    possono risultare meno fluidi.

    Il confronto riguarda solo i VIDEO. Le foto hanno per definizione
    risoluzioni e proporzioni diverse fra loro, e il frame rate che ffprobe
    riporta per un jpeg (25) e' un valore di comodo, non un dato reale:
    segnalarli produrrebbe solo avvisi da ignorare.
    """
    resolutions: dict[tuple[int, int], list[str]] = {}
    rates: dict[float, list[str]] = {}

    for path, info in cache.items():
        if not info or not info.get("width"):
            continue
        name = path.name

        if kinds.get(path) == "video":
            resolutions.setdefault((info["width"], info["height"]), []).append(name)
            if info.get("fps"):
                rates.setdefault(round(float(info["fps"]), 2), []).append(name)

        if info["width"] < project.output.size[0] or info["height"] < project.output.size[1]:
            report.warnings.append(
                f"{name}: {info['width']}x{info['height']} e' piu' piccolo del canvas "
                f"{project.output.size[0]}x{project.output.size[1]}: verra' ingrandito "
                "e apparira' meno nitido"
            )

    if len(resolutions) > 1:
        detail = " · ".join(
            f"{w}x{h}: {', '.join(sorted(set(names)))}" for (w, h), names in resolutions.items()
        )
        report.warnings.append(f"risoluzioni discordanti fra le sorgenti ({detail})")

    if len(rates) > 1:
        detail = " · ".join(
            f"{fps:g} fps: {', '.join(sorted(set(names)))}" for fps, names in rates.items()
        )
        report.warnings.append(f"frame rate discordanti fra le sorgenti ({detail})")

    for fps, names in rates.items():
        if abs(fps - project.output.fps) > 0.01:
            report.warnings.append(
                f"{', '.join(sorted(set(names)))}: {fps:g} fps contro i "
                f"{project.output.fps} fps dell'output: verra' ricampionato"
            )


def _check_audio(report: Report, project: Project, cache: dict) -> None:
    """Avvisa se la traccia audio non copre tutto il montaggio."""
    if project.audio is None:
        return
    info = _probe_cached(project.resolve(project.audio.src), cache)
    if not info:
        return
    coperto = info["duration"] + project.audio.start
    if coperto < report.duration - 0.05:
        report.warnings.append(
            f"la traccia audio copre {coperto:.2f}s dei {report.duration:.2f}s del "
            "montaggio: il finale restera' in silenzio"
        )


def format_report(report: Report) -> str:
    """Rende il riepilogo come testo pronto per il terminale."""
    lines: list[str] = []
    if report.project_path.name:
        lines.append(f"Progetto : {report.project_path}")
    lines.append(
        f"Canvas   : {report.size[0]}x{report.size[1]} @ {report.fps} fps"
    )
    lines.append(f"Output   : {report.output_path}")
    lines.append("")
    label_width = max((len(row.label) for row in report.rows), default=0)
    trans_width = max((len(row.transition_label()) for row in report.rows), default=0)
    lines.append(
        f"  #  inizio     fine    durata  {'transizione':<{trans_width}}  tipo   segmento"
    )

    for row in report.rows:
        p = row.placement
        lines.append(
            f"{row.index:3d}  {format_time(p.start):>7}  {format_time(p.end):>7}"
            f"  {p.duration:7.2f}s  {row.transition_label():<{trans_width}}  {row.kind:<5}  "
            f"{row.label:<{label_width}}  {row.detail}".rstrip()
        )

    lines.append("")
    lines.append(
        f"Durata totale: {format_time(report.duration)}  ({report.duration:.2f}s, "
        f"{int(report.duration * report.fps)} fotogrammi)"
    )
    if report.subtitle_count:
        lines.append(f"Sottotitoli  : {report.subtitle_count} battute")

    if report.warnings:
        lines.append("")
        lines.append(f"Avvisi ({len(report.warnings)}):")
        lines.extend(f"  - {w}" for w in report.warnings)
    else:
        lines.append("")
        lines.append("Nessun avviso.")

    return "\n".join(lines)
