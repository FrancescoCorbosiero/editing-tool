"""
ESEMPIO 3 - Immagini: a schermo pieno nella timeline, o sovrapposte al video.

Concetti:
  - un'immagine non ha durata propria: gliela dai tu con with_duration()
  - with_start() decide QUANDO appare nella timeline
  - with_position() decide DOVE
  - CompositeVideoClip impila i livelli: il primo e' il fondo, gli altri sopra
"""

from moviepy import CompositeVideoClip, ImageClip, VideoFileClip, vfx

W, H = 1920, 1080

video = VideoFileClip("assets/input.mp4").subclipped(0, 10).resized((W, H))

# Immagine sovrapposta in alto a sinistra, dal secondo 2 per 4 secondi
logo = (
    ImageClip("assets/logo.png")
    .with_duration(4)
    .with_start(2)
    .resized(width=220)
    .with_position((60, 60))
    .with_effects([vfx.CrossFadeIn(0.5), vfx.CrossFadeOut(0.5)])
)

finale = CompositeVideoClip([video, logo], size=(W, H))
finale.write_videofile("output/es03.mp4", fps=30, codec="libx264", audio_codec="aac")

video.close()
