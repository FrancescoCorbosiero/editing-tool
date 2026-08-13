"""
Wrapper sottili attorno a ffmpeg/ffprobe.

Quando serve solo tagliare, concatenare o rimpicciolire, chiamare ffmpeg
direttamente e' 10-50x piu' veloce di MoviePy, perche' non passa i frame
attraverso Python/numpy. MoviePy serve quando si deve COMPORRE.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    """ffmpeg o ffprobe non disponibile, oppure uscito con errore."""


def ensure_ffmpeg() -> None:
    """Verifica che ffmpeg e ffprobe siano nel PATH, altrimenti spiega come installarli."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise FFmpegError(
            f"{', '.join(missing)} non trovato/i nel PATH.\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: winget install Gyan.FFmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg"
        )


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"Comando fallito: {' '.join(cmd)}\n{result.stderr[-2000:]}")
    return result


def probe(path: str | Path) -> dict:
    """
    Restituisce i metadati utili di un file multimediale:
    durata, risoluzione, fps, codec, presenza di audio.
    """
    ensure_ffmpeg()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    result = _run([
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ])
    data = json.loads(result.stdout)

    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    fps = None
    if video_stream and video_stream.get("r_frame_rate"):
        num, _, den = video_stream["r_frame_rate"].partition("/")
        try:
            fps = round(int(num) / int(den or 1), 3)
        except (ValueError, ZeroDivisionError):
            fps = None

    return {
        "path": str(path),
        "duration": float(data.get("format", {}).get("duration", 0.0)),
        "size_bytes": int(data.get("format", {}).get("size", 0)),
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "fps": fps,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "has_audio": audio_stream is not None,
    }


def fast_cut(src: str | Path, dst: str | Path, start: float, end: float) -> Path:
    """
    Taglio senza ricompressione: istantaneo e senza perdita di qualita',
    ma il punto di taglio si allinea al keyframe piu' vicino (puo' scostarsi
    di qualche decimo di secondo). Per il fotogramma esatto usa accurate_cut().
    """
    ensure_ffmpeg()
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-ss", str(start), "-to", str(end),
        "-i", str(src),
        "-c", "copy",
        str(dst),
    ])
    return dst


def accurate_cut(src: str | Path, dst: str | Path, start: float, end: float, crf: int = 18) -> Path:
    """Taglio al fotogramma esatto, con ricompressione."""
    ensure_ffmpeg()
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-ss", str(start), "-to", str(end),
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-c:a", "aac",
        str(dst),
    ])
    return dst


def make_proxy(src: str | Path, dst: str | Path, height: int = 480) -> Path:
    """
    Crea una versione leggera del sorgente, da usare durante il montaggio.
    Si lavora sul proxy (veloce) e si rifa' l'export finale sull'originale.
    """
    ensure_ffmpeg()
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k",
        str(dst),
    ])
    return dst


def extract_frame(src: str | Path, dst: str | Path, at: float) -> Path:
    """Estrae un singolo fotogramma come immagine: utile per individuare i punti di taglio."""
    ensure_ffmpeg()
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-ss", str(at), "-i", str(src),
        "-frames:v", "1", "-q:v", "2",
        str(dst),
    ])
    return dst
