# Prompt per Claude Code

Copia il blocco qui sotto nella sessione di Claude Code aperta nella root del repo.

Non incollarlo tutto in una volta se vuoi controllo: le fasi sono progettate per
essere eseguite **una alla volta**. Fai la Fase 1, verifica, poi chiedi la Fase 2.

---

```
Lavori su `vedit`, un toolkit Python per montare video in modo dichiarativo:
un file YAML descrive una timeline, il codice la traduce in clip MoviePy e la esporta.

PRIMA DI SCRIVERE CODICE: leggi CLAUDE.md, poi vedit/models.py e vedit/builder.py.
CLAUDE.md contiene vincoli non negoziabili, in particolare sull'API di MoviePy 2.x —
la 1.x è incompatibile e gran parte del codice che conosci è per la 1.x.

Contesto su di me: so programmare bene, ma non ho mai usato un software di editing
video. Non do per scontato nessun termine del dominio. Quando introduci un concetto
di editing (keyframe, letterbox, L-cut, lower third, safe area), spiegalo in una riga
nel commento o nel README. Il codice è anche il mio materiale di studio.

METODO DI LAVORO
- Una fase alla volta. Al termine di ogni fase fermati e riassumi cosa hai cambiato,
  poi aspetta il mio via libera prima di passare alla successiva.
- Ogni funzionalità dichiarativa richiede tre modifiche coordinate: il campo in
  models.py con la validazione, la traduzione in builder.py, la riga nella tabella
  dello schema in README.md. Non lasciarne indietro una.
- Aggiungi test in tests/ per ogni fase. I test non devono richiedere file video:
  usa segmenti `type: color`. Dove serve un sorgente reale, generalo con ffmpeg
  (`testsrc` di lavfi) in una fixture temporanea.
- Prima di dire che una fase è completa: `pytest -q` verde, `python -m vedit render
  projects/demo/timeline.yaml --dry-run` senza errori, e per le modifiche al
  rendering un render `--preview` reale con verifica dei frame campionati
  (il metodo è descritto in CLAUDE.md).
- Se una scelta di design ha alternative sensate, fermati e chiedimi, invece di
  decidere in silenzio.

FASE 1 — Robustezza
Prima di aggiungere funzionalità, rendi solido quello che c'è.
- Verifica all'avvio che tutti i file referenziati nel progetto esistano, e riporta
  TUTTI gli errori insieme invece di fermarti al primo.
- Barra di avanzamento leggibile: MoviePy stampa un tqdm rumorosissimo. Sopprimilo
  (`logger=None` in write_videofile) e mostra un progresso pulito con la stima del
  tempo residuo.
- Gestisci Ctrl-C durante l'export: chiudi i clip, cancella il file parziale.
- Un flag `--check` che valida il progetto e stampa un riepilogo della timeline
  (durata totale, elenco dei segmenti con inizio/fine calcolati, avvisi su
  risoluzioni o fps discordanti fra le sorgenti) senza renderizzare nulla.

FASE 2 — Transizioni vere
Al momento esiste solo il crossfade. Aggiungi un campo `transition_type` sui segmenti:
`crossfade` (attuale, default), `fade_through_black`, `slide` (con direzione),
`wipe` (con direzione), `cut` (nessuna transizione).
Implementale in un modulo dedicato `vedit/transitions.py` con un registry
nome → funzione, così aggiungerne una nuova non richiede di toccare builder.py.
Documenta nel README come si aggiunge una transizione custom.

FASE 3 — Ken Burns e movimento sulle immagini
Uno slideshow di immagini statiche è morto. Aggiungi un campo `motion` sui segmenti
immagine: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, con parametro `amount`.
Attenzione: il ridimensionamento dinamico frame per frame è lento e produce
artefatti se le dimensioni risultanti sono dispari — arrotonda a numeri pari.
Misura l'impatto sui tempi di export e documentalo.

FASE 4 — Testo e sottotitoli
- Migliora l'overlay `text`: sfondo semitrasparente opzionale, contorno, a capo
  automatico entro una larghezza massima, allineamento.
- Aggiungi il supporto ai file `.srt`: un campo `subtitles` nel progetto che carica
  un srt e lo renderizza sul video, con stile configurabile.
- Fornisci un font libero in assets/fonts/ o documenta chiaramente come indicarne uno,
  perché senza font esplicito il TextClip di MoviePy fallisce su molti sistemi.

FASE 5 — Flusso di lavoro con i proxy
Montare su file 4K è insopportabilmente lento. Aggiungi:
- `python -m vedit proxy <progetto>` che genera versioni a 480p di tutte le sorgenti
  in proxies/, con cache basata su hash del file (non rigenerare se già presente).
- Un flag `--use-proxy` su render che sostituisce automaticamente le sorgenti con i
  proxy, mantenendo identico il risultato del montaggio.
- L'export finale usa sempre gli originali.

FASE 6 — Qualità del progetto
- Sposta la configurazione in un pyproject.toml, con un entry point `vedit` così si
  può invocare senza `python -m`.
- Aggiungi ruff per lint e formattazione, configurato nel pyproject.
- Una GitHub Action che su push installa le dipendenze, installa ffmpeg e lancia
  pytest e ruff.
- Un file docs/GLOSSARIO.md con i termini di editing usati nel repo, spiegati per
  qualcuno che viene dalla programmazione e non dal video.

Comincia dalla Fase 1. Prima di scrivere, dimmi cosa hai capito dell'architettura
attuale e come intendi procedere.
```

---

## Come usarlo

```bash
git clone <url-del-tuo-repo>
cd video-toolkit
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
claude
```

Poi incolla il blocco. Claude Code leggerà `CLAUDE.md` automaticamente ad ogni
sessione, quindi i vincoli restano attivi anche nelle conversazioni successive.

## Suggerimenti

**Fai un commit prima di ogni fase.** Così puoi tornare indietro con `git reset --hard`
se una direzione non ti convince, senza perdere il lavoro precedente.

**Chiedi spiegazioni.** "Perché hai usato `with_effects` invece di X?" è una domanda
legittima e ti insegna il dominio molto più in fretta della lettura passiva.

**Non saltare la Fase 1.** È la meno divertente ed è quella che ti farà risparmiare
più tempo: senza messaggi d'errore decenti, ogni bug successivo costa il triplo.
