---
name: monta
description: Monta un video su un template vedit con le immagini, i video, le GIF e i testi che manda l'utente, e glielo consegna. Usala quando l'utente manda dei file da mettere in un template, chiede di cambiare media o testi di un video gia' fatto, o chiede "fammi il video".
---

# Montare un video su un template

Il template decide **quando** si stacca (la musica, i tagli, lo stile); tu decidi
**cosa** si vede, seguendo quello che chiede l'utente. Lancia i comandi dalla
radice del repo.

## 1. Il template e l'edit

```bash
vedit templates                                          # quali ci sono
vedit new edits/<nome> --template templates/<template>   # se il video e' nuovo
```

Se c'è un solo template usa quello; se l'utente modifica un video già fatto, lavora
sul suo `edits/<nome>/edit.yaml` invece di crearne uno nuovo. `<nome>`: breve,
minuscolo, con i trattini.

## 2. I media

Copia i file caricati in `edits/<nome>/media/`, con nomi che conservino l'ordine
voluto (`01-apertura.mp4`, `02-grafico.png`...). Poi scrivili nella lista `media`
dell'`edit.yaml`: **uno per posto, in ordine**. Lo scheletro creato da `vedit new`
ha un commento per posto con quando entra, quanto dura e cosa c'era nel riferimento.

Come scegliere, se l'utente non lo dice:

- l'**ordine** dell'utente vince su tutto;
- i **video** nei posti `hint: video` e in quelli lunghi; da un video lungo scegli
  il pezzo migliore con `file.mp4@secondi` (guardalo con `vedit sheet file.mp4`);
- nei posti brevi (sotto il mezzo secondo) immagini che si capiscono al volo;
- le **GIF** vanno ovunque: se sono più corte del posto ripartono da capo;
- con meno media che posti i media si ripetono: avvisa l'utente, e chiedigli se
  vuole mandarne altri prima di consegnare.

Un media può cambiare le scelte del template per il suo posto:

```yaml
  - src: media/03-foto.jpg
    fit: cover            # a tutto schermo invece che intera
    motion: zoom_in       # un lento ingrandimento
```

## 3. I testi

Traduci le richieste dell'utente in voci della lista `texts`:

```yaml
texts:
  - text: "L'ormone della crescita"
    slot: 2-8             # QUANDO: un posto (3), un intervallo (2-8), oppure at: 4.2 (+ duration)
    position: top         # DOVE: top, center, bottom, un numero 0-1 (altezza) o [x, y]
  - text: "Funziona davvero?"
    slot: 25
    bg_color: black       # stile: solo se serve cambiare quello del template
    bg_opacity: 0.6
    padding: 16
```

Preferisci `slot` ad `at`: un testo agganciato ai posti compare e sparisce sul
battito. Non mettere due testi nello stesso punto nello stesso momento.

## 4. Controlla, guarda, consegna

```bash
vedit render edits/<nome> --check          # errori e avvisi: risolvili tutti
vedit render edits/<nome> --preview        # anteprima veloce (meta' risoluzione)
vedit sheet edits/<nome>/output/<nome>_preview.mp4 --slots templates/<template> \
            -o edits/<nome>/output/provini.png
```

Apri i provini e guarda ogni posto: il media giusto? I testi si leggono, sono interi,
non coprono la parte importante dell'immagine? Correggi e ripeti. Poi il video finale:

```bash
vedit render edits/<nome>
```

Mandalo all'utente come file (`edits/<nome>/output/<nome>.mp4`), con due righe su
cosa hai messo dove. Fai il commit dell'`edit.yaml`, non dei media: ricordagli che
in una sessione nuova, per rifare il render, i file andranno caricati di nuovo.
