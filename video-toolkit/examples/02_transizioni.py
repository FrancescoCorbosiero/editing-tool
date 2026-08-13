"""
ESEMPIO 2 - La transizione: far dissolvere un clip nell'altro.

Il punto centrale, quello che confonde tutti all'inizio:
un crossfade richiede che i due clip si SOVRAPPONGANO nel tempo.
Se li metti semplicemente in fila e aggiungi una dissolvenza,
il secondo clip dissolve dal NERO, non dal primo clip.

Due modi per ottenere la sovrapposizione:
  A) concatenate_videoclips(..., padding=-T, method="compose")
  B) posizionare i clip a mano con with_start()  <- piu' controllo, vedi builder.py
"""

from moviepy import VideoFileClip, concatenate_videoclips, vfx

T = 1.0  # durata della transizione

video = VideoFileClip("assets/input.mp4")
clips = [video.subclipped(5, 12), video.subclipped(20, 26), video.subclipped(40, 47)]

# Crossfade in entrata su tutti tranne il primo
clips = [c if i == 0 else c.with_effects([vfx.CrossFadeIn(T)]) for i, c in enumerate(clips)]

# padding negativo = i clip si sovrappongono di T secondi
montaggio = concatenate_videoclips(clips, padding=-T, method="compose")
montaggio.write_videofile("output/es02.mp4", fps=30, codec="libx264", audio_codec="aac")

video.close()
