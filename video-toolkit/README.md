# vedit — montaggio video da codice

Toolkit per montare video scrivendo un file YAML invece di trascinare clip in una GUI.
Costruito su **MoviePy 2.x** (composizione) e **FFmpeg** (operazioni veloci).

Due modi di usarlo, e il secondo è quello che fa risparmiare le ore.

**1. Scrivere il montaggio.** Un file YAML descrive la timeline, `vedit` la esporta:

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

**2. Riusare un montaggio che funziona.** Da un video che ti piace si estrae un
**template audio**: la musica, il tempo, gli istanti dei tagli, il formato. I media
restano fuori — quelli li porti tu, ogni volta diversi.

```bash
python -m vedit extract riferimento.mp4          # -> templates/riferimento/
python -m vedit apply templates/riferimento le-mie-foto/ --preview
```

È lo stesso gesto di quando su CapCut riusi un "suono": non stai prendendo in
prestito una canzone, stai prendendo in prestito un montaggio che su quella canzone
funziona. La differenza è che qui il montaggio è un file di testo che puoi leggere,
correggere e versionare.

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
pip install -e ".[dev]"          # installa vedit + pytest e ruff
```

`-e` (*editable*) installa il progetto **collegandolo** alla cartella invece di
copiarlo: le modifiche al codice sono attive subito, senza reinstallare. `[dev]`
aggiunge gli strumenti di sviluppo; senza, ottieni solo quello che serve per
renderizzare. In alternativa `pip install -r requirements.txt` installa le sole
dipendenze, ma non ti dà il comando `vedit`.

**3. Prova**:

```bash
vedit render projects/demo/timeline.yaml --dry-run
```

Dopo `pip install -e .` il comando si chiama **`vedit`**. Se preferisci non
installare niente, `python -m vedit ...` funziona lo stesso da dentro questa
cartella: in questo README i due sono intercambiabili.

Il `--dry-run` costruisce la timeline e valida il file senza esportare nulla: è il modo
più rapido per scoprire un errore di configurazione.

---

## Uso

```bash
# Metadati di un file (durata, risoluzione, fps, codec)
python -m vedit probe assets/riprese.mp4

# Font utilizzabili per testo e sottotitoli su questa macchina
python -m vedit fonts

# Tempo e battiti di una traccia, per montare a tempo di musica
python -m vedit beats assets/musica.mp3

# Dove stacca un video: i tagli che il rilevatore riconosce
python -m vedit shots riferimento.mp4

# Estrae un template audio da un video che ti piace
python -m vedit extract riferimento.mp4

# I template che hai in casa
python -m vedit templates

# Applica un template ai tuoi media e monta
python -m vedit apply templates/riferimento foto1.jpg riprese.mp4 --preview

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

## Template audio

Un video di riferimento contiene due cose separabili. Da una parte **i media**: le
riprese, le foto, quello che si vede. Dall'altra la **struttura**: la musica, il
tempo, gli istanti in cui si stacca, le transizioni, il formato. La prima parte è
irripetibile — sono i tuoi filmati — la seconda no: quella è una ricetta, e si
applica a materiale completamente diverso.

Un template è quella seconda parte.

### Perché "audio"

Perché la traccia non è un accessorio, è la struttura portante. Gli istanti dei
tagli sono i battiti **di quella musica**: staccarli da lei li renderebbe numeri a
caso. Per questo il file audio vive dentro il template, ed è l'unico media che un
template si porta dietro.

Due conseguenze pratiche: un template dura quanto la sua traccia, e ha un numero
fisso di posti da riempire.

### Il giro completo

