# templates/

I **template audio**: montaggi riutilizzabili, senza i media.

Ogni template è una cartella con due file:

```
templates/riferimento/
├── template.yaml     la struttura: istanti dei tagli, transizioni, formato
└── audio.m4a         la traccia su cui quegli istanti sono stati misurati
```

```bash
python -m vedit templates                                  # quali ho
python -m vedit apply templates/riferimento foto/ --preview # usane uno
python -m vedit extract un-video-che-mi-piace.mp4          # fanne un altro
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
l'ha fatta — vale come per qualsiasi campione musicale.

Il modo pulito per un template che vuoi distribuire è rifare l'estrazione da un
video con musica tua o libera: la struttura (gli istanti, le transizioni, i
movimenti) è farina del tuo sacco, ed è la parte che conta.

---

## `riferimento`

Il primo template del repo, estratto da un montaggio di materiale d'archivio a tempo
di musica: un'apertura lunga di quattro secondi e poi diciassette stacchi rapidi,
quasi tutti di un battito o mezzo.

| | |
|---|---|
| durata | 12.75s |
| tempo | 118.4 BPM |
| slot | 18 |
| formato | 1152×576 @ 30 fps |
| transizioni | stacchi netti |

Serve materiale **dinamico**: con diciotto posti e una media di sette decimi l'uno,
i primi quattro secondi reggono un'inquadratura sola e tutto il resto sono lampi. Su
un formato diverso da 2:1 conviene applicarlo con `--size`:

```bash
python -m vedit apply templates/riferimento media/ --size 1080x1920 --preview
```

---

## `panzerknacker`

L'opposto del precedente: un video divulgativo con voce fuori campo, dieci
inquadrature lunghe quasi due secondi l'una.

| | |
|---|---|
| durata | 19.20s |
| tempo | 119.5 BPM (ma vedi sotto) |
| slot | 10 |
| formato | 1280×720 @ 30 fps |
| transizioni | stacchi netti |

Estratto con **`--grid off`**, cioe' senza riallineare i tagli al battito, ed e' una
decisione che vale la pena spiegare perche' e' il caso in cui la regola generale non
si applica. Il BPM viene rilevato, ma solo quattro tagli su nove ci cadono sopra: qui
il montaggio non segue la musica, segue **il discorso**. Quei tagli appartengono a
quella voce, e spostarli sulla griglia li avrebbe staccati da cio' che li motiva.

La regola che se ne ricava: prima di estrarre, `vedit beats` sul riferimento. Se
avvisa che i colpi sono fuori griglia, il video probabilmente e' parlato, e la
griglia va spenta.

**Quello che questo template NON si porta dietro** sono le scritte a schermo, che nel
video originale sono meta' del suo carattere. Riempirne gli slot da' il ritmo e la
voce, non i cartelli: quelli si aggiungono a mano come `overlays` nel progetto
generato con `--to-yaml`.
