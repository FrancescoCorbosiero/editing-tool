# Contesto per Claude Code

Leggi questo file prima di modificare il repo.

## Cos'è questo progetto

`vedit` monta video in modo dichiarativo: un file YAML descrive una timeline, il
codice la traduce in clip MoviePy e la esporta. L'utente **non conosce i software di
editing** e sta imparando il dominio attraverso questo codice: la leggibilità e i
commenti esplicativi contano quanto la correttezza.

## Vincolo critico: MoviePy 2.x

Il repo usa MoviePy **2.x**, la cui API è incompatibile con la 1.x. Il tuo training
contiene moltissimo codice 1.x che qui **non funziona**. Differenze da rispettare:

| MoviePy 1.x (NON usare) | MoviePy 2.x (usare) |
|---|---|
| `from moviepy.editor import *` | `from moviepy import *` |
| `clip.subclip(a, b)` | `clip.subclipped(a, b)` |
| `clip.set_position(...)` | `clip.with_position(...)` |
| `clip.set_duration(...)` | `clip.with_duration(...)` |
| `clip.set_start(...)` | `clip.with_start(...)` |
| `clip.resize(...)` | `clip.resized(...)` |
| `clip.crop(...)` | `clip.with_effects([vfx.Crop(...)])` |
| `clip.fx(vfx.fadein, 1)` | `clip.with_effects([vfx.FadeIn(1)])` |
| `clip.crossfadein(1)` | `clip.with_effects([vfx.CrossFadeIn(1)])` |

Gli effetti nella 2.x sono **classi**, non funzioni. Se non sei sicuro del nome di un
effetto, verificalo con `python -c "from moviepy import vfx; print(dir(vfx))"` invece
di indovinare.

## Architettura e confini

Il confine che conta è fra i moduli che importano MoviePy e quelli che non lo fanno.
Tutto ciò che si può calcolare senza MoviePy sta dalla parte leggera, così resta
testabile in millisecondi e utilizzabile dai comandi che non renderizzano.

Senza MoviePy:

- **`vedit/models.py`** — dataclass e parsing YAML. **Non deve importare MoviePy.**
  Questo permette di testare la validazione in millisecondi. Non violare questo confine.
- **`vedit/timeline.py`** — matematica delle posizioni (inizio/fine/sovrapposizione).
  Usata sia dal builder sia da `--check`: una sola implementazione, nessuna divergenza.
- **`vedit/transitions.py`** — registry `nome → funzione` delle transizioni. Le sue
  funzioni **usano** MoviePy ma lo importano al loro interno, perché `models.py`
  importa questo modulo per validare i nomi. Non spostare quegli import in cima.
- **`vedit/motion.py`** — registry dei movimenti sulle immagini (Ken Burns), stessa
  regola sugli import di `transitions.py`.
- **`vedit/subtitles.py`** — parsing dei `.srt`. Solo manipolazione di testo.
- **`vedit/proxies.py`** — copie leggere dei sorgenti, con cache basata sull'impronta
  del file. Chiama ffmpeg, non MoviePy.
- **`vedit/fonts.py`** — ricerca dei font e a capo del testo (usa Pillow, non MoviePy).
- **`vedit/report.py`** — il riepilogo di `render --check`. Legge i metadati con ffprobe.
- **`vedit/ffmpeg_tools.py`** — subprocess verso ffmpeg/ffprobe. Nessun MoviePy.

Con MoviePy:

- **`vedit/builder.py`** — traduce `Project` in clip. È qui che vive il montaggio.
- **`vedit/progress.py`** — barra di avanzamento (usa proglog, che arriva con MoviePy).

- **`vedit/cli.py`** — argparse. Importa MoviePy **pigramente** dentro le funzioni
  comando, perché l'import è lento e `probe`/`init`/`--check` non ne hanno bisogno.

Ogni nuova funzionalità dichiarativa richiede tre modifiche coordinate:
1. il campo in `models.py` con la sua validazione
2. la traduzione in `builder.py`
3. la riga nella tabella dello schema in `README.md`

