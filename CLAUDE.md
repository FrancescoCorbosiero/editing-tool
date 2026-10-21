# Contesto per Claude Code

Leggi questo file prima di modificare il repo.

## Cos'è questo progetto

`vedit` fa una cosa sola: **video verticali a tempo di musica**, dove i cambi di
immagine cadono sul battito e sopra compaiono dei testi. Il modello è quello dei
video "usa questo suono" dei social: un montaggio che funziona su una canzone, rifatto
con altri media.

Due oggetti, e la differenza fra loro è tutto il progetto:

- il **template** (`templates/<nome>/`) è la parte che **non cambia**: la traccia
  audio, gli istanti dei tagli, lo stile (media interi o a tutto schermo, dissolvenze),
  lo stile dei testi. Si estrae una volta da un video di riferimento (`vedit extract`);
- l'**edit** (`edits/<nome>/edit.yaml`) è la parte che **cambia a ogni video**: quale
  media va in quale posto e quali testi compaiono, dove e quando.

L'utente **non conosce i software di montaggio** e vuole che sia l'assistente a fare
la maggior parte del lavoro: carica un video, tu lo templetizzi; manda media e testi,
tu monti il video e glielo consegni. Le due procedure sono le skill del progetto:

- **`.claude/skills/templetizza/`** — da un video caricato a un template in `templates/`;
- **`.claude/skills/monta/`** — da media e testi a un video finito, con un edit in `edits/`.

Seguile quando l'utente chiede quelle cose, anche se non le nomina.

Il vincolo che tiene onesto tutto il resto: **template ed edit generano un
`timeline.yaml`, non sono un secondo motore di montaggio**. Quello che producono deve
poter essere scritto a mano, salvato con `--to-yaml` e renderizzato da `vedit render`.
Se una funzionalità non è esprimibile come progetto, il problema è la funzionalità.

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
di indovinare. Attenzione: la 2.2.1 riporta ancora `__version__ = "2.1.2"`; la versione
vera la dice `pip show moviepy`.

## Architettura e confini

Il confine che conta è fra i moduli che importano MoviePy e quelli che non lo fanno.
Tutto ciò che si può calcolare senza MoviePy sta dalla parte leggera, così resta
testabile in millisecondi e utilizzabile dai comandi che non renderizzano.

Senza MoviePy:

- **`vedit/models.py`** — dataclass e parsing del `timeline.yaml`, e `place()` (dove va
  un overlay). **Non deve importare MoviePy.** Non violare questo confine.
- **`vedit/timeline.py`** — matematica delle posizioni (inizio/fine/sovrapposizione).
  Usata sia dal builder sia da `--check`: una sola implementazione, nessuna divergenza.
- **`vedit/transitions.py`** — registry `nome → funzione` delle transizioni. Le sue
  funzioni **usano** MoviePy ma lo importano al loro interno, perché `models.py`
  importa questo modulo per validare i nomi. Non spostare quegli import in cima.
- **`vedit/motion.py`** — registry dei movimenti sulle immagini (Ken Burns), stessa
  regola sugli import di `transitions.py`.
- **`vedit/beats.py`** — tempo e battiti di una traccia audio. ffmpeg + numpy.
- **`vedit/scenes.py`** — dove stacca un video (istogrammi), se un'inquadratura è un
  video o una foto ferma, se ha le bande. Il gemello di `beats.py`, stessa filosofia.
- **`vedit/templates.py`** — i template: `Slot`, `TemplateStyle`, `Template`, e
  `bind()`, che produce il **dizionario di un progetto**. Non importa il builder.
- **`vedit/extract.py`** — da un video a un template: chiama `beats` e `scenes`,
  riconosce stile e dissolvenze, allinea i tagli al battito, scrive il `template.yaml`.
- **`vedit/edit.py`** — gli edit: legge l'`edit.yaml`, risolve i tempi dei testi sui
  posti del template, produce il progetto (i media passano da `bind()`).
