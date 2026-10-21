# templates/

I **template audio**: montaggi riutilizzabili, senza i media.

Ogni template è una cartella con due file:

```
templates/raffica/
├── template.yaml     la struttura: istanti dei tagli, stile, formato, stile dei testi
└── audio.m4a         la traccia su cui quegli istanti sono stati misurati
```

```bash
vedit templates                                          # quali ho
vedit new edits/mio-video --template templates/raffica   # un video nuovo su un template
vedit extract un-video-che-mi-piace.mp4 -o templates/x   # un template nuovo
```

## Perché qui i media si versionano

Il resto del repo esclude i media da git, e per un buon motivo: sono pesanti e
cambiano in continuazione. La traccia di un template è l'eccezione, e lo è **per
costruzione**: gli istanti dei tagli sono i battiti di quella musica, e senza di lei
sono numeri a caso. La traccia non è un allegato del template, è metà del template.
Pesa quanto una canzone tagliata a quindici secondi.

## Sui diritti

Un template estratto da un video di qualcun altro si porta dietro la sua musica.
Per lavorare va benissimo; se il risultato lo pubblichi, la traccia resta di chi
l'ha fatta — vale come per qualsiasi campione musicale. Sui social di solito il
modo pulito è montare il video senza musica e aggiungere lo stesso suono dalla
libreria della piattaforma, che ha le licenze.

---

## `raffica`

Estratto da un montaggio divulgativo su TikTok: screenshot di articoli scientifici,
grafici e diagrammi che si susseguono **a ogni battito**, su una base a 151,5 BPM.

| | |
|---|---|
| durata | 18,13s |
| tempo | 151,5 BPM (un battito ogni 0,396s) |
| posti | 28 |
| formato | 720×1280 (verticale) @ 30 fps |
| stile | media interi su nero (`contain`), si spegne nel nero negli ultimi 1,97s |
| transizioni | stacchi netti |

La struttura, che è il motivo per cui funziona:

| posti | cosa succede | nel riferimento |
|---|---|---|
| 1 (`apertura`) | 4 secondi su un'immagine sola, mentre la musica parte | un video (un'animazione 3D) |
| 2–20 | la raffica: un'immagine per battito, qualche mezzo battito | screenshot e grafici |
| 21 (`pausa`) | due secondi fermi: la musica respira, lo spettatore legge | un titolo di PubMed |
| 22–27 | di nuovo la raffica | screenshot |
| 28 (`chiusura`) | l'ultima immagine si spegne nel nero | una pagina di testo |

Per riempirlo bene:

- nell'**apertura** va un video, o un'immagine che regga quattro secondi: è il posto
  in cui si decide se lo spettatore resta;
- nella **raffica** vanno immagini che si capiscono in un colpo d'occhio: in 0,4
  secondi non si legge, si riconosce. Testi lunghi qui sono texture, e va bene così;
- la **pausa** è il posto per l'immagine che deve essere letta davvero, o per un testo;
- i media entrano interi, con le bande nere: uno screenshot orizzontale resta
  leggibile da bordo a bordo invece di essere tagliato.