Se introduce un termine di montaggio nuovo, aggiungilo anche a `docs/GLOSSARIO.md`.

## Convenzioni

- Commenti e messaggi utente in **italiano**; nomi di funzioni, variabili e classi in
  **inglese**. Il codice esistente segue già questa regola.
- I commenti spiegano il **perché**, non il cosa. Il pubblico è qualcuno che sta
  imparando il dominio: quando una scelta è controintuitiva (es. la sovrapposizione
  necessaria al crossfade), spiegala.
- Type hint ovunque. `from __future__ import annotations` in cima ai moduli.
- Errori attesi → eccezioni tipizzate (`ConfigError`, `FFmpegError`) intercettate in
  `cli.py` e mostrate come messaggi leggibili, mai come traceback.
- Nessuna dipendenza nuova senza motivo forte. Lo stack è: moviepy, PyYAML, numpy,
  Pillow. FFmpeg è un binario di sistema, non un pacchetto pip.

## Test e lint

```bash
pytest -q
ruff check .
```

`ruff check` deve passare (configurazione in `pyproject.toml`). `ruff format` è
configurato ma **non** va applicato in blocco al codice esistente: i commenti
allineati in colonna sono voluti e il formatter li schiaccerebbe.

Il confine "niente MoviePy nei moduli leggeri" è verificato da
`tests/test_confini.py`: se aggiungi un modulo dalla parte leggera, mettilo in
quella lista.

I test **non devono richiedere file video**: usa segmenti `type: color`, generati in
memoria. Se una funzionalità ha bisogno di un sorgente reale, genera un file
sintetico con ffmpeg in una fixture temporanea (`testsrc` di lavfi), non committare
media nel repo.

Prima di dichiarare completo un lavoro:
1. `pytest -q` verde
2. `python -m vedit render projects/demo/timeline.yaml --dry-run` senza errori
3. per modifiche al rendering, un render `--preview` reale e la verifica del risultato

## Verifica del risultato di un render

Non fidarti del fatto che il comando esca con codice 0: un video può essere prodotto
e essere sbagliato. Campiona i frame e controlla i valori:

```python
from moviepy import VideoFileClip
v = VideoFileClip("output/demo_preview.mp4")
print(v.duration, v.size, v.fps)
for t in [0, 2, 5]:
    print(t, v.get_frame(t).mean(axis=(0, 1)).round(1))   # RGB medio
v.close()
```

Durante un crossfade il colore medio deve variare **gradualmente** fra i due
segmenti; se salta di colpo, la sovrapposizione non sta funzionando.

## Trappole già incontrate

- `CrossFadeIn` agisce sulla maschera alpha: se il clip non ha maschera l'effetto non
  ha su cosa agire. Il codice chiama `.with_mask()` come guardia — non rimuoverla.
- I clip vanno **chiusi**: ogni `VideoFileClip` apre un processo ffmpeg. Registra le
  sorgenti in `_OPEN_CLIPS` e chiudi con `close_all()`, anche in caso di eccezione.
- I percorsi nel YAML sono relativi alla cartella **del YAML**, non alla working
  directory. Usa sempre `project.resolve(path)`.
- Con `pix_fmt` diverso da `yuv420p` il video non si apre su molti player. È già
  forzato negli `ffmpeg_params`.
- `TextClip` vuole il **percorso** di un file di font, non un nome. `fonts.py` risolve
  percorsi, nomi installati e un default di sistema: passa sempre da lì.
- Il `method="caption"` di MoviePy 2.1.x spezza **dentro** le parole quando il testo
  occupa più di due righe (mescola indici assoluti e relativi in `__break_text`).
  L'a capo lo calcola `fonts.wrap_text`: non tornare a `caption`.
- Larghezze/altezze dispari fanno fallire libx264. Se aggiungi ridimensionamenti
  dinamici (zoom, Ken Burns), arrotonda a numeri pari.
