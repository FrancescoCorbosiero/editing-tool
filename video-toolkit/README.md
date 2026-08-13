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

# Riepilogo della timeline: cosa cade dove, e cosa non torna
python -m vedit render projects/demo/timeline.yaml --check

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

## Prima di renderizzare: `--check`

`--check` legge il progetto, calcola la timeline e la stampa, senza costruire né
esportare niente. Non importa nemmeno MoviePy: risponde in un decimo di secondo.

```
$ python -m vedit render projects/demo/timeline.yaml --check
Progetto : projects/demo/timeline.yaml
Canvas   : 1920x1080 @ 30 fps
Output   : /…/output/demo.mp4

  #  inizio     fine    durata  transiz.  tipo   segmento
  0  0:00.00  0:01.00     1.00s       -   color  intro     colore rgb(0, 0, 0)
  1  0:00.50  0:07.50     7.00s   0.50s   video  apertura  input.mp4  [5 -> 12]  1280x720
  2  0:06.30  0:10.30     4.00s   1.20s   image  foto-1    foto1.jpg  1080x1350
  3  0:09.50  0:16.50     7.00s   0.80s   video  chiusura  input.mp4  [40 -> 47]  1280x720

Durata totale: 0:16.50  (16.50s, 495 fotogrammi)

Avvisi (2):
  - timeline[1]: transizione ridotta da 0.8s a 0.50s (non puo' superare meta' dei clip coinvolti)
  - input.mp4: 1280x720 e' piu' piccolo del canvas 1920x1080: verra' ingrandito e apparira' meno nitido
```

La colonna `transiz.` è la sovrapposizione **effettiva** con il segmento precedente,
che non sempre coincide con quella richiesta (vedi il primo avviso). Gli avvisi
segnalano quello che il render farebbe in silenzio: tagli oltre la fine del file,
sorgenti da ingrandire, risoluzioni o frame rate discordanti fra i video, una
traccia audio più corta del montaggio.

Le tre verifiche che fa `vedit` prima di iniziare qualsiasi export:

1. **il YAML è valido** — e se non lo è, elenca *tutti* gli errori insieme, non uno per volta;
2. **i file esistono** — tutti, prima di aprirne uno solo;
3. **i conti tornano** — durate e sovrapposizioni sono calcolate dallo stesso codice
   che poi renderizza (`vedit/timeline.py`), quindi il riepilogo non può mentire.

Durante l'export vedi una riga di avanzamento con la percentuale e la stima del
tempo residuo. Se premi **Ctrl-C** il render si ferma, chiude i processi ffmpeg
e cancella il file parziale: un mp4 troncato è indistinguibile da uno buono
finché non provi ad aprirlo.

---

## Struttura del repo

```
vedit/
  models.py        Schema del progetto e parsing YAML. Nessuna dipendenza da MoviePy.
  timeline.py      Dove inizia e finisce ogni segmento. Matematica pura, niente MoviePy.
  transitions.py   Registry delle transizioni: aggiungerne una è un file solo.
  motion.py        Registry dei movimenti sulle immagini (Ken Burns).
  report.py        Il riepilogo di --check. Legge i metadati con ffprobe.
  builder.py       Traduce il progetto in clip MoviePy. È qui che vive la logica di montaggio.
  progress.py      La barra di avanzamento dell'export.
  ffmpeg_tools.py  Chiamate dirette a ffmpeg/ffprobe per le operazioni veloci.
  cli.py           Interfaccia da riga di comando.
projects/demo/     Progetto di esempio, documentato campo per campo.
examples/          Script didattici progressivi (leggili in ordine).
assets/            I tuoi file sorgente. Ignorato da git.
output/            I render. Ignorato da git.
tests/             Test rapidi che non richiedono file video.
```

La separazione `models` / `builder` è deliberata: la validazione è testabile in
millisecondi senza toccare MoviePy, che è lentissimo da importare. `timeline.py` e
`report.py` stanno dalla parte leggera del confine per lo stesso motivo — `--check`
deve rispondere subito.

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