```bash
# 1. Guarda cosa ha capito il rilevatore, prima di costruirci sopra
python -m vedit shots riferimento.mp4

# 2. Estrai il template: traccia audio, BPM, istanti dei tagli, formato
python -m vedit extract riferimento.mp4 -o templates/il-mio-stile

# 3. Applicalo ai tuoi file
python -m vedit apply templates/il-mio-stile foto1.jpg gita.mp4@12 --preview

# 4. Se ti serve toccare qualcosa a mano, esci in un progetto normale
python -m vedit apply templates/il-mio-stile media/ --to-yaml progetti/vacanza.yaml
python -m vedit render progetti/vacanza.yaml --preview
```

Il passo 4 è la valvola di sfogo che tiene onesto tutto il resto: un template
**genera un `timeline.yaml`**, non è un secondo motore di montaggio. Quello che
produce è esattamente ciò che avresti potuto scrivere a mano, e da lì in poi vale
tutto quello che sai già.

### Cosa succede durante l'estrazione

```
$ python -m vedit extract riferimento.mp4
Template : riferimento  ->  templates/riferimento
Traccia  : audio.m4a  (12.75s)
Tempo    : 118.4 BPM  (un battito ogni 0.507s, il primo a 0.170s)
Formato  : 1152x576 @ 30 fps
Slot     : 18  (il più corto 0.27s, il più lungo 4.22s)
Griglia  : half - 9 tagli riallineati al battito, in media di 19 ms
Scartati : 2 tagli troppo ravvicinati per essere slot

  #   entra a   dura   battiti  transizione  movimento
  0      0.00   4.22s     8.34  cut          pan_left
  1      4.22   0.51s     1.00  cut          -
  2      4.73   0.51s     1.00  cut          -
  ...
```

Tre analisi diverse messe d'accordo:

| passo | modulo | domanda |
|---|---|---|
| battito | `beats.py` | in quali istanti cade la cassa? |
| tagli | `scenes.py` | in quali istanti cambia l'inquadratura? |
| allineamento | `extract.py` | quali tagli erano sul battito, e quanto ci sono andati vicini? |

**L'allineamento è il passaggio che rende un template riusabile.** I tagli misurati
non cadono mai esattamente sul battito, nemmeno in un montaggio fatto benissimo: a
30 fps un fotogramma dura 33 ms, e chi ha montato aveva la sua mano. Scrivere nel
template i tagli grezzi significherebbe portarsi dietro quelle imprecisioni per
sempre. Avvicinarli al battito più vicino dà una griglia pulita.

Il riallineamento è **prudente**: sposta un taglio solo se era già vicino (entro un
quarto di suddivisione). Un taglio a metà strada fra due battiti non è sbagliato, è
in levare — una scelta — e resta dov'è. Con `--grid` decidi la finezza della
griglia:

| `--grid` | allinea a | quando |
|---|---|---|
| `beat` | i battiti | montaggi lenti, un'immagine per battito |
| `half` (default) | anche i mezzi battiti | il caso normale: molti stacchi in levare |
| `quarter` | anche i quarti | montaggi fittissimi |
| `off` | niente | quando il rilevamento ti convince già così |

### Come i media finiscono negli slot

In ordine. Il primo file nel primo slot, e via così.

```bash
# Una cartella si espande nei file che contiene, in ordine alfabetico
python -m vedit apply templates/riferimento foto/

# `@secondi` sceglie da dove prendere una ripresa lunga
python -m vedit apply templates/riferimento intro.jpg gita.mp4@45 tramonto.mp4@3
```

Il numero di slot lo decide la musica, e quasi mai coincide con quanti file hai:

- **meno media che slot** → si ricomincia da capo, e `vedit` te lo dice. È quello
  che fa chiunque monti un video da tre riprese su una canzone che ne chiederebbe
  dodici, e produce comunque un montaggio guardabile.
- **più media che slot** → gli ultimi restano fuori.
- `--strict` trasforma entrambi in un errore, quando vuoi il numero esatto.

**Un video più corto del suo slot viene rallentato** per arrivare in fondo, e
`vedit` scrive di quanto. Il motivo è che il taglio successivo cade sul battito, e
quel battito non si sposta per fare spazio a un video corto. Sotto `0.25x` il
rallentatore diventa un fermo immagine, e allora è un errore.

