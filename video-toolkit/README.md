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

# Font utilizzabili per testo e sottotitoli su questa macchina
python -m vedit fonts

# Riepilogo della timeline: cosa cade dove, e cosa non torna
python -m vedit render projects/demo/timeline.yaml --check

# Anteprima veloce: metà risoluzione, encoding ultrafast → output/demo_preview.mp4
python -m vedit render projects/demo/timeline.yaml --preview

# Copie leggere dei sorgenti, per montare su 4K senza aspettare
python -m vedit proxy projects/demo/timeline.yaml
python -m vedit render projects/demo/timeline.yaml --preview --use-proxy

# Export finale
python -m vedit render projects/demo/timeline.yaml

# Nuovo progetto da template
python -m vedit init projects/mio-video
```

**Lavora sempre con `--preview` mentre monti.** L'export a piena risoluzione può
richiedere minuti; l'anteprima secondi. Togli il flag solo quando il montaggio ti convince.

L'anteprima riscala **tutto** il progetto, non solo il canvas: posizioni degli
overlay, corpo del testo, margini dei sottotitoli. Quello che vedi a metà
risoluzione è quello che otterrai a piena risoluzione, in miniatura.

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
  subtitles.py     Lettura dei file .srt. Solo testo, nessuna dipendenza.
  fonts.py         Trova un font utilizzabile e manda a capo il testo.
  proxies.py       Copie leggere dei sorgenti, con cache per impronta del file.
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

| Campo | Si applica a | Note |
|---|---|---|
| `type` | — | `image` \| `text` |
| `src` / `text` | image / text | il file oppure la scritta |
| `start`, `duration` | tutti | `duration` assente = fino alla fine del video |
| `width`, `height` | image | uno solo dei due mantiene le proporzioni |
| `position` | tutti | `[x, y]` in pixel, oppure `"center"` / `["center", "top"]` |
| `fade`, `opacity` | tutti | dissolvenza in entrata/uscita e trasparenza |

I campi di **stile del testo** valgono sia qui sia nei sottotitoli:

| Campo | Default (overlay) | Note |
|---|---|---|
| `font` | primo font di sistema | percorso a un `.ttf`/`.otf` **oppure** nome di un font installato |
| `font_size` | `64` | |
| `color` | `white` | nome o `#rrggbb` |
| `stroke_color`, `stroke_width` | nessuno | contorno: la difesa più economica contro uno sfondo mosso |
| `bg_color`, `bg_opacity` | nessuno, `0.6` | riquadro dietro il testo; `bg_color` è un nome o `[R,G,B]` |
| `max_width` | nessuno | `≤ 1` = frazione del canvas, `> 1` = pixel. Attiva l'a capo automatico |
| `align` | `center` | `left` \| `center` \| `right` |
| `padding` | `0` | spazio fra testo e bordo del riquadro |

### `subtitles` — un file `.srt` sopra tutto il montaggio

| Campo | Default | Note |
|---|---|---|
| `src` | — | percorso del `.srt` |
| `margin_bottom` | `60` | distanza dal bordo inferiore, in pixel |
| `offset` | `0` | sposta **tutti** i tempi: per rimettere in sincrono un srt sfasato |
| stile | `font_size: 48`, bianco con contorno nero, `max_width: 0.8`, `padding: 8` | vedi la tabella sopra |

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

## Testo e sottotitoli

### Il font: il problema numero uno

MoviePy disegna il testo con Pillow, che vuole il **percorso di un file** `.ttf`
o `.otf`. Non conosce i nomi dei font installati come farebbe un word processor,
e se non gli si dice niente ripiega su un font interno minimale — quando non
fallisce del tutto. È la ragione per cui in rete si trovano decine di
segnalazioni di «TextClip non funziona».

`vedit` accetta tre modi di indicarlo, in ordine di precedenza:

```yaml
font: ../../assets/fonts/Inter-Bold.ttf   # 1. percorso, relativo al file YAML
font: DejaVu Sans                          # 2. nome di un font installato
# (niente)                                 # 3. un font di sistema scelto da vedit
```

```bash
python -m vedit fonts     # cosa c'è su questa macchina, e quale verrebbe usato
```

**Nel repo non c'è nessun font**, di proposito: sono file binari, con licenze
proprie da rispettare e ridistribuire, e ogni sistema operativo ne ha già di
ottimi installati. Se ti serve un font specifico — perché il video deve essere
coerente con un'identità visiva — mettilo in `assets/fonts/` e indicane il
percorso: quella cartella è ignorata da git, come tutti i media.

### Rendere il testo leggibile

Il testo su video ha un solo problema: ci finisce sopra qualsiasi cosa. Le tre
difese, in ordine di efficacia:

```yaml
overlays:
  - type: text
    text: "Il mio primo montaggio"
    stroke_color: black      # 1. contorno: costa niente, funziona quasi sempre
    stroke_width: 2
    bg_color: black          # 2. riquadro semitrasparente: l'unico che regge
    bg_opacity: 0.45         #    su uno sfondo molto mosso
    padding: 14              #    (dà respiro fra lettere e bordo del riquadro)
    font_size: 72            # 3. corpo grande: aiuta, ma non basta da solo
    max_width: 0.7           # va a capo da solo entro il 70% del canvas
    align: center
    position: ["center", 820]
```

`max_width` attiva **l'a capo automatico alle parole**. Il riquadro di sfondo
resta largo quanto la riga più lunga: un testo corto non si porta dietro un
rettangolo mezzo vuoto.

### Sottotitoli da file `.srt`

```yaml
subtitles:
  src: ../../assets/dialoghi.srt
  font_size: 42
  stroke_color: black
  stroke_width: 2
  max_width: 0.8            # 80% del canvas
  margin_bottom: 70         # distanza dal bordo inferiore
  offset: -0.5              # tutto mezzo secondo prima: sistema un srt sfasato
```

Un `.srt` è testo semplice, a blocchi separati da una riga vuota:

```
1
00:00:01,000 --> 00:00:04,200
Prima battuta,
anche su due righe
```

Il numero progressivo serve solo agli umani, `vedit` lo ignora. Vengono accettati
i ritorni a capo di Windows, il BOM del Blocco Note, il punto al posto della
virgola nei millisecondi e i file salvati in latin-1. Ogni battuta diventa un clip
di testo indipendente, posizionato **dal basso**: un sottotitolo su due righe è
più alto, e ancorandolo in alto la seconda riga finirebbe fuori dal quadro.

`--check` conta le battute e avvisa su quelle che si sovrappongono nel tempo, che
durano meno di mezzo secondo (illeggibili) o che iniziano dopo la fine del montaggio.

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

## Montare su 4K: i proxy

Montare direttamente su file 4K è insopportabile: ogni fotogramma va decodificato,
ridimensionato e ricomposto, e quel lavoro viene buttato via al tentativo successivo.
La soluzione standard nei software di montaggio si chiama **proxy**: si genera una
volta una copia a bassa risoluzione di ogni sorgente, si monta su quella, e l'export
finale torna agli originali. Il montaggio non cambia — tagli, transizioni e durate
lavorano sul *tempo*, non sui pixel — cambia solo quanto aspetti.

```bash
# una volta sola: crea proxies/ accanto al file di progetto
python -m vedit proxy projects/demo/timeline.yaml

# mentre monti: veloce
python -m vedit render projects/demo/timeline.yaml --preview --use-proxy

# export finale: sempre dagli originali
python -m vedit render projects/demo/timeline.yaml
```

Misurato su un sorgente 3840×2160, montaggio di 10s verso 1080p:

| operazione | tempo |
|---|---|
| anteprima dai sorgenti 4K | 51s |
| generazione dei proxy (una volta sola) | 2.5s |
| anteprima dai proxy | **9.6s** |

**5× più veloce**, e la generazione si ripaga alla prima anteprima. Su riprese
reali la generazione è più lenta (il sorgente sintetico di questa misura è
pochissimi MB), ma il guadagno per anteprima è lo stesso.

### La cache

Il nome del proxy contiene un'impronta del contenuto del sorgente:

```
proxies/riprese-480p-35e057a4c37b.mp4
```

Se il file originale cambia, cambia l'impronta, il proxy vecchio non viene più
trovato e ne nasce uno nuovo. Non esiste un controllo «è aggiornato?» da
sbagliare, e non c'è modo di montare per errore su un proxy che non corrisponde
più al suo originale. L'impronta si calcola su dimensione, primo e ultimo MiB:
leggere per intero un file da 20 GB costerebbe, a ogni controllo, il tempo che
i proxy servono a risparmiare.

`--height` genera proxy a un'altezza diversa (convivono con quelli già fatti),
`--force` li rigenera. Un sorgente già più piccolo dell'altezza richiesta viene
saltato: non ha senso rimpicciolire ciò che è già piccolo.

### Le due protezioni

- **`--use-proxy` senza `--preview`** aggiunge `_proxy` al nome del file: un
  export a piena risoluzione fatto sui proxy è indistinguibile da quello buono
  finché non lo guardi, e non deve poterlo sovrascrivere.
- **Proxy mancante** non è un errore: `vedit` avvisa e monta quel segmento
  sull'originale. Chi ha appena aggiunto una ripresa non deve vedere un render
  che fallisce.

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
