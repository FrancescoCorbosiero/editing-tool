# vedit — video a tempo di musica

Video verticali in cui ogni cambio di immagine cade sul battito, con dei testi sopra:
il genere "usa questo suono" dei social. Prendi un video che ti piace, ne ricavi la
**struttura** — la musica, gli istanti dei tagli, lo stile — e la riempi ogni volta
con media e testi diversi.

```yaml
# edits/ormone/edit.yaml
template: ../../templates/raffica

media:
  - media/apertura.mp4         # 1) il video dell'apertura, 4 secondi
  - media/grafico.png          # 2) poi un'immagine per battito...
  - media/studio.png
  - media/onda.gif             # le GIF corte ripartono da capo

texts:
  - text: "L'ormone della crescita"
    slot: 2-8                  # dal posto 2 alla fine dell'8, sul battito
    position: top
```

```bash
vedit render edits/ormone --preview
```

---

## Come funziona

Due oggetti, e la differenza fra loro è tutta l'idea:

```
 un video che ti piace ──extract──▶ templates/raffica/          una volta
                                        │  musica, tagli, stile
                                        ▼
 i tuoi media + testi ──────────▶ edits/ormone/edit.yaml ──render──▶ mp4    ogni video
```

- il **template** è la parte che **non cambia**: la traccia audio, gli istanti in cui
  si stacca, come entrano le immagini (intere su nero o a tutto schermo), come si apre
  e si chiude il video, l'aspetto dei testi;
- l'**edit** è la parte che **cambia a ogni video**: quale media va in quale posto, e
  quali testi compaiono, dove e quando.

È lo stesso gesto di quando sui social riusi un "suono": non prendi in prestito una
canzone, prendi in prestito un montaggio che su quella canzone funziona. La differenza
è che qui il montaggio è un file di testo che si legge, si corregge e si versiona.

## Con un assistente

Il modo previsto di usarlo è con Claude Code aperto su questo repo, che fa il lavoro
al posto tuo. Il repo ha due skill che descrivono la procedura passo per passo:

| chiedi | succede | skill |
|---|---|---|
| carichi un video e chiedi di **templetizzarlo** | ne estrae musica, tagli e stile, lo verifica e lo salva in `templates/` | `templetizza` |
| mandi immagini, video, GIF e i **testi** che vuoi | crea l'edit, mette i media nei posti, i testi dove dici, controlla i provini e ti manda il video | `monta` |