- **`vedit/text.py`** — disegna il testo in un'immagine RGBA con Pillow.
- **`vedit/fonts.py`** — ricerca dei font e a capo del testo (Pillow).
- **`vedit/sheet.py`** — il foglio dei provini di un video (ffmpeg + Pillow).
- **`vedit/report.py`** — il riepilogo di `render --check`. Legge i metadati con ffprobe.
- **`vedit/ffmpeg_tools.py`** — subprocess verso ffprobe. Nessun MoviePy.

Con MoviePy:

- **`vedit/builder.py`** — traduce `Project` in clip. È qui che vive il montaggio.
- **`vedit/progress.py`** — barra di avanzamento (usa proglog, che arriva con MoviePy).

- **`vedit/cli.py`** — argparse. Importa MoviePy **pigramente** dentro le funzioni
  comando, perché l'import è lento e `extract`/`new`/`--check` non ne hanno bisogno.

### Dove va una funzionalità nuova

Ogni nuova funzionalità del progetto richiede tre modifiche coordinate:
1. il campo in `models.py` con la sua validazione
2. la traduzione in `builder.py`
3. la riga nella tabella dello schema in `README.md`

Se il campo appartiene allo **stile di un template** (vale per tutti i posti), le
modifiche diventano cinque: il campo in `TemplateStyle` o `Slot` (`templates.py`), la
sua scrittura in `bind()`, la riga nella tabella del template. Se lo deve dedurre
`extract`, anche lì. Se invece è una scelta **di un singolo video** (un media, un
testo), va in `edit.py`: `MEDIA_KEYS` o `TEXT_KEYS`, la traduzione nel progetto, la
riga nella tabella dell'edit.

Se introduce un termine di montaggio nuovo, aggiungilo anche a `docs/GLOSSARIO.md`.

### La matematica delle posizioni sta in un posto solo

`timeline.py` ha due funzioni di piazzamento, e la differenza è il cuore del
montaggio a tempo:

- **`plan()`** — a durate: ogni segmento parte dove finisce il precedente, e una
  sovrapposizione **accorcia** il montaggio anticipando tutto quello che viene dopo.
- **`plan_anchored()`** — a istanti (`at`): le posizioni sono fissate, e il segmento
  che entra in dissolvenza parte in anticipo senza spostare nessun taglio. `at` è il
  momento in cui il segmento ha **finito** di entrare.

`builder.py` e `report.py` chiamano entrambe le stesse funzioni, e la riduzione
delle transizioni troppo lunghe la decide **solo** `plan_anchored`, che la restituisce
in `Placement.overlap`. Non ricalcolarla altrove: `--check` e il render mostrerebbero
numeri diversi, ed è esattamente il bug che quel modulo esiste per prevenire.

## Convenzioni

- Commenti e messaggi utente in **italiano**; nomi di funzioni, variabili e classi in
  **inglese**. Il codice esistente segue già questa regola.
- I commenti spiegano il **perché**, non il cosa. Il pubblico è qualcuno che sta
  imparando il dominio: quando una scelta è controintuitiva (es. la sovrapposizione
  necessaria al crossfade), spiegala.
- Type hint ovunque. `from __future__ import annotations` in cima ai moduli.
- Errori attesi → eccezioni tipizzate (`ConfigError`, `FFmpegError`) intercettate in
  `cli.py` e mostrate come messaggi leggibili, mai come traceback. In un file YAML si
  raccolgono **tutti** gli errori prima di arrendersi.
- I posti di un template si contano **da 1**, ovunque l'utente li veda: commenti del
  template, `slot:` negli edit, tabelle dei comandi.
- Nessuna dipendenza nuova senza motivo forte. Lo stack è: moviepy, PyYAML, numpy,
  Pillow. FFmpeg è un binario di sistema, non un pacchetto pip.
- I media non si versionano. L'eccezione è la traccia di un template, che ne è metà.

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

I test **non devono richiedere file video nel repo**: usa segmenti `type: color` o
immagini generate in memoria con Pillow. Se una funzionalità ha bisogno di un
sorgente reale, genera un file sintetico con ffmpeg in una fixture temporanea
(`testsrc`, `color` di lavfi), non committare media.

