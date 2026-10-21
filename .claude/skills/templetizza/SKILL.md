---
name: templetizza
description: Trasforma un video di riferimento caricato dall'utente in un template vedit (la musica, i tagli a tempo, lo stile) dentro templates/. Usala quando l'utente carica un video e chiede di "templetizzarlo", di farne un template, di "usare questo suono" o di rifare un montaggio come quello.
---

# Templetizzare un video

L'utente non conosce i programmi di montaggio: il lavoro lo fai tu, e alla fine
gli dici in parole semplici cosa hai capito del video e cosa gli serve per
riempirlo. Lancia i comandi dalla radice del repo.

## 1. Metti il video in un posto di lavoro

I video caricati arrivano in una cartella di upload (il percorso è nel messaggio).
Copialo in una cartella temporanea tua, **mai dentro il repo**: i media non si
versionano. Scegli il nome del template: breve, minuscolo, con i trattini
(es. `raffica`, `zoom-lento`). Se l'utente non lo dice, proponine uno che descriva
lo stile, non il contenuto.

## 2. Guardalo prima di estrarre

```bash
vedit sheet <video> --shots -o <tmp>/riferimento.png   # un fotogramma per inquadratura
vedit beats <video>                                    # tempo e aderenza alla griglia
```

Apri l'immagine dei provini e guardala davvero. Chiediti:

- le immagini sono **intere su uno sfondo** (bande sopra e sotto) o **a tutto schermo**?
- ci sono **testi sovrimpressi**? Che aspetto hanno (colore, contorno, riquadro)?
- il video **si apre o si chiude nel nero**?
- quali inquadrature sono **video** e quali **foto ferme**?

Se `vedit beats` dice che i colpi cadono fuori griglia, il montaggio probabilmente
segue una voce e non la musica: estrai con `--grid off`.

## 3. Estrai

```bash
vedit extract <video> -o templates/<nome> --name <nome>
```

Leggi l'output: la riga `Stile` (fit, dissolvenze), il numero di posti, la colonna
`nel riferimento` (video/image). Se vuoi vedere i tagli trovati: `vedit shots <video>`.

## 4. Correggi a mano quello che serve

Apri `templates/<nome>/template.yaml` e confrontalo con quello che hai visto:

- `style.fit`: `contain` se le immagini erano intere con le bande, `cover` se a
  tutto schermo. `style.fade_in`/`fade_out` se il video si apre/chiude nel nero;
- `text`: se il riferimento ha testi, rifanne l'aspetto (`font_size`, `color`,
  `stroke_color`, `bg_color`...). Se non ne ha, lascia lo stile di partenza;
- `label` sui posti che contano (`apertura`, `pausa`, `chiusura`...): servono a
  parlarne con l'utente e compaiono nei riepiloghi;
- un taglio mancato o di troppo: aggiungi o togli uno slot, spostando solo gli `at`.

## 5. Verifica che i tagli cadano sugli istanti

Riempi il template con una tinta diversa per posto e controlla i fotogrammi prima e
dopo ogni `at` (il metodo è in CLAUDE.md, "Verifica del risultato di un render"):

```bash
python - <<'PY'
from pathlib import Path
from PIL import Image
import colorsys, yaml
n = len(yaml.safe_load(open("templates/<nome>/template.yaml"))["slots"])
Path("<tmp>/tinte").mkdir(parents=True, exist_ok=True)
for i in range(n):
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb((i * 0.37) % 1, 0.9, 1 if i % 2 == 0 else 0.55))
    Image.new("RGB", (720, 900), (r, g, b)).save(f"<tmp>/tinte/{i:02d}.png")
PY
vedit apply templates/<nome> <tmp>/tinte -o <tmp>/tinte.mp4
```

Poi lo snippet di CLAUDE.md sugli `at`. Ogni taglio deve risultare; con una
dissolvenza finale, la luce deve scendere fino al nero.

## 6. Salva e racconta

- aggiungi una sezione al `templates/README.md`: numeri, struttura (quali posti
  fanno cosa), consigli per riempirlo;
- fai il commit di `template.yaml` e della traccia audio (`.gitignore` li lascia
  passare apposta) e di nient'altro;
- di' all'utente, in poche righe: quanti posti, il tempo, lo stile, quali posti
  chiedono un video e quali un'immagine, e che adesso può mandarti media e testi
  (è il lavoro della skill `monta`).
