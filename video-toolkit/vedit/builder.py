"""
Costruzione della timeline MoviePy a partire da un Project.

NOTA IMPORTANTE SULLE VERSIONI
------------------------------
Questo codice usa l'API di MoviePy 2.x:
  - `from moviepy import ...`  (il namespace `moviepy.editor` NON esiste piu')
  - `.subclipped()` al posto di `.subclip()`
  - `.with_start()` / `.with_duration()` / `.with_position()` al posto di `.set_*()`
  - effetti come classi:  `.with_effects([vfx.CrossFadeIn(1.0)])`

La maggior parte dei tutorial online e' ancora ferma alla 1.x e non funziona qui.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
    vfx,
)

from . import transitions
from .models import AudioSpec, Overlay, Project, Segment
from .progress import RenderProgress, format_duration
from .timeline import clamp_overlap, plan, total_duration
from .transitions import TransitionContext, TransitionRequest

log = logging.getLogger("vedit")

# Tiene traccia dei clip aperti per poterli chiudere a fine render:
# MoviePy apre un processo ffmpeg per ogni file sorgente.
_OPEN_CLIPS: list = []


# --------------------------------------------------------------------------
# Helper geometrici
# --------------------------------------------------------------------------

def fit_clip(clip, size: tuple[int, int], mode: str):
    """
    Adatta un clip al canvas di output.

    contain : rientra tutto, con bande nere (letterbox)
    cover   : riempie il canvas, tagliando l'eccesso
    stretch : deforma per riempire (da evitare, ma a volte serve)
    """
    target_w, target_h = size
    src_w, src_h = clip.size

    if mode == "stretch":
        return clip.resized((target_w, target_h))

    scale_contain = min(target_w / src_w, target_h / src_h)
    scale_cover = max(target_w / src_w, target_h / src_h)
    scale = scale_contain if mode == "contain" else scale_cover

    clip = clip.resized(scale)

    if mode == "cover":
        # Ritaglio centrale alle dimensioni esatte del canvas
        clip = clip.with_effects([
            vfx.Crop(
                width=target_w,
                height=target_h,
                x_center=clip.w / 2,
                y_center=clip.h / 2,
            )
        ])

    return clip


def place_on_canvas(clip, size: tuple[int, int], background: tuple[int, int, int]):
    """
    Centra il clip su uno sfondo delle dimensioni esatte del canvas.
    Serve per avere segmenti tutti della stessa dimensione: senza questo,
    concatenare clip di risoluzioni diverse produce risultati imprevedibili.
    """
    if tuple(clip.size) == tuple(size):
        return clip

    bg = ColorClip(size=size, color=background, duration=clip.duration)
    composed = CompositeVideoClip([bg, clip.with_position("center")], size=size)
    composed = composed.with_duration(clip.duration)
    if clip.audio is not None:
        composed = composed.with_audio(clip.audio)
    return composed


# --------------------------------------------------------------------------
# Costruzione dei singoli segmenti
# --------------------------------------------------------------------------

def build_segment(seg: Segment, project: Project):
    """Trasforma un Segment del YAML in un clip MoviePy pronto per il montaggio."""
    size = project.output.size
    fit_mode = seg.fit or project.defaults.fit

    if seg.type == "video":
        path = project.resolve(seg.src)
        if not path.exists():
            raise FileNotFoundError(f"Sorgente video non trovata: {path}")
        clip = VideoFileClip(str(path))
        _OPEN_CLIPS.append(clip)

        if seg.start is not None or seg.end is not None:
            clip = clip.subclipped(seg.start or 0, seg.end)

        if seg.speed != 1.0:
            clip = clip.with_effects([vfx.MultiplySpeed(seg.speed)])

        if seg.mute:
            clip = clip.without_audio()

    elif seg.type == "image":
        path = project.resolve(seg.src)
        if not path.exists():
            raise FileNotFoundError(f"Immagine non trovata: {path}")
        duration = seg.duration or project.defaults.image_duration
        clip = ImageClip(str(path)).with_duration(duration)

    elif seg.type == "color":
        clip = ColorClip(size=size, color=seg.color, duration=seg.duration)

    else:  # pragma: no cover - gia' validato in models.py
        raise ValueError(f"Tipo di segmento sconosciuto: {seg.type}")

    clip = fit_clip(clip, size, fit_mode)
    clip = place_on_canvas(clip, size, project.output.background)
    return clip


# --------------------------------------------------------------------------
# Montaggio con transizioni
# --------------------------------------------------------------------------

def concat_with_transitions(clips: list, requests: list[TransitionRequest],
                            size: tuple[int, int]):
    """
    Concatena i clip applicando la transizione in ENTRATA di ciascuno.

    `requests[i]` descrive come entra il clip i-esimo (requests[0] viene
    ignorato: il primo clip non ha nulla che lo preceda).

    Il trucco chiave delle transizioni "con sovrapposizione": il clip parte a
    `fine del precedente - durata`, cosi' i due coesistono nel tempo. Senza
    quella sovrapposizione una dissolvenza incrociata dissolverebbe dal nero.
    Le transizioni senza sovrapposizione (stacco, dissolvenza al nero) lasciano
    i clip in fila e si consumano al loro interno.

    Chi applica l'effetto e' il registry in transitions.py: questa funzione non
    sa cosa sia un wipe, sa solo che qualcuno gli restituira' due clip modificati.
    """
    if not clips:
        raise ValueError("Nessun clip da concatenare")

    durations = [clip.duration for clip in clips]
    specs = [transitions.get(req.type) for req in requests]

    # La durata effettiva vale per tutti i tipi (anche quelli che non
    # sovrappongono: una dissolvenza al nero piu' lunga del clip non ha senso),
    # mentre la sovrapposizione la chiedono solo i tipi che ne hanno bisogno.
    effective = [0.0] * len(clips)
    overlaps = [0.0] * len(clips)
    for i in range(1, len(clips)):
        effective[i] = clamp_overlap(requests[i].duration, durations[i - 1], durations[i])
        overlaps[i] = effective[i] if specs[i].overlaps else 0.0

    # Il calcolo di inizio/fine sta in timeline.py, che non dipende da MoviePy:
    # cosi' `render --check` puo' mostrare le stesse cifre senza importare nulla.
    placements = plan(durations, overlaps)

    placed: list = []
    for i, (clip, place) in enumerate(zip(clips, placements)):
        current = clip.with_start(place.start)

        if i > 0 and effective[i] > 0:
            ctx = TransitionContext(
                duration=effective[i], direction=requests[i].direction, size=size
            )
            previous, current = specs[i].apply(placed[-1], current, ctx)
            placed[-1] = previous

        placed.append(current)

    montage = CompositeVideoClip(placed, size=size).with_duration(total_duration(placements))
    return montage


# --------------------------------------------------------------------------
# Overlay
# --------------------------------------------------------------------------

def build_overlay(ov: Overlay, project: Project, video_duration: float):
    """Costruisce un singolo overlay (immagine o testo) da sovrapporre al montaggio."""
    duration = ov.duration if ov.duration is not None else max(video_duration - ov.start, 0.1)

    if ov.type == "image":
        path = project.resolve(ov.src)
        if not path.exists():
            raise FileNotFoundError(f"Overlay non trovato: {path}")
        clip = ImageClip(str(path)).with_duration(duration)
        if ov.width or ov.height:
            if ov.width and ov.height:
                clip = clip.resized((ov.width, ov.height))
            elif ov.width:
                clip = clip.resized(width=ov.width)
            else:
                clip = clip.resized(height=ov.height)
    else:
        clip = TextClip(
            text=ov.text,
            font=ov.font,
            font_size=ov.font_size,
            color=ov.color,
            method="label",
        ).with_duration(duration)

    clip = clip.with_start(ov.start).with_position(ov.position)

    if ov.opacity < 1.0:
        clip = clip.with_opacity(ov.opacity)

    if ov.fade > 0:
        if clip.mask is None:
            clip = clip.with_mask()
        clip = clip.with_effects([vfx.CrossFadeIn(ov.fade), vfx.CrossFadeOut(ov.fade)])

    return clip


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------

def build_audio(spec: AudioSpec, project: Project, video_duration: float):
    """Prepara la traccia audio aggiuntiva, tagliata alla durata del video."""
    path = project.resolve(spec.src)
    if not path.exists():
        raise FileNotFoundError(f"Traccia audio non trovata: {path}")

    audio = AudioFileClip(str(path))
    _OPEN_CLIPS.append(audio)

    usable = min(audio.duration, video_duration - spec.start)
    if usable <= 0:
        raise ValueError("La traccia audio inizia dopo la fine del video")
    if audio.duration < video_duration - spec.start:
        log.warning(
            "La traccia audio (%.1fs) e' piu' corta del video (%.1fs): "
            "il finale restera' senza musica.",
            audio.duration, video_duration,
        )

    audio = audio.subclipped(0, usable)

    effects = []
    if spec.volume != 1.0:
        effects.append(afx.MultiplyVolume(spec.volume))
    if spec.fade_in > 0:
        effects.append(afx.AudioFadeIn(spec.fade_in))
    if spec.fade_out > 0:
        effects.append(afx.AudioFadeOut(spec.fade_out))
    if effects:
        audio = audio.with_effects(effects)

    if spec.start > 0:
        audio = audio.with_start(spec.start)

    return audio


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build(project: Project):
    """Costruisce il clip finale, pronto per write_videofile()."""
    size = project.output.size

    log.info("Costruzione di %d segmenti...", len(project.timeline))
    clips = []
    requests = []
    for i, seg in enumerate(project.timeline):
        clips.append(build_segment(seg, project))
        # La transizione dichiarata sul segmento vince sul default globale
        requests.append(seg.transition_request(project.defaults))
        log.info("  [%d] %s %s (%.2fs)", i, seg.type, seg.label or seg.src or "", clips[-1].duration)

    video = concat_with_transitions(clips, requests, size)
    log.info("Durata del montaggio: %.2fs", video.duration)

    if project.overlays:
        log.info("Applicazione di %d overlay...", len(project.overlays))
        layers = [video] + [build_overlay(ov, project, video.duration) for ov in project.overlays]
        video = CompositeVideoClip(layers, size=size).with_duration(video.duration)

    if project.audio is not None:
        from moviepy import CompositeAudioClip

        music = build_audio(project.audio, project, video.duration)
        if project.audio.replace or video.audio is None:
            video = video.with_audio(music)
        else:
            video = video.with_audio(CompositeAudioClip([video.audio, music]))

    return video


def _even(value: int) -> int:
    """Arrotonda al pari inferiore: libx264 rifiuta larghezze o altezze dispari."""
    return max(2, int(value) - int(value) % 2)


def discard_partial(target: Path) -> list[Path]:
    """
    Cancella il file interrotto e i temporanei di MoviePy.

    Un mp4 troncato a meta' export non e' riproducibile ma esiste: lasciarlo
    li' significa ritrovarselo domani e credere che il render fosse riuscito.
    MoviePy scrive anche l'audio in un file `...TEMP_MPY_wvf_snd.*` accanto
    alla destinazione, e non lo ripulisce se l'export non arriva in fondo.
    """
    removed = []
    candidates = [target, *target.parent.glob(f"{target.stem}TEMP_MPY_*")]
    for path in candidates:
        try:
            if path.exists():
                path.unlink()
                removed.append(path)
        except OSError:  # noqa: PERF203 - un file bloccato non deve mascherare l'interruzione
            log.warning("Non sono riuscito a rimuovere %s", path)
    return removed


def render(project: Project, dry_run: bool = False, preview: bool = False) -> Path | None:
    """Costruisce ed esporta il video. Restituisce il percorso del file prodotto."""
    out = project.output

    if preview:
        # Anteprima veloce: meta' risoluzione, encoding rapidissimo, qualita' bassa.
        # Serve per iterare sul montaggio senza aspettare l'export finale.
        out.size = (_even(out.size[0] // 2), _even(out.size[1] // 2))
        out.fps = min(out.fps, 24)
        out.preset = "ultrafast"
        out.crf = 30
        out.path = out.path.with_name(out.path.stem + "_preview" + out.path.suffix)

    video = build(project)

    if dry_run:
        log.info("dry-run: nessun file scritto. Durata finale %.2fs", video.duration)
        close_all()
        return None

    target = project.resolve(out.path)
    target.parent.mkdir(parents=True, exist_ok=True)

    log.info("Export verso %s (%dx%d @ %dfps, crf=%d, preset=%s)",
             target, out.size[0], out.size[1], out.fps, out.crf, out.preset)

    ffmpeg_params = ["-crf", str(out.crf), "-pix_fmt", "yuv420p"]

    # logger=progress al posto del tqdm di MoviePy: stessa informazione,
    # una riga sola, con la stima del tempo residuo (vedi progress.py).
    progress = RenderProgress()
    started = time.monotonic()

    try:
        video.write_videofile(
            str(target),
            fps=out.fps,
            codec=out.codec,
            audio_codec=out.audio_codec,
            preset=out.preset,
            threads=out.threads,
            ffmpeg_params=ffmpeg_params,
            logger=progress,
        )
    except KeyboardInterrupt:
        progress.close_line()
        close_all()   # prima i processi ffmpeg, poi i file: altrimenti restano aperti
        for path in discard_partial(target):
            log.warning("Interrotto: rimosso il file parziale %s", path.name)
        raise
    finally:
        progress.close_line()

    log.info("Export completato in %s", format_duration(time.monotonic() - started))
    close_all()
    return target


def close_all() -> None:
    """Chiude i file sorgente aperti (evita processi ffmpeg zombie)."""
    while _OPEN_CLIPS:
        clip = _OPEN_CLIPS.pop()
        try:
            clip.close()
        except Exception:  # noqa: BLE001 - la chiusura non deve mai far fallire il render
            pass