### Cambiare formato mentre applichi

Il template ricorda il formato del riferimento, ma non te lo impone:

```bash
python -m vedit apply templates/riferimento media/ --size 1080x1920   # verticale
python -m vedit apply templates/riferimento media/ --fps 60
```

### L'audio dei tuoi video

Per impostazione predefinita **viene tolto**: la traccia del template è la traccia
del montaggio, ed è il senso di un template audio. Con `--keep-audio` le due si
sommano — serve quando nei tuoi video c'è qualcosa da sentire — e allora quasi
sempre conviene abbassare la musica con `--volume 0.4`.

### Lo schema di `template.yaml`

| campo | | significato |
|---|---|---|
| `name` | | nome del template |
| `duration` | | quanto dura il montaggio completo, cioè la traccia |
| `audio.src` | | il file audio, dentro la cartella del template |
| `audio.bpm` | | il tempo misurato, `0` se non riconosciuto |
| `audio.offset` | | dove cade il primo battito |
| `audio.volume`, `audio.fade_out` | | livello e dissolvenza in chiusura |
| `format.size`, `format.fps` | | canvas del riferimento, sovrascrivibile con `--size`/`--fps` |
| `slots[].at` | obbligatorio | istante in cui lo slot entra in scena |
| `slots[].transition` | | durata della transizione in entrata |
| `slots[].transition_type` | | `cut` (default) \| `crossfade` \| `fade_through_black` \| `slide` \| `wipe` |
| `slots[].motion` | | movimento se in quello slot finisce una **foto** |
| `slots[].amount` | | quanto movimento, in frazione |
| `slots[].fit` | | `cover` (default) \| `contain` \| `stretch` |
| `slots[].label` | | un nome per quel posto ("il ritornello") |

**Uno slot non ha una durata.** Finisce quando comincia il successivo, e l'ultimo
finisce con la traccia. Scriverla in due posti significherebbe poterla scrivere in
due modi diversi — e allora quale delle due comanda? Le durate le vedi calcolate
nei commenti che `extract` scrive accanto a ogni slot, e in `apply --check`.

### Il template si corregge a mano

È un file di testo, ed è pensato per essere aperto. Le cose che vale la pena
cambiare, in ordine di frequenza:

- **spostare un `at`**: sposta *quel* taglio e basta, nessun altro si muove;
- **togliere un `motion`** che non ti convince su una foto;
- **aggiungere una transizione**: `transition: 0.3` + `transition_type: crossfade`;
- **dare un `label` agli slot** che riconosci ("apertura", "ritornello").

### Limiti, onestamente

Il rilevatore trova i **tagli netti**, che sono la stragrande maggioranza. Una
dissolvenza lenta non produce nessun picco e viene ignorata; un flash o
un'esplosione possono valere un falso taglio. Il rilevamento del tempo funziona su
materiale con una cassa marcata e un tempo stabile — elettronica, pop, hip hop — e
sbaglia su registrazioni dal vivo e brani acustici.

Per questo `vedit shots` e `vedit beats` esistono come comandi a sé: si guarda cosa
ha capito la macchina **prima** di costruirci sopra, e si regola `--sensitivity`.

La traccia audio di un template resta di chi l'ha fatta: estrarla è comodo per
lavorare, pubblicare è un altro discorso.

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
  beats.py         Tempo e battiti di una traccia audio (ffmpeg + numpy).
  scenes.py        Dove stacca un video: i tagli, per istogrammi (ffmpeg + numpy).
  templates.py     Template audio: slot, lettura del YAML, applicazione ai media.
  extract.py       Da un video di riferimento a un template: mette d'accordo battiti e tagli.
  subtitles.py     Lettura dei file .srt. Solo testo, nessuna dipendenza.
  fonts.py         Trova un font utilizzabile e manda a capo il testo.
  proxies.py       Copie leggere dei sorgenti, con cache per impronta del file.
  report.py        Il riepilogo di --check. Legge i metadati con ffprobe.
  builder.py       Traduce il progetto in clip MoviePy. È qui che vive la logica di montaggio.
  progress.py      La barra di avanzamento dell'export.
  ffmpeg_tools.py  Chiamate dirette a ffmpeg/ffprobe per le operazioni veloci.
  cli.py           Interfaccia da riga di comando.