Per cambiare qualcosa basta dirlo ("metti il video al posto 5", "il titolo più in
alto", "togli l'ultima scritta"): l'edit si corregge e il template resta lo stesso.

## A mano

```bash
vedit extract riferimento.mp4 -o templates/raffica   # un template da un video
vedit templates                                      # i template che hai

vedit new edits/ormone --template templates/raffica  # un edit nuovo, commentato posto per posto
vedit render edits/ormone --check                    # cosa cade dove, senza renderizzare
vedit render edits/ormone --preview                  # anteprima veloce (metà risoluzione)
vedit render edits/ormone                            # il video finale
vedit sheet edits/ormone/output/ormone.mp4 --slots templates/raffica   # i provini

vedit shots riferimento.mp4                          # i tagli che il rilevatore vede
vedit beats riferimento.mp4                          # tempo e battiti della musica
vedit apply templates/raffica cartella/ --preview    # prova veloce: media in ordine, niente testi
```

**Lavora sempre con `--preview`.** L'anteprima riscala tutto il progetto, testi
compresi: quello che vedi a metà risoluzione è quello che otterrai, in miniatura.

---

## L'edit

`vedit new` crea la cartella `edits/<nome>/` con un `edit.yaml` già pronto: un posto
per riga, con un commento che dice quando entra, quanto dura e cosa c'era lì nel video
di riferimento.

```yaml
template: ../../templates/raffica      # 32 posti, 151.5 BPM, 18.13s, 720x1280

media:
  - media/01.mp4                 #  1)    0.00s  dura 3.86s  video  [apertura]
  - media/02.jpg                 #  2)    3.86s  dura 0.20s
  - media/03.jpg                 #  3)    4.06s  dura 0.20s
  ...

texts: []
```

I media vanno in `edits/<nome>/media/` (ignorata da git, come `output/`): l'edit si
versiona, i file no.

### `media` — un media per posto, in ordine

| forma | significato |
|---|---|
| `media/foto.jpg` | un'immagine: entra intera o a tutto schermo, come dice lo stile del template |
| `media/clip.mp4` | un video, dall'inizio |
| `media/clip.mp4@12.5` | un video, dal secondo 12.5 del file |
| `media/onda.gif` | una GIF: se è più corta del posto riparte da capo |
| `{src: ..., ...}` | una mappa, per cambiare le scelte del template su quel posto: |
| `start` | da quale secondo del file (come `@`) |
| `fit` | `contain` (intera, con le bande) \| `cover` (a tutto schermo) \| `stretch` |
| `motion`, `amount` | un movimento sulla foto (`zoom_in`, `pan_left`...; `none` lo toglie) |
| `loop` | `true` per far ripartire un video corto invece di rallentarlo |

Con meno media che posti i media si ripetono da capo (e `vedit` lo dice); con più
media che posti gli ultimi restano fuori. Un video più corto del suo posto viene
rallentato fino a riempirlo, perché il taglio dopo cade sul battito e il battito non
si sposta; sotto `0.25x` è un errore.

### `texts` — cosa, quando, dove

```yaml
texts:
  - text: "L'ormone della crescita"
    slot: 2-8
    position: top
  - text: "191 aminoacidi"
    at: 1.0
    duration: 2.5
    position: bottom
  - text: "Funziona davvero?"
    slot: 25
    bg_color: black
    bg_opacity: 0.6
    padding: 16
```

| campo | | significato |
|---|---|---|
| `text` | obbligatorio | la scritta; `\n` va a capo, altrimenti va a capo da sola |
| `slot` | uno fra `slot` e `at` | `3` = per tutto il posto 3; `3-5` = dall'inizio del 3 alla fine del 5 |
| `at` | | in secondi: compare lì e dura fino al taglio dopo |
| `duration` | | quanti secondi dura (con `slot` o con `at`) |
| `position` | `center` | `top` \| `center` \| `bottom`, un numero fra 0 e 1 (l'altezza: 0 in cima), oppure `[x, y]` in frazioni |
| `fade` | `0` | secondi di dissolvenza in entrata e in uscita |
| stile | dal template | qualsiasi campo di stile del testo (vedi [Testo](#testo)) |

**Agganciare un testo a un posto** invece che ai secondi lo fa comparire e sparire
sul battito, insieme all'immagine: è il motivo per cui `slot` è il modo consigliato.

Le posizioni `top` e `bottom` stanno dentro la **safe area**, la parte dello schermo
che le app non coprono con i loro pulsanti; con le frazioni il testo si centra sul
punto indicato e non esce mai dallo schermo. Le misure dello stile in pixel si
intendono sul formato del template: se l'edit esporta in un altro formato, scalano.

### Gli altri campi

| campo | significato |
|---|---|
| `template` | la cartella del template, relativa all'edit (obbligatorio) |
| `output` | il file finale (default `output/<nome dell'edit>.mp4`) |
| `size`, `fps` | per esportare in un formato diverso da quello del template |
| `keep_audio` | `true` tiene l'audio dei tuoi video sotto la musica (default: tolto) |
| `volume` | il volume della musica del template (`1` = com'è) |

`vedit render edits/ormone --to-yaml progetto.yaml` scrive il `timeline.yaml` in cui
l'edit si espande: è la valvola di sfogo per le modifiche che l'edit non prevede.

---

## Il template

```
templates/raffica/
├── template.yaml     la struttura: istanti dei tagli, stile, formato, stile dei testi
└── audio.m4a         la traccia su cui quegli istanti sono stati misurati
```

La traccia vive dentro il template ed è l'unico media che si versiona: gli istanti dei
tagli sono i battiti **di quella musica**, e staccati da lei sarebbero numeri a caso.
Un template dura quanto la sua traccia e ha un numero fisso di posti.

### Cosa fa `vedit extract`

```
$ vedit extract riferimento.mp4 -o templates/raffica
Template : raffica  ->  templates/raffica
Traccia  : audio.m4a  (18.13s)
Tempo    : 151.5 BPM  (un battito ogni 0.396s, il primo a 0.100s)
Formato  : 720x1280 @ 30 fps
Stile    : media interi su rgb(0, 0, 0) (contain), si spegne nel nero in 1.97s
Slot     : 32  (il piu' corto 0.17s, il piu' lungo 3.86s)
Griglia  : half - 26 tagli riallineati al battito, in media di 26 ms

  #   entra a   dura   battiti  transizione  nel riferimento  movimento
  1      0.00   3.86s     9.75  cut          video            -
  2      3.86   0.20s     0.50  cut          -                -
  3      4.06   0.20s     0.50  cut          -                -
  ...
```

| passo | modulo | domanda |
|---|---|---|
| battito | `beats.py` | in quali istanti cade la cassa? |
| tagli | `scenes.py` | in quali istanti cambia l'inquadratura? |
| contenuto | `scenes.py` | quell'inquadratura era un video o una foto ferma? aveva le bande? |
| stile | `extract.py` | le immagini erano intere o a tutto schermo? il video si apre o si chiude nel nero? |
| allineamento | `extract.py` | quali tagli erano sul battito, e quanto ci sono andati vicini? |

**L'allineamento è il passaggio che rende un template riusabile.** I tagli misurati
non cadono mai esattamente sul battito: a 30 fps un fotogramma dura 33 ms, e chi ha
montato aveva la sua mano. Avvicinarli al battito più vicino dà una griglia pulita.
È prudente: sposta un taglio solo se era già vicino; uno a metà strada fra due
battiti è in levare — una scelta — e resta dov'è. `--grid` decide la finezza:

| `--grid` | allinea a | quando |
|---|---|---|
| `beat` | i battiti | montaggi lenti, un'immagine per battito |
| `half` (default) | anche i mezzi battiti | il caso normale |
| `quarter` | anche i quarti | montaggi fittissimi |
| `off` | niente | video parlati: i tagli seguono la voce, non la musica |

Il template **riproduce** il riferimento, non lo abbellisce: una foto finisce in
movimento solo dove il riferimento scorreva davvero, e mai se le immagini entrano
intere (il movimento le taglierebbe).

### Lo schema di `template.yaml`

| campo | | significato |
|---|---|---|
| `name`, `duration` | | nome; quanto dura il montaggio, cioè la traccia |
| `audio.src`, `audio.bpm`, `audio.offset` | | la traccia, il tempo, dove cade il primo battito |
| `audio.volume`, `audio.fade_out` | | livello e dissolvenza audio in chiusura |
| `format.size`, `format.fps` | | il canvas del riferimento |
| `style.fit` | `cover` | come entrano i media: `contain` (interi, con le bande) \| `cover` \| `stretch` |
| `style.background` | `[0,0,0]` | colore delle bande |
| `style.fade_in`, `style.fade_out` | `0` | secondi di dissolvenza dal nero all'inizio, al nero alla fine |
| `text` | proporzionato al canvas | lo stile di partenza dei testi degli edit (campi della tabella [Testo](#testo)) |
| `slots[].at` | obbligatorio | istante in cui il posto entra in scena |
| `slots[].hint` | | cosa c'era nel riferimento: `video` \| `image` (un consiglio) |
| `slots[].label` | | un nome per quel posto (`apertura`, `pausa`) |
| `slots[].transition`, `transition_type` | `cut` | come entra: `crossfade` \| `fade_through_black` \| `slide` \| `wipe` |
| `slots[].motion`, `amount` | | movimento se ci finisce una foto |
| `slots[].fit` | lo stile | per cambiare il fit di un posto solo |

**Uno slot non ha una durata.** Finisce quando comincia il successivo, e l'ultimo con
la traccia. Il template è un file di testo pensato per essere corretto a mano:
spostare un `at` sposta *quel* taglio e basta; dare un `label` ai posti che contano
aiuta a parlarne.

### Limiti, onestamente

Il rilevatore trova i **tagli netti**, che sono la stragrande maggioranza; una
dissolvenza lenta fra due immagini non produce nessun picco. Gli stacchi rapidi da
mezzo battito restano posti; i lampi sotto 0.15s si fondono con il posto vicino
(`--min-slot 0.1` per tenerli). Il tempo si
riconosce su musica con una cassa marcata e un tempo stabile — elettronica, pop, hip
hop — e sbaglia su registrazioni dal vivo e brani acustici. Per questo `vedit shots`,
`vedit beats` e `vedit sheet --shots` esistono come comandi a sé: si guarda cosa ha
capito la macchina **prima** di costruirci sopra.

La traccia di un template resta di chi l'ha fatta: estrarla è comodo per lavorare,
pubblicare è un altro discorso (vedi [templates/README.md](templates/README.md)).

---

## Prima di renderizzare: `--check`

`--check` legge l'edit, calcola il montaggio e lo stampa, senza costruire né esportare
niente. Non importa nemmeno MoviePy: risponde in un attimo.

```
$ vedit render edits/ormone --check
  #   entra a   dura   media
  1      0.00   3.86s  apertura.mp4
  2      3.86   0.20s  grafico.png
 ...
 14      7.82   0.40s  onda.gif   (in loop)

  #  inizio     fine    durata  transizione  tipo   segmento
  0  0:00.00  0:03.86     3.86s  -    video  apertura  apertura.mp4  [0 -> 3.86]  muto  720x1280
 ...
Durata totale: 0:18.13  (18.13s, 543 fotogrammi)
Dissolvenze : al nero negli ultimi 1.97s

Sopra il montaggio (2):
   inizio     fine  dove      cosa
  0:03.86  0:06.24  top       L'ormone della crescita
  0:11.78  0:13.76  center    Funziona davvero?

Avvisi (1):
  - onda.gif: 240x240 verra' ingrandito 3.0 volte per entrare nel canvas 720x1280 (contain): apparira' meno nitido
```

Le verifiche che fa `vedit` prima di qualsiasi export:

1. **il YAML è valido** — e se non lo è elenca *tutti* gli errori insieme, con il
   numero del testo o del media sbagliato (un campo scritto male, un posto che non
   esiste, `slot` e `at` insieme);
2. **i file esistono** — tutti, prima di aprirne uno solo;
3. **i conti tornano** — posizioni e durate vengono dallo stesso codice che poi
   renderizza (`vedit/timeline.py`), quindi il riepilogo non può mentire.

Durante l'export una riga mostra la percentuale e il tempo residuo; **Ctrl-C** ferma
tutto, chiude i processi ffmpeg e cancella il file parziale.

## I provini: `vedit sheet`

Un'immagine con tanti fotogrammi del video, per guardarlo tutto con un colpo d'occhio:

```bash
vedit sheet riferimento.mp4 --shots                       # uno per inquadratura
vedit sheet edits/ormone/output/ormone.mp4 --slots templates/raffica   # uno per posto
vedit sheet qualsiasi.mp4 --every 0.5                     # uno ogni mezzo secondo
```

È il modo di controllare un render senza riprodurlo: ogni posto ha il media giusto?
i testi si leggono e sono interi? Ed è come un assistente guarda i video che monta.

---

## Il progetto: `timeline.yaml`

Template ed edit non sono un secondo motore di montaggio: **generano un
`timeline.yaml`**, il formato che il builder sa montare, e che si può scrivere anche a
mano (`--to-yaml` lo salva). Questo è il suo schema.

### `output` e il resto del progetto

| Campo | Default | Note |
|---|---|---|
| `output.path` | `output/out.mp4` | relativo alla cartella del YAML |
| `output.size` | `[1920, 1080]` | tutto viene adattato a queste dimensioni |
| `output.fps` | `30` | |
| `output.codec` | `libx264` | `libx265` per file più piccoli ma meno compatibili |
| `output.preset` | `medium` | `ultrafast`…`veryslow`: più lento = file più piccolo |
| `output.crf` | `20` | 18 alta qualità · 23 default · 28 compresso |
| `output.background` | `[0,0,0]` | colore delle bande in modalità `contain` |
| `fade_in`, `fade_out` | `0` | secondi di dissolvenza dal nero all'inizio e al nero alla fine di tutto il video, testi compresi |
| `defaults` | | `transition`, `transition_type`, `direction`, `image_duration`, `fit` |
| `audio` | | `src`, `volume`, `fade_in`, `fade_out`, `start`, `replace` (`true` sostituisce l'audio dei segmenti) |

### `timeline` — i segmenti

| Campo | Si applica a | Note |
|---|---|---|
| `type` | — | `video` \| `image` \| `color` |
| `src` | video, image | percorso del sorgente |
| `start`, `end` | video | punti di taglio **nel sorgente**, non nella timeline |
| `duration` | image, color | |
| `at` | tutti | istante sul **montaggio** in cui il segmento entra in scena |
| `transition`, `transition_type`, `direction` | tutti | la transizione in **entrata** (vedi [Transizioni](#transizioni)) |
| `motion`, `amount` | image | movimento sulla foto, `amount` = 0.15 vuol dire 15% |
| `speed` | video | `2.0` doppia velocità, `0.5` rallentatore |
| `loop` | video | se il sorgente finisce prima del segmento, ricomincia da capo |
| `mute` | video | esclude l'audio del segmento |
| `fit` | video, image | sovrascrive il default (ignorato se c'è `motion`) |

### `overlays` — sopra a tutto

| Campo | Si applica a | Note |
|---|---|---|
| `type` | — | `image` \| `text` |
| `src` / `text` | image / text | il file oppure la scritta |
| `start`, `duration` | tutti | `duration` assente = fino alla fine del video |
| `position` | tutti | `top` \| `center` \| `bottom`; `{x, y}` in frazioni (il centro dell'overlay va lì); `[x, y]` in pixel (l'angolo in alto a sinistra) |
| `width`, `height` | image | uno solo dei due mantiene le proporzioni |
| `fade`, `opacity` | tutti | dissolvenza in entrata/uscita e trasparenza |
| stile | text | i campi della tabella [Testo](#testo) |

### Durate o istanti

Un progetto si scrive in due modi. **A durate** ogni segmento dice quanto dura, e la
sua posizione è la somma di quelli prima: comodo per un racconto, pessimo per la
musica, perché **allungare uno spezzone sposta tutti i tagli successivi**. **A
istanti** ogni segmento dichiara `at`, il momento in cui entra, e finisce quando entra
il successivo: spostare un taglio è cambiare un numero, e si muove solo quel taglio.
È il modo in cui template ed edit scrivono i progetti.

| campo | in quale tempo |
|---|---|
| `at` | il **montaggio finale** — quando lo spettatore vede il cambio |
| `start` / `end` | il **file sorgente** — da dove si prende il materiale |

Le regole, verificate da `--check`: o hanno `at` **tutti** i segmenti o nessuno; il
primo `at` è `0` e gli istanti crescono; l'ultimo segmento dichiara `end` o
`duration`, perché non ha un taglio dopo di sé che lo chiuda.

**Le dissolvenze non spostano gli istanti.** Una dissolvenza incrociata ha bisogno
che il clip che entra cominci **prima** della fine del precedente. La conciliazione
con `at`: `at` è il momento in cui il segmento **ha finito di entrare**. Il clip parte
`transition` secondi prima, e il taglio resta dov'era — sul battito.

---

## Transizioni

Ogni segmento dichiara come **entra** in scena; la transizione appartiene al clip che
arriva. I template estratti usano gli stacchi netti del riferimento; le altre si
mettono a mano su uno slot (`transition: 0.3` + `transition_type: crossfade`).

| `transition_type` | Cosa fa | Sovrappone? |
|---|---|---|
| `cut` | stacco netto | no |
| `crossfade` | dissolvenza incrociata: i due clip si vedono insieme | sì |
| `fade_through_black` | il primo si spegne nel nero, il secondo si accende | no |
| `slide` | il nuovo clip entra scorrendo da un bordo (`direction`) | sì |
| `wipe` | una linea attraversa lo schermo e scopre il nuovo clip | sì |

La durata viene limitata a **metà del clip più corto** fra i due coinvolti, e
`--check` lo dice. Le transizioni vivono in `vedit/transitions.py`, in un registry
`nome → funzione`: aggiungerne una è una funzione decorata con `@register`, e diventa
disponibile in YAML, nella validazione e in `--check` senza toccare nient'altro (le
regole del contratto sono nel docstring del modulo).

## Testo

Il testo lo disegna `vedit/text.py` con Pillow, non il `TextClip` di MoviePy, che
spezza le parole a metà e dalla versione 2.2 taglia in basso l'ultima riga.

| Campo | Default | Note |
|---|---|---|
| `font` | dal template | percorso a un `.ttf`/`.otf`, nome di un font installato, o più candidati separati da virgole: vince il primo che c'è |
| `font_size` | dal template | in pixel |
| `color` | `white` | nome, `#rrggbb` |
| `stroke_color`, `stroke_width` | `black`, proporzionato | contorno: la difesa più economica contro uno sfondo mosso |
| `bg_color`, `bg_opacity` | nessuno, `0.6` | riquadro dietro il testo; un nome o `[R,G,B]` |
| `padding` | `0` | spazio fra testo e bordo del riquadro |
| `max_width` | `0.84` | `≤ 1` = frazione del canvas, `> 1` = pixel. Va a capo alle parole entro quella larghezza |
| `align` | `center` | `left` \| `center` \| `right` |

Lo stile di partenza di ogni template è bianco, grassetto, con un contorno nero:
si legge sopra qualsiasi cosa, chiara o scura, senza bisogno di un riquadro. Su
immagini molto fitte (uno screenshot pieno di testo) un riquadro semitrasparente
(`bg_color: black`, `bg_opacity: 0.6`, `padding: 16`) è l'unica difesa che regge.

`vedit fonts` dice quali font ci sono su questa macchina e quale verrebbe usato. Nel
repo non c'è nessun font: lo stile dei template indica `DejaVu Sans Bold, Arial Bold,
arialbd`, che dà lo stesso aspetto su Linux, Mac e Windows.

## Movimento sulle foto (Ken Burns)

Una foto può muoversi lentamente nel suo posto — dal documentarista **Ken Burns**,
che animava così le fotografie d'archivio:

```yaml
- src: media/foto.jpg
  motion: zoom_in      # oppure zoom_out, pan_left, pan_right, pan_up, pan_down
  amount: 0.15         # 15% di ingrandimento: lo spazio su cui si muove
```

`amount` è la corsa, non la velocità: un posto più lungo con lo stesso `amount` si
muove più piano. I nomi descrivono **la camera**: `pan_right` sposta l'inquadratura
a destra, quindi l'immagine scivola a sinistra. Con un movimento la foto riempie
sempre lo schermo (altrimenti si muoverebbero anche le bande), quindi `fit` non vale.
Costa: un `pan` riscala la foto una volta sola e poi ritaglia (gratis), uno `zoom` la
riscala a ogni fotogramma (circa 3 volte più lento).

---

## Installazione

**1. FFmpeg** (obbligatorio, non è una libreria Python):

```bash
brew install ffmpeg              # macOS
winget install Gyan.FFmpeg       # Windows
sudo apt install ffmpeg          # Ubuntu/Debian
```

Dopo l'installazione apri un terminale nuovo, e `ffmpeg -version` deve rispondere.

**2. Python 3.10+**, dalla cartella del repo (quella con `pyproject.toml`).

macOS e Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # installa vedit, pytest e ruff
vedit templates                  # se risponde, funziona
```

Windows (PowerShell), un comando per riga:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
vedit templates
```

Su Windows `python` spesso apre il Microsoft Store invece di Python: è un collegamento
di sistema ("alias di esecuzione dell'app") che intercetta il comando. `py`, il
launcher installato insieme a Python, lo evita; dentro l'ambiente attivato `python`
torna a funzionare. Se `Activate.ps1` dice che l'esecuzione di script è disabilitata,
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` la permette per quella
finestra sola. L'ambiente va riattivato in ogni terminale nuovo.

`-e` (*editable*) collega il progetto alla cartella invece di copiarlo: le modifiche
al codice sono attive subito. `python -m vedit ...` funziona anche senza installare.

## Struttura del repo

```
vedit/
  models.py        Schema del timeline.yaml e parsing. Nessuna dipendenza da MoviePy.
  timeline.py      Dove inizia e finisce ogni segmento. Matematica pura.
  templates.py     I template: slot, stile, lettura del YAML, applicazione ai media.
  edit.py          Gli edit: media nei posti, testi con i tempi risolti sui posti.
  extract.py       Da un video a un template: battiti, tagli, stile, allineamento.
  beats.py         Tempo e battiti di una traccia audio (ffmpeg + numpy).
  scenes.py        Tagli, video o foto, bande: l'analisi dei fotogrammi.
  transitions.py   Registry delle transizioni.
  motion.py        Registry dei movimenti sulle foto (Ken Burns).
  text.py          Il testo disegnato con Pillow.
  fonts.py         Trova un font utilizzabile e manda a capo il testo.
  sheet.py         Il foglio dei provini.
  report.py        Il riepilogo di --check.
  builder.py       Traduce il progetto in clip MoviePy: qui vive il montaggio.
  progress.py      La barra di avanzamento dell'export.
  ffmpeg_tools.py  ffprobe per i metadati.
  cli.py           Interfaccia da riga di comando.
templates/         I template: un template.yaml e la sua traccia, per cartella.
edits/             Un edit per video: l'edit.yaml si versiona, media/ e output/ no.
.claude/skills/    Le procedure per l'assistente: templetizza, monta.
docs/GLOSSARIO.md  I termini di montaggio, spiegati per chi viene dalla programmazione.
tests/             Test rapidi che non richiedono file video nel repo.
```

La separazione fra moduli leggeri e builder è deliberata: tutto quello che si può
calcolare senza MoviePy (validazione, tempi, riepiloghi, analisi) si testa in
millisecondi, e `--check` risponde subito.

## Test e qualità

```bash
pytest -q          # i test
ruff check .       # il lint
```

I test usano segmenti `color` e immagini generate in memoria: **nessun file video nel
repo**. Quelli che hanno bisogno di un sorgente vero (battiti, tagli, estrazione,
provini, GIF) se lo generano con ffmpeg in una cartella temporanea, e si saltano da
soli se ffmpeg non c'è. `tests/test_confini.py` verifica che i moduli leggeri non si
tirino dietro MoviePy: è il confine architetturale reso eseguibile.

Su ogni push una GitHub Action installa ffmpeg, lancia lint e test su Python 3.10 e
3.12, poi fa il giro completo su materiale sintetico: estrae un template, lo applica,
crea un edit con un testo e una GIF, renderizza e controlla nei pixel che i tagli
cadano sugli istanti e che il testo si veda. Un export può uscire con codice 0 e
produrre un video sbagliato: la CI lo verifica come lo verificheresti tu.

## Riferimenti

- [`docs/GLOSSARIO.md`](docs/GLOSSARIO.md) — i termini di montaggio usati qui
- [`templates/README.md`](templates/README.md) — i template del repo e come riempirli
- [Documentazione MoviePy 2.x](https://zulko.github.io/moviepy/)
- [Filtri FFmpeg](https://ffmpeg.org/ffmpeg-filters.html)
