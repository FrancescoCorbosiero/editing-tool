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

Controlla che non manchino battiti: confronta il numero di posti con i tagli che
vede un rilevatore piu' fine, `vedit shots <video> --min-shot 0.1`. Gli stacchi
rapidi da mezzo battito restano posti da soli; se ne trovi di ancora piu' brevi e
nei provini si vede che sono voluti (non un flash o un glitch), riestrai con
`--min-slot 0.1 --force`. I tagli finti dentro una dissolvenza finale si scartano
da soli.

## 4. Correggi a mano quello che serve

Apri `templates/<nome>/template.yaml` e confrontalo con quello che hai visto:

- `style.fit`: `contain` se le immagini erano intere con le bande, `cover` se a
  tutto schermo. `style.fade_in`/`fade_out` se il video si apre/chiude nel nero;
- `text`: se il riferimento ha testi, rifanne l'aspetto (`font_size`, `color`,
  `stroke_color`, `bg_color`...). Se non ne ha, lascia lo stile di partenza;
- `label` sui posti che contano (`apertura`, `pausa`, `chiusura`...): servono a
  parlarne con l'utente e compaiono nei riepiloghi;
- un taglio mancato o di troppo: non riscrivere gli `at` a mano, usa `vedit slots`
  (`--cut 4.45` aggiunge un taglio sulla griglia del battito, `--split 4` divide un
  posto in parti uguali, `--merge 5` toglie il taglio fra il 4 e il 5). I numeri sono
  quelli dell'elenco di `vedit slots templates/<nome>`, e il comando stampa come
  tornare indietro.

## 5. Verifica che i tagli cadano sugli istanti

Monta il template con una tinta diversa per posto, il suo numero sopra, sulla sua
musica:

```bash
vedit slots templates/<nome> --video        # scrive output/<nome>-posti.mp4
```

Poi controlla i fotogrammi prima e dopo ogni `at` di quel video con lo snippet di
CLAUDE.md ("Verifica del risultato di un render"). Ogni taglio deve risultare; con una
dissolvenza finale, la luce deve scendere fino al nero. Guarda anche i provini:
`vedit sheet output/<nome>-posti.mp4 --slots templates/<nome>`.

## 6. Salva e racconta

- aggiungi una sezione al `templates/README.md`: numeri, struttura (quali posti
  fanno cosa), consigli per riempirlo;
- fai il commit di `template.yaml` e della traccia audio (`.gitignore` li lascia
  passare apposta) e di nient'altro;
- mandagli il video dei posti numerati (`output/<nome>-posti.mp4`): lo guarda con
  la musica e ti dice se manca un taglio, chiamandolo per numero o per secondo;
- di' all'utente, in poche righe: quanti posti, il tempo, lo stile, quali posti
  chiedono un video e quali un'immagine, e che adesso può mandarti media e testi
  (è il lavoro della skill `monta`).

## Quando l'utente sente un battito che manca

Succede, e non è un tuo errore: il template copia il riferimento, e il riferimento
può non tagliare su un colpo che l'utente sente ("al drop sono quattro colpi e cambia
tre volte"). Il suo orecchio vince sul riferimento.

1. Trova i posti di quel momento: `vedit slots templates/<nome>` (entra a, dura,
   battiti). Se serve sapere dove cadono i colpi, li elenca
   `vedit beats templates/<nome>/audio.m4a --json` (la lista `onsets`).
2. Correggi: `--cut <secondi>` per un colpo preciso, `--split N` (`--into K`) per
   "K colpi dentro il posto N", `--merge N` per un taglio di troppo.
3. Rifai il video dei posti (`--video`), verificalo come al passo 5 e mandalo
   all'utente: deve sentire i tagli dove li voleva.
4. `vedit slots` elenca gli edit che usano il template: in ognuno serve un media per
   ogni posto nuovo, e i `slot:` dei testi vanno spostati (il comando dice come sono
   cambiati i numeri). Aggiorna anche i numeri dei posti in `templates/README.md`.
