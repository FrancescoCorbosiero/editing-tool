# assets/

Metti qui i tuoi file sorgente: video, immagini, audio, font.

Il contenuto di questa cartella è escluso da git (vedi `.gitignore`): i media sono
pesanti e non vanno versionati. Se ti serve materiale di prova, puoi generarlo con
ffmpeg senza scaricare nulla:

```bash
# video di test 60s con pattern e tono audio
ffmpeg -f lavfi -i testsrc=size=1280x720:rate=30:duration=60 \
       -f lavfi -i sine=frequency=440:duration=60 \
       -c:v libx264 -pix_fmt yuv420p -c:a aac assets/input.mp4

# immagine a tinta unita, formato verticale
ffmpeg -f lavfi -i color=c=orange:size=1080x1350 -frames:v 1 assets/foto1.jpg
```

Il progetto demo in `projects/demo/timeline.yaml` si aspetta `input.mp4`,
`foto1.jpg` e `logo.png` in questa cartella.
