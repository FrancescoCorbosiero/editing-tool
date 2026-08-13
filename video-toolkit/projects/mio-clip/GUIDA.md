# Guida al mio clip

Questa cartella è **tua**. Il progetto demo e gli esempi non la toccano, e lei non
tocca loro: puoi sbagliare quanto vuoi qui dentro senza rompere niente.

```
projects/mio-clip/
  timeline.yaml    il montaggio: cosa va in scena, quando, con che transizione
  assets/          i tuoi file (video, foto, musica) — ignorati da git
  output/          i render — ignorati da git
  GUIDA.md         questo file
```

## L'idea di fondo

`timeline.yaml` **non contiene video**: contiene la descrizione di un montaggio.
È una lista di pezzi in ordine. Il programma legge la lista, va a prendere i file
in `assets/`, e li assembla. Cambiare il montaggio significa cambiare il testo del
file — mai toccare i sorgenti, che restano intatti.

Conseguenza pratica: se sbagli, **hai sbagliato a scrivere**, non hai rovinato niente.

## I tre comandi

Lanciali sempre dalla cartella `video-toolkit/`.

```bash
# 1. CONTROLLA — non renderizza niente, risponde in un decimo di secondo
vedit render projects/mio-clip/timeline.yaml --check
```

Ti dice dove cade ogni pezzo, quanto dura il tutto, e cosa non gli torna. **Usalo
ogni volta che tocchi il file.** Se qui è sbagliato, è inutile aspettare un render.

```bash
# 2. ANTEPRIMA — mezza risoluzione, brutta, veloce
vedit render projects/mio-clip/timeline.yaml --preview
```

Esce `output/clip_preview.mp4`. È il file che guardi mentre monti: è una miniatura
fedele del risultato, con posizioni e testi in scala.

```bash
# 3. EXPORT — piena risoluzione, lento
vedit render projects/mio-clip/timeline.yaml
```

Esce `output/clip.mp4`. Fallo solo quando l'anteprima ti convince.

## Le cinque modifiche che farai più spesso

**Mettere la tua roba.** Copia i tuoi file in `assets/` con i nomi che il YAML si
aspetta (`foto1.jpg`, `ripresa.mp4`): non devi cambiare una riga. Se preferisci i
tuoi nomi, cambia il campo `src`.

**Cambiare quanto dura un pezzo.** Nel segmento, `duration: 4` → `duration: 6`.
Per i video invece si spostano `start` e `end`, che sono i secondi **dentro il file
sorgente**: `start: 12, end: 20` prende otto secondi a partire dal minuto 0:12.

**Cambiare una transizione.** `transition_type:` accetta `crossfade` (morbida,
invisibile), `cut` (stacco netto), `fade_through_black` (stacco di tempo), `slide` e
`wipe` (movimento, vogliono anche `direction`). `transition:` è la durata.

**Aggiungere un pezzo.** Copia un blocco della timeline, incollalo dove vuoi che
compaia, cambia `src` e `label`. L'ordine nella lista è l'ordine sullo schermo.

**Passare al verticale** (per i social): in `output`, `size: [1080, 1920]`. Tutto il
resto si adatta da solo — `fit: cover` ritaglia il materiale orizzontale.

## Quando qualcosa non funziona

Il programma non ti fa mai vedere un traceback: se qualcosa non va te lo dice in
italiano. I due errori del principiante:

- **«File non trovato»** — il percorso in `src` parte da questa cartella, non da
  dove hai lanciato il comando. `assets/foto1.jpg`, non `foto1.jpg`.
- **«transizione ridotta»** — non è un errore, è un avviso: una transizione non può
  durare più di metà del pezzo più corto che collega. Se vuoi una dissolvenza da 2
  secondi, i due pezzi devono durare almeno 4 secondi.

## Dove vive il codice, se ti viene voglia di guardarlo

| ti chiedi... | apri |
|---|---|
| quali campi accetta il YAML e come vengono controllati | `vedit/models.py` |
| come si calcola dove cade ogni pezzo | `vedit/timeline.py` |
| come nasce una transizione | `vedit/transitions.py` |
| come si muove una foto (Ken Burns) | `vedit/motion.py` |
| come tutto diventa un video | `vedit/builder.py` |

I termini di montaggio che non conosci sono in [`docs/GLOSSARIO.md`](../../docs/GLOSSARIO.md).