templates/         I template audio: un template.yaml e la sua traccia, per cartella.
projects/demo/     Progetto di esempio, documentato campo per campo.
examples/          Script didattici progressivi (leggili in ordine).
docs/GLOSSARIO.md  I termini di montaggio, spiegati per programmatori.
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
| `at` | tutti | istante sul **montaggio** in cui il segmento entra in scena (vedi sotto) |
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

## Due modi di scrivere un montaggio: durate o istanti

Il modo predefinito è **a durate**: ogni segmento dice quanto dura, e la sua
posizione è la somma di quelli prima.

```yaml
timeline:
  - type: video
    src: assets/a.mp4
    start: 4
    end: 6          # dura 2s, quindi il prossimo comincia a 2s
```

Funziona benissimo per un racconto. Per la musica è pessimo, e il motivo è uno solo:
**allungare uno spezzone sposta tutti i tagli successivi.** Se avevi dieci stacchi a
tempo e allunghi il terzo di un decimo di secondo, gli altri sette vanno fuori tempo
tutti insieme.

L'alternativa è **a istanti**: ogni segmento dichiara `at`, il momento in cui entra
in scena. Le durate non si scrivono — un segmento finisce quando comincia il successivo.

```yaml
timeline:
  - at: 0.00          # il primo deve sempre partire da 0
    type: video
    src: assets/a.mp4
    start: 1.20       # attenzione: `start` è nel SORGENTE, `at` nel MONTAGGIO
    label: apertura

  - at: 2.028
    type: video
    src: assets/a.mp4
    start: 6.36
    label: stacco

  - at: 2.535         # l'ultimo è l'unico che deve dire dove finisce
    type: video
    src: assets/a.mp4
    start: 11.60
    end: 12.61
    label: chiusura
```

Adesso spostare un taglio è **cambiare un numero**, e si muove solo quel taglio.
La colonna degli `at` diventa il ritmo del montaggio, leggibile a colpo d'occhio:
passi regolari sono un ritmo costante, passi che si dimezzano sono un'accelerazione.

I due orologi da non confondere:

| campo | in quale tempo |
|---|---|
| `at` | il **montaggio finale** — quando lo spettatore vede il cambio |
| `start` / `end` | il **file sorgente** — da dove si prende il materiale |

Le regole, poche e verificate da `--check`:

- o li hanno **tutti** i segmenti, o nessuno: mezzo montaggio a istanti e mezzo a
  durate sarebbe illeggibile;
- il primo `at` è `0`, e gli istanti crescono;
- l'ultimo segmento dichiara `end` o `duration`, perché non ha un taglio dopo di sé
  che lo chiuda;
- una transizione non può durare più dello spazio fra i due istanti che collega: si
  dissolve **da** qualcosa, e quel qualcosa deve essere già in scena.

### Le dissolvenze non spostano gli istanti

Una dissolvenza incrociata ha bisogno che il clip che entra cominci **prima** della
fine del precedente, altrimenti non ha niente su cui dissolvere. Sembra
incompatibile con `at`, che promette di non spostare niente. La conciliazione sta
nel decidere cosa fissa l'istante:

> `at` è il momento in cui il segmento **ha finito di entrare**.

Il clip parte `transition` secondi prima e a `at` è completamente in scena. Il
taglio resta dov'era — sul battito, se ce l'avevi messo — e la sovrapposizione se la
mangia la coda del segmento precedente, che sotto continua a vedersi.

