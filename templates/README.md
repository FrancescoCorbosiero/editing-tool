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