`transition` (secondi), `transition_type`, `direction`, `image_duration` (secondi),
`fit` (`contain` | `cover` | `stretch`).

### `timeline` — segmenti in fila

| Campo | Si applica a | Note |
|---|---|---|
| `type` | — | `video` \| `image` \| `color` |
| `src` | video, image | percorso del sorgente |
| `start`, `end` | video | punti di taglio **nel sorgente**, non nella timeline |
| `duration` | image, color | |
| `transition` | tutti | durata della transizione in **entrata**, sovrascrive il default |
| `transition_type` | tutti | `crossfade` (default) \| `fade_through_black` \| `slide` \| `wipe` \| `cut` |
| `direction` | slide, wipe | bordo da cui **arriva** il nuovo clip: `left` \| `right` \| `top` \| `bottom` |
| `motion` | image | `zoom_in` \| `zoom_out` \| `pan_left` \| `pan_right` \| `pan_up` \| `pan_down` |
| `amount` | image con `motion` | quanto movimento, in frazione: `0.15` = 15% (default) |
| `speed` | video | `2.0` doppia velocità, `0.5` slow motion |
| `mute` | video | esclude l'audio del segmento |
| `fit` | video, image | sovrascrive il default (ignorato se c'è `motion`) |

### `overlays` — sovrapposti a tutto

`type` (`image` | `text`), `src`/`text`, `start`, `duration`, `width`/`height`,
`position` (`[x, y]` in pixel oppure `"center"` / `["center", "top"]`),
`fade`, `opacity`. Per il testo servono anche `font` (percorso a un `.ttf`),
`font_size`, `color`.

### `audio` — traccia aggiuntiva

`src`, `volume`, `fade_in`, `fade_out`, `start`, `replace`
(`true` sostituisce l'audio dei segmenti, `false` lo somma).

---

## Transizioni

Ogni segmento dichiara come **entra** in scena. La transizione appartiene al clip
che arriva, non alla coppia: `transition_type` sul terzo segmento descrive il
passaggio dal secondo al terzo.

```yaml
- type: image
  src: ../../assets/foto1.jpg
  transition: 1.0            # quanto dura
  transition_type: wipe      # come avviene
  direction: left            # da quale bordo arriva (solo slide e wipe)
```

| `transition_type` | Cosa fa | Sovrappone? |
|---|---|---|
| `crossfade` | dissolvenza incrociata: i due clip si vedono insieme | sì |
| `fade_through_black` | il primo si spegne nel nero, il secondo si accende | no |
| `slide` | il nuovo clip entra scorrendo da un bordo | sì |
| `wipe` | una linea attraversa lo schermo e scopre il nuovo clip | sì |
| `cut` | stacco netto, nessuna transizione | no |

**«Sovrappone» cambia la durata del montaggio.** Una transizione sovrapposta fa
coesistere i due clip per la sua durata, quindi il totale si accorcia: due clip da
4s con 1s di crossfade fanno 7s, non 8. Le altre lasciano i clip in fila e si
consumano al loro interno: `fade_through_black` spende metà della durata sulla coda
del primo clip e metà sulla testa del secondo, e il totale resta 8s.

In ogni caso la durata viene limitata a **metà del clip più corto** fra i due
coinvolti: `--check` te lo dice quando succede.

`direction` indica sempre il bordo **da cui arriva** il nuovo clip: `left` = entra
da sinistra muovendosi verso destra. Sono accettati anche `up`/`down` come sinonimi
di `top`/`bottom`.

### Aggiungere una transizione tua

Le transizioni vivono in `vedit/transitions.py`, in un registry `nome → funzione`.
Aggiungerne una è un file solo: scrivi la funzione, decorala, ed è disponibile in
YAML, in validazione e in `--check` senza toccare nient'altro.

```python
@register("fade_through_white", overlaps=False)
def fade_through_white(prev, current, ctx):
    """Come fade_through_black, ma passando dal bianco: piu' aggressivo, da usare raramente."""
    from moviepy import vfx

    half = ctx.duration / 2.0
    bianco = [255, 255, 255]
    return (
        prev.with_effects([vfx.FadeOut(half, final_color=bianco)]),
        current.with_effects([vfx.FadeIn(half, initial_color=bianco)]),
    )
```

Le regole del contratto:

- la firma è sempre `(prev, current, ctx) → (prev, current)`. Puoi modificare **anche
  il clip precedente**: è così che `fade_through_black` gli mette la dissolvenza in uscita;
- `ctx` contiene `duration` (già limitata), `direction` e `size` (il canvas);
- `overlaps=True` se i due clip devono coesistere nel tempo, `False` se restano in fila.
  Questa scelta la usa `timeline.py` per calcolare la durata finale;
- `directional=True` se usi `ctx.direction`;
- **importa MoviePy dentro la funzione**, non in cima al file: `models.py` importa
  questo modulo per validare i nomi e non deve trascinarsi dietro MoviePy.

---

## Movimento sulle immagini (effetto Ken Burns)

Una foto immobile sullo schermo è morta: l'occhio la legge in un secondo e poi si
stacca. Il rimedio classico — dal documentarista **Ken Burns**, che animava così
le fotografie d'archivio — è muovere lentamente l'inquadratura sull'immagine.

```yaml
- type: image
  src: ../../assets/foto1.jpg
  duration: 5
  motion: zoom_in      # oppure zoom_out, pan_left, pan_right, pan_up, pan_down
  amount: 0.15         # 15% di ingrandimento: quello è lo spazio su cui si muove
```

`amount` è **la corsa disponibile**, non la velocità: l'immagine viene ingrandita
di quella frazione oltre il canvas, e il movimento consuma esattamente quell'eccedenza
nell'arco della `duration`. Un segmento più lungo con lo stesso `amount` si muove
più piano. Valori fra `0.1` e `0.25` sono quasi impercettibili, che è l'obiettivo:
se noti il movimento, è troppo.

I nomi descrivono **la camera**, non l'immagine, come in ogni software di montaggio:
`pan_right` sposta l'inquadratura verso destra, quindi l'immagine sullo schermo
scivola verso sinistra.

Con `motion`, il campo `fit` viene ignorato: il movimento deve riempire il canvas,
altrimenti muoverebbe anche le bande nere. `--check` te lo ricorda.

### Quanto costa il movimento

Non è gratis, e i due tipi non costano affatto uguale:

| `motion` | export | rapporto |
|---|---|---|
| nessuno | 46s | 1.0× |
| `pan_*` | 40s | 0.9× |
| `zoom_*` | 140s | 3.0× |

*12s di video (3 immagini da 4s), 1920×1080 @ 30 fps, sorgenti 3000×2000,
`preset: ultrafast`, macchina a 4 core. Conta il rapporto, non i secondi.*

La differenza è nell'implementazione, e vale la pena capirla:

- un **pan** ingrandisce l'immagine **una volta sola** e poi ritaglia una finestra
  diversa a ogni fotogramma. Ritagliare è affettare un array numpy: costa quanto
  copiare la memoria, cioè niente. (Esce leggermente più veloce del caso statico
  perché produce fotogrammi già delle dimensioni esatte del canvas.)
- uno **zoom** deve **riscalare** l'immagine a ogni fotogramma, con
  un'interpolazione di qualità su milioni di pixel, 30 volte al secondo.

Quindi: usa `pan_*` liberamente, e `zoom_*` con criterio — o almeno monta con
`--preview` e tieni lo zoom per l'export finale. Per rimisurare sul tuo materiale:

```bash
# stessa timeline, una volta senza motion e una con
time python -m vedit render progetto-statico.yaml
time python -m vedit render progetto-zoom.yaml
```

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