```yaml
timeline:
  - {type: video, src: a.mp4, at: 0.0, start: 0}
  - {type: video, src: b.mp4, at: 2.0, start: 0, transition: 0.4,
     transition_type: crossfade}
  - {type: video, src: c.mp4, at: 4.0, start: 0, end: 2.4, transition: 0.4,
     transition_type: crossfade}
```

Il secondo segmento entra a `1.6`, è pieno a `2.0`, e occupa fino a `4.0`: di
sorgente ne consuma `2.4` secondi invece di `2`. È la differenza pratica fra i due
modi — **a durate** ogni sovrapposizione anticipa tutto quello che viene dopo, e i
tagli che erano sul battito non ci sono più; **a istanti** restano dove li hai
messi.

Un dettaglio dell'ultimo segmento, che non ha un taglio dopo di sé: quello che
dichiara (`end - start`, oppure `duration`) è quanto **mostra**, e la dissolvenza in
entrata se ne mangia una parte. Nell'esempio sopra `c.mp4` mostra 2.4 secondi, 0.4
dei quali passano a entrare: il montaggio finisce a `6.0`.

### Montare a tempo di musica

`vedit beats` dà il tempo del brano; da lì gli `at` sono aritmetica:

```bash
$ vedit beats assets/musica.m4a
Tempo    : 118.4 BPM   (un battito ogni 0.507s)
```

Un battito `0.507`, mezzo `0.253`, quattro `2.028`. Scrivi gli istanti su quei
multipli e i cambi di scena cadono sulla cassa. Ma restano numeri normali: se un
taglio ti piace un pelo più tardi, scrivi il numero che vuoi. La griglia è un
suggerimento, non un vincolo — nel clip che abbiamo analizzato per costruire questa
funzione, il montatore umano stava fra 1,5 e 3 fotogrammi dal battito, e funzionava.

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

## Test e qualità

```bash
pytest -q          # i test
ruff check .       # il lint
```

I test coprono parsing, validazione, matematica delle transizioni, movimento,
sottotitoli e stile del testo usando segmenti `color` e immagini generate in
memoria: **nessun file video nel repo**. I pochi test che hanno bisogno di un
sorgente vero (i proxy) se lo generano con ffmpeg in una cartella temporanea, e
si saltano da soli se ffmpeg non c'è.

Un test merita una nota: `tests/test_confini.py` importa i moduli "leggeri" in un
interprete separato e verifica che **non** si siano tirati dietro MoviePy. È il
confine architetturale del progetto reso eseguibile — senza, prima o poi qualcuno
aggiunge un `import` in cima al file sbagliato e `--check` inizia a costarci
secondi invece di millisecondi.

`ruff check` deve passare. `ruff format` è configurato ma **non** obbligatorio:
i commenti allineati in colonna sui campi delle dataclass si leggono come una
tabella, e il formatter li schiaccerebbe. Il perché è scritto nel `pyproject.toml`.

Su ogni push, una GitHub Action (`.github/workflows/ci.yml`) installa ffmpeg,
lancia lint e test su Python 3.10 e 3.12, genera il materiale di prova con ffmpeg
e renderizza davvero il progetto demo, controllando durata, dimensioni e che i
fotogrammi non siano neri. Un export può uscire con codice 0 e produrre un video
sbagliato: la CI lo verifica come lo verificheresti tu.

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

- [`docs/GLOSSARIO.md`](docs/GLOSSARIO.md) — i termini di montaggio usati qui,
  spiegati per chi viene dalla programmazione
- [Documentazione MoviePy 2.x](https://zulko.github.io/moviepy/)
- [Guida alla migrazione 1.x → 2.x](https://zulko.github.io/moviepy/getting_started/updating_to_v2.html)
- [Filtri FFmpeg](https://ffmpeg.org/ffmpeg-filters.html)
