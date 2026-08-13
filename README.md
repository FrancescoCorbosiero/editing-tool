# vedit — montaggio video da codice

Toolkit per montare video scrivendo un file YAML invece di trascinare clip in una GUI.
Costruito su **MoviePy 2.x** (composizione) e **FFmpeg** (operazioni veloci).

```yaml
timeline:
  - type: video
    src: assets/riprese.mp4
    start: 5
    end: 12
  - type: image
    src: assets/foto.jpg
    duration: 4
    transition: 1.2
```

```bash
python -m vedit render projects/demo/timeline.yaml
```

---

## Installazione

**1. FFmpeg** (obbligatorio, non è una libreria Python):

```bash
brew install ffmpeg              # macOS
winget install Gyan.FFmpeg       # Windows
sudo apt install ffmpeg          # Ubuntu/Debian
```

Verifica con `ffmpeg -version`.

**2. Ambiente Python** (serve Python 3.10+):

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Prova**:

```bash
python -m vedit render projects/demo/timeline.yaml --dry-run
```

Il `--dry-run` costruisce la timeline e valida il file senza esportare nulla: è il modo
più rapido per scoprire un errore di configurazione.

---

## Uso

```bash
# Metadati di un file (durata, risoluzione, fps, codec)
python -m vedit probe assets/riprese.mp4

# Anteprima veloce: metà risoluzione, encoding ultrafast → output/demo_preview.mp4
python -m vedit render projects/demo/timeline.yaml --preview

# Export finale
python -m vedit render projects/demo/timeline.yaml

# Nuovo progetto da template
python -m vedit init projects/mio-video
```

**Lavora sempre con `--preview` mentre monti.** L'export a piena risoluzione può
richiedere minuti; l'anteprima secondi. Togli il flag solo quando il montaggio ti convince.

---

## Struttura del repo

```
vedit/
  models.py        Schema del progetto e parsing YAML. Nessuna dipendenza da MoviePy.
  builder.py       Traduce il progetto in clip MoviePy. È qui che vive la logica di montaggio.
  ffmpeg_tools.py  Chiamate dirette a ffmpeg/ffprobe per le operazioni veloci.
  cli.py           Interfaccia da riga di comando.
projects/demo/     Progetto di esempio, documentato campo per campo.
examples/          Script didattici progressivi (leggili in ordine).
assets/            I tuoi file sorgente. Ignorato da git.
output/            I render. Ignorato da git.
tests/             Test rapidi che non richiedono file video.
```

La separazione `models` / `builder` è deliberata: la validazione è testabile in
millisecondi senza toccare MoviePy, che è lentissimo da importare.

---

## Schema del progetto

### `output`

| Campo | Default | Note |
|---|---|---|
| `path` | `output/out.mp4` | relativo alla cartella del YAML |
| `size` | `[1920, 1080]` | tutto viene adattato a queste dimensioni |
| `fps` | `30` | |
| `codec` | `libx264` | `libx265` per file più piccoli ma meno compatibili |
| `preset` | `medium` | `ultrafast`…`veryslow`: più lento = file più piccolo |
| `crf` | `20` | 18 alta qualità · 23 default · 28 compresso |
| `background` | `[0,0,0]` | colore delle bande in modalità `contain` |

### `defaults`

`transition` (secondi), `image_duration` (secondi), `fit` (`contain` | `cover` | `stretch`).

### `timeline` — segmenti in fila

| Campo | Si applica a | Note |
|---|---|---|
| `type` | — | `video` \| `image` \| `color` |
| `src` | video, image | percorso del sorgente |
| `start`, `end` | video | punti di taglio **nel sorgente**, non nella timeline |
| `duration` | image, color | |
| `transition` | tutti | crossfade in **entrata**, sovrascrive il default |
| `speed` | video | `2.0` doppia velocità, `0.5` slow motion |
| `mute` | video | esclude l'audio del segmento |
| `fit` | video, image | sovrascrive il default |

### `overlays` — sovrapposti a tutto

`type` (`image` | `text`), `src`/`text`, `start`, `duration`, `width`/`height`,
`position` (`[x, y]` in pixel oppure `"center"` / `["center", "top"]`),
`fade`, `opacity`. Per il testo servono anche `font` (percorso a un `.ttf`),
`font_size`, `color`.

### `audio` — traccia aggiuntiva

`src`, `volume`, `fade_in`, `fade_out`, `start`, `replace`
(`true` sostituisce l'audio dei segmenti, `false` lo somma).

---

## Le tre cose che confondono all'inizio

**1. Un crossfade richiede sovrapposizione.**
Se metti due clip in fila e aggiungi una dissolvenza al secondo, questo dissolve
dal *nero*, non dal primo clip. I due clip devono coesistere nel tempo.
`concat_with_transitions()` in `builder.py` lo fa facendo partire ogni clip a
`cursore − durata_transizione`.

**2. `start`/`end` sono nel tempo del sorgente.**
`start: 40` significa "prendi dal minuto 0:40 del file originale", non "metti questo
segmento al secondo 40 del montaggio". La posizione nella timeline è determinata
dall'ordine dei segmenti.

**3. La maggior parte dei tutorial online è per MoviePy 1.x.**
La 2.0 ha rotto l'API: `moviepy.editor` non esiste più, `subclip` è `subclipped`,
`set_position` è `with_position`, gli effetti sono classi applicate con
`.with_effects([...])`. Se copi codice da Stack Overflow e ottieni `AttributeError`,
quasi certamente è questo.

---

## Quando usare FFmpeg direttamente

MoviePy passa ogni fotogramma attraverso Python e numpy: è comodo per comporre,
ma lento. Per tagliare, concatenare o ridimensionare senza effetti, `ffmpeg_tools.py`
espone wrapper che sono 10–50× più veloci:

```python
from vedit.ffmpeg_tools import fast_cut, make_proxy, probe

probe("assets/riprese.mp4")                          # metadati
fast_cut("in.mp4", "out.mp4", 10, 25)                # taglio senza ricompressione
make_proxy("in.mp4", "proxies/in.mp4", height=480)   # versione leggera per montare
```

`fast_cut` non ricomprime: è istantaneo e senza perdita, ma il taglio si allinea al
keyframe più vicino (scarto fino a qualche decimo di secondo). Per il fotogramma
esatto usa `accurate_cut`.

---

## Test

```bash
pytest -q
```

I test coprono parsing, validazione e matematica delle transizioni usando segmenti
`color` generati in memoria — nessun file video richiesto, girano in meno di un secondo.

---

## Percorso di apprendimento

Leggi gli script in `examples/` in ordine, lanciandoli:

1. `01_taglio_e_concatenazione.py` — tagliare e attaccare
2. `02_transizioni.py` — perché serve la sovrapposizione
3. `03_immagini_e_overlay.py` — livelli e posizionamento
4. `04_usa_il_toolkit.py` — generare timeline da codice

Poi apri `builder.py`: a quel punto lo leggerai senza fatica.

---

## Riferimenti

- [Documentazione MoviePy 2.x](https://zulko.github.io/moviepy/)
- [Guida alla migrazione 1.x → 2.x](https://zulko.github.io/moviepy/getting_started/updating_to_v2.html)
- [Filtri FFmpeg](https://ffmpeg.org/ffmpeg-filters.html)
