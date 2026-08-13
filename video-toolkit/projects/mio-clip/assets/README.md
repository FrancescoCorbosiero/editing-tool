# I file del clip

Qui dentro vanno **i tuoi** file: video, foto, musica, font. La cartella è esclusa
da git (i media sono pesanti e non si versionano), quindi puoi metterci quello che
vuoi senza sporcare il repo.

`timeline.yaml` in questo momento si aspetta questi nomi:

| file | cos'è | usato da |
|---|---|---|
| `foto1.jpg` | un'immagine | il segmento `foto` |
| `ripresa.mp4` | un video | il segmento `ripresa` |
| `musica.mp3` | una traccia audio | la sezione `audio` (per ora commentata) |

**Per usare la tua roba: sostituisci il file tenendo lo stesso nome.** Non serve
toccare il YAML. Se invece preferisci i tuoi nomi, cambia il campo `src` del
segmento — ricordandoti che il percorso parte da questa cartella di progetto.

## Segnaposto

Finché non hai il materiale vero, servono dei file finti per poter renderizzare.
Questi comandi li rigenerano (lanciali da `video-toolkit/`):

```bash
cd projects/mio-clip

# video di prova: 30s con pattern e un tono audio
ffmpeg -f lavfi -i testsrc=size=1280x720:rate=30:duration=30 \
       -f lavfi -i sine=frequency=440:duration=30 \
       -c:v libx264 -pix_fmt yuv420p -c:a aac assets/ripresa.mp4

# immagine di prova con un motivo riconoscibile
ffmpeg -f lavfi -i testsrc=size=1600x1200 -frames:v 1 assets/foto1.jpg
```

Usa immagini **con un motivo**, non a tinta unita: su un rettangolo arancione
uniforme un movimento Ken Burns c'è ma non si vede, e sembra che non funzioni.