Prima di dichiarare completo un lavoro:
1. `pytest -q` verde e `ruff check .` pulito
2. per modifiche al rendering, un render reale e la verifica del risultato (sotto)
3. per modifiche ai template o agli edit, il giro completo su materiale sintetico:
   una tinta per posto su `templates/raffica`, render, e verifica che i tagli cadano
   sugli `at`; poi `vedit sheet ... --slots templates/raffica` e **guarda i provini**

## Verifica del risultato di un render

Non fidarti del fatto che il comando esca con codice 0: un video può essere prodotto
e essere sbagliato. Il primo controllo è guardarlo: `vedit sheet` compone i provini in
un'immagine che puoi aprire. Il secondo è misurarlo:

```python
from moviepy import VideoFileClip
v = VideoFileClip("edits/prova/output/prova_preview.mp4")
print(v.duration, v.size, v.fps)
for t in [0, 2, 5]:
    print(t, v.get_frame(t).mean(axis=(0, 1)).round(1))   # RGB medio
v.close()
```

Durante un crossfade il colore medio deve variare **gradualmente** fra i due
segmenti; se salta di colpo, la sovrapposizione non sta funzionando.

Per un template la verifica è più precisa, perché c'è un valore atteso: **i tagli
devono cadere sugli `at`**. Si applica il template a tinte unite — un colore per
slot — e si guarda il fotogramma prima e dopo ogni istante dichiarato:

```python
import yaml, numpy as np
from moviepy import VideoFileClip

istanti = [s["at"] for s in yaml.safe_load(open("templates/raffica/template.yaml"))["slots"]]
v = VideoFileClip("output/prova.mp4")
for at in istanti[1:]:
    prima, dopo = v.get_frame(at - 0.05), v.get_frame(at + 0.05)
    assert np.abs(prima.mean(axis=(0, 1)) - dopo.mean(axis=(0, 1))).max() > 20, at
v.close()
```

Con una dissolvenza il colore a `at` deve essere **già quello nuovo**: la
dissolvenza si chiude sull'istante, non ci passa in mezzo.

## Trappole già incontrate

- `CrossFadeIn` agisce sulla maschera alpha: se il clip non ha maschera l'effetto non
  ha su cosa agire. Il codice chiama `.with_mask()` come guardia — non rimuoverla.
- I clip vanno **chiusi**: ogni `VideoFileClip` apre un processo ffmpeg. Registra le
  sorgenti in `_OPEN_CLIPS` e chiudi con `close_all()`, anche in caso di eccezione.
- I percorsi nel YAML sono relativi alla cartella **del YAML**, non alla working
  directory. Usa sempre `project.resolve(path)`. Il template di un edit si scrive
  sempre relativo (`../../templates/x`): un percorso assoluto vale su una macchina sola.
- Con `pix_fmt` diverso da `yuv420p` il video non si apre su molti player. È già
  forzato negli `ffmpeg_params`.
- Il testo lo disegna **`text.py` con Pillow**, non il `TextClip` di MoviePy: il suo
  `caption` spezza le righe dentro le parole, e dalla 2.2 il suo `label` taglia in
  basso l'ultima riga di ogni scritta. Non tornare a `TextClip`.
- Pillow vuole il **percorso** di un file di font, non un nome. `fonts.py` risolve
  percorsi, nomi installati, elenchi di candidati separati da virgole e un default di
  sistema: passa sempre da lì.
- Le foto ferme si compongono sul canvas **una volta sola** (`still_on_canvas`):
  passare da `fit_clip` + `place_on_canvas` le ricomporrebbe a ogni fotogramma, e
  l'export di un template di foto costerebbe più del doppio.
- Le foto dei telefoni hanno la rotazione nei metadati EXIF: si leggono con
  `load_still`, che la applica, mai con `ImageClip(percorso)`.
- Larghezze/altezze dispari fanno fallire libx264. Se aggiungi ridimensionamenti
  dinamici (zoom, Ken Burns), arrotonda a numeri pari.
- Durante una dissolvenza al nero il rilevatore dei tagli vede tagli finti: `extract`
  li scarta (`drop_inside_fades`). Se tocchi il rilevamento, il test con le bande e la
  dissolvenza finale in `test_extract.py` deve restare verde.
