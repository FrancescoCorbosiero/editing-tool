"""
ESEMPIO 1 - Il taglio: prendere due pezzi di un video e attaccarli.

Concetti:
  - subclipped(inizio, fine) taglia nel tempo del SORGENTE, non della timeline
  - concatenate_videoclips mette in fila i clip, senza transizione

Lancia con:  python examples/01_taglio_e_concatenazione.py
"""

from moviepy import VideoFileClip, concatenate_videoclips

SORGENTE = "assets/input.mp4"

video = VideoFileClip(SORGENTE)
print(f"Sorgente: {video.duration:.1f}s, {video.w}x{video.h}, {video.fps} fps")

primo = video.subclipped(5, 12)
secondo = video.subclipped(40, 47)

montaggio = concatenate_videoclips([primo, secondo])
montaggio.write_videofile("output/es01.mp4", fps=30, codec="libx264", audio_codec="aac")

video.close()
