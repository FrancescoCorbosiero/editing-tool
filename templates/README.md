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
| posti | 32 |
| formato | 720×1280 (verticale) @ 30 fps |
| stile | media interi su nero (`contain`), si spegne nel nero negli ultimi 1,97s |
| transizioni | stacchi netti |

La struttura, che è il motivo per cui funziona:

| posti | cosa succede | nel riferimento |
|---|---|---|
| 1 (`apertura`) | quasi 4 secondi su un'immagine sola, mentre la musica parte | un video (un'animazione 3D) |
| 2–3 | due stacchi da mezzo battito: l'ingresso nella raffica | due grafici in un lampo |
| 4–24 | la raffica: un'immagine per battito, con due lampi da mezzo battito (posti 11 e 21) | screenshot e grafici |
| 25 (`pausa`) | due secondi fermi: la musica respira, lo spettatore legge | un titolo di PubMed |
| 26–31 | di nuovo la raffica | screenshot |
| 32 (`chiusura`) | l'ultima immagine si spegne nel nero | una pagina di testo |

Per riempirlo bene:

- nell'**apertura** va un video, o un'immagine che regga quattro secondi: è il posto
  in cui si decide se lo spettatore resta;
- nella **raffica** vanno immagini che si capiscono in un colpo d'occhio: in 0,4
  secondi non si legge, si riconosce. Testi lunghi qui sono texture, e va bene così;
- i **lampi** (posti 2–3, 11 e 21) durano un quinto di secondo: un'immagine qualsiasi
  dà lo scatto, la stessa del posto prima lo nasconde;
- la **pausa** è il posto per l'immagine che deve essere letta davvero, o per un testo;
- i media entrano interi, con le bande nere: uno screenshot orizzontale resta
  leggibile da bordo a bordo invece di essere tagliato.

---

## `jumpstyle`

Estratto da un montaggio su TikTok del genere "primati di un paese": riprese a tutto
schermo che cambiano **a ogni battito**, e ogni quattro battiti un titolo rosso con un
numero ("AFRICA'S MOST VISITED COUNTRY — 19.8M"), su un bootleg jumpstyle.

| | |
|---|---|
| durata | 28,33s |
| tempo | 111,2 BPM (un battito ogni 0,54s) |
| posti | 61 |
| formato | 1080×1080 (quadrato) @ 60 fps |
| stile | media a tutto schermo (`cover`), finisce con una dissolvenza rapida al nero |
| transizioni | stacchi netti |
| testi | rossi, maiuscoli, stretti e pesanti; il numero sotto in bianco |

La struttura è regolarissima: un'apertura di quattro battiti, poi **12 sezioni da
quattro battiti** (2,16s), una per primato, poi la chiusura. Le etichette dei posti
nel `template.yaml` segnano dove comincia ogni sezione.

| sezione | posti | da – a | |
|---|---|---|---|
| `apertura` | 1–3 | 0,00 – 2,28s | nel riferimento: un meme |
| 1 | 4–7 | 2,28 – 4,44s | |
| 2 | 8–13 | 4,44 – 6,59s | finisce con un collage (10–13) |
| 3 | 14–17 | 6,59 – 8,75s | |
| 4 | 18–23 | 8,75 – 10,91s | collage (20–23) |
| 5 | 24–27 | 10,91 – 13,07s | |
| 6 | 28–33 | 13,07 – 15,23s | collage (30–33) |
| 7 | 34–37 | 15,23 – 17,39s | |
| 8 | 38–44 | 17,39 – 19,54s | collage (41–44) |
| 9 | 45–48 | 19,54 – 21,70s | |
| 10 | 49–54 | 21,70 – 23,86s | collage (51–54) |
| 11 | 55–58 | 23,86 – 26,02s | |
| 12 | 59–60 | 26,02 – 27,23s | |
| `chiusura` | 61 | 27,23 – 28,33s | nel riferimento: la bandiera |

Per riempirlo bene:

- **quasi tutto video**: nel riferimento 29 dei 39 posti con un suggerimento erano
  riprese in movimento (droni, strade, treni). Ne basta mezzo secondo a posto;
- **un titolo e un numero per sezione**, sugli stessi posti. Titolo al 44% dell'altezza,
  numero al 56%: così non si toccano nemmeno quando il titolo va su due righe.

  ```yaml
  texts:
    - text: "AFRICA'S MOST VISITED COUNTRY"
      slot: 8-13
      position: 0.44
    - text: "19.8M"
      slot: 8-13
      position: 0.56
      color: white
      stroke_color: black
      stroke_width: 4
      font_size: 64
  ```

- i **collage** sono quattro posti rapidissimi (0,15–0,36s): quattro media diversi danno
  la raffica del riferimento, lo stesso media ripetuto la nasconde;
- il font dei titoli è **Impact** su Windows e Mac; dove non c'è (le sessioni cloud) si
  ripiega su un nero pesante più largo, e un titolo lungo va su due righe;
- a 60 fps l'export è lento: `fps: 30` nell'edit lo dimezza, e sui social non si nota.

Quello che il template **non** si porta dietro, perché sono effetti e non posti: il meme
fisso in primo piano nell'apertura (dietro, nel riferimento, cambiavano gli sfondi), la
tinta rossa con la stella verde, i pannelli dei collage che restano a schermo insieme,
e il lampeggio sul nero del finale (qui una dissolvenza rapida).
