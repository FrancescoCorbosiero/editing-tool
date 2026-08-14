# Glossario

I termini di montaggio che compaiono in questo repo, spiegati a chi viene dalla
programmazione e non dal video. Dove aiuta, c'è l'analogia con qualcosa che già
conosci — sapendo che le analogie, prima o poi, mentono.

---

## Il materiale

**Fotogramma** (*frame*) — una singola immagine. Un video è un array di immagini
mostrate abbastanza in fretta da sembrare movimento. Tutto il resto è dettaglio.

**fps** (*frame per second*) — quante immagini al secondo. 24 è il cinema, 25/30 la
televisione, 50/60 lo sport e i videogiochi. **Mescolare fps diversi nello stesso
montaggio** costringe a ricampionare: qualche fotogramma viene duplicato o buttato, e
i movimenti possono risultare meno fluidi. `--check` te lo segnala.

**Risoluzione** — quanti pixel per fotogramma, `larghezza × altezza`. 1920×1080 è
"Full HD" o "1080p", 3840×2160 è "4K". La `p` sta per *progressive*: tutte le righe
del fotogramma sono catturate nello stesso istante. L'alternativa storica,
*interlacciato* (`i`), catturava metà righe alla volta — un trucco per dimezzare la
banda ai tempi della TV analogica, che oggi incontri solo su materiale d'archivio.

**Proporzioni** (*aspect ratio*) — il rapporto larghezza/altezza: 16:9 è
l'orizzontale standard, 9:16 il verticale dei telefoni, 1:1 il quadrato. È la
proprietà che ti costringe a scegliere fra bande nere e ritaglio quando mescoli
materiale girato in formati diversi.

**Codec** — l'algoritmo che comprime i fotogrammi (`libx264`, `libx265`).
**Contenitore** (*container*) — il formato del file che li contiene, insieme
all'audio e ai metadati (`.mp4`, `.mkv`, `.mov`). Sono cose diverse: un `.mp4` può
contenere codec diversi, come un `.zip` può contenere qualsiasi cosa.

**Pixel format** (`yuv420p`) — come sono organizzati i colori dentro il flusso
compresso. `yuv420p` tiene la luminosità a risoluzione piena e il colore a un quarto,
perché l'occhio umano è molto più sensibile alla prima. È il formato che **tutti** i
player sanno leggere: `vedit` lo forza, e non è una scelta da rivedere.

**Keyframe** — parola con **due significati diversi**, ed è una fonte di confusione
seria:
1. *nella compressione*: un fotogramma memorizzato per intero, senza riferimenti agli
   altri. I fotogrammi fra due keyframe descrivono solo le differenze, ed è per
   questo che un taglio "senza ricompressione" (`fast_cut`) può spostarsi al keyframe
   più vicino: prima non c'è un fotogramma completo da cui ripartire;
2. *nell'animazione*: un punto in cui dichiari il valore di un parametro (posizione,
   scala, opacità), lasciando che il software interpoli fra un punto e l'altro. Questo
   è il senso che ha "keyframe" quando si parla di effetti.

**CRF** (*Constant Rate Factor*) — la manopola della qualità in libx264/libx265, da 0
(senza perdita, enorme) a 51 (irriconoscibile). 18 è alta qualità, 23 il default, 28
compresso. **Più basso = più grande.** A differenza del bitrate, dichiari la qualità
e lasci che sia il file a pesare quello che serve.

**Preset** — quanto tempo l'encoder può spendere a cercare la compressione migliore
(`ultrafast` … `veryslow`). Non cambia la qualità *dichiarata* (quella è il CRF),
cambia quanto file serve per ottenerla. È il classico scambio tempo/spazio.

**Bitrate** — quanti bit al secondo occupa il flusso. È il modo alternativo di
governare la qualità: lo imponi quando devi rispettare un limite (una piattaforma, un
supporto), mentre il CRF è quello che vuoi quando ti interessa il risultato.

---

## Il montaggio

**Timeline** — l'asse del tempo su cui si dispongono i pezzi. In `vedit` è una lista
YAML: l'ordine nella lista *è* l'ordine nel tempo.

**Clip** — un pezzo di materiale posizionato sulla timeline. Un file sorgente può
comparire in dieci clip diversi, con dieci tagli diversi: il clip non è il file, è
un intervallo che punta al file.

**Segmento** — il nome che questo repo dà a una voce della timeline, per non
confonderla con il clip MoviePy che ne nasce.

**Inquadratura** (*shot*) — un pezzo di video girato senza interruzioni, cioè quello
che sta fra due tagli. Nel materiale già montato che analizzi è l'unità che il
rilevatore cerca (`vedit shots`); nel montaggio che stai scrivendo corrisponde a un
segmento.

**Ritmo del montaggio** — ogni quanto si stacca. Non è una preferenza estetica: la
durata media delle inquadrature è la cosa che lo spettatore percepisce come
"energia" del video. Sotto il secondo è un montaggio nervoso da social, sopra i
cinque è un documentario.

**Taglio IN / OUT** (*in point*, *out point*) — dove comincia e dove finisce la
porzione che prendi **dal sorgente**. In `vedit` sono `start` e `end`, e sono nel
tempo del *file*, non della timeline: `start: 40` significa "dal minuto 0:40 del
file", non "al secondo 40 del montaggio".

**Stacco** (*cut*) — passare da un'inquadratura all'altra senza niente in mezzo. È il
passaggio più usato al mondo e il più sottovalutato da chi comincia, che tende a
dissolvere tutto. Uno stacco dice "siamo ancora qui, ma guarda di là".

**Transizione** — qualsiasi cosa metti *fra* due inquadrature al posto di uno stacco.
Non è decorazione: ogni transizione afferma qualcosa sul rapporto fra i due pezzi.

**Dissolvenza incrociata** (*crossfade*, *dissolve*) — il secondo pezzo compare mentre
il primo svanisce. Richiede che i due **coesistano nel tempo**: è la ragione per cui
un crossfade accorcia il montaggio: due clip da 4s con 1s di dissolvenza durano 7s,
non 8. Senza sovrapposizione dissolveresti dal nero, non dall'altro clip.

**Dissolvenza al nero** (*fade to black*, *dip to black*) — il primo pezzo si spegne,
il secondo si accende. Il nero in mezzo è una pausa, e il pubblico la legge come un
salto di tempo o di luogo. Non sovrappone nulla, quindi non accorcia il montaggio.

**Wipe** — una linea attraversa lo schermo e "scopre" il nuovo pezzo. I clip non si
muovono, si muove il confine fra i due. Si realizza con una **maschera** animata.

**Slide** (*push*) — il nuovo pezzo entra scorrendo da un bordo. A differenza del
wipe, qui è l'immagine che si sposta.

**Maschera** (*mask*, *canale alfa*) — un'immagine in scala di grigi grande quanto il
fotogramma, dove 0 = trasparente e 1 = opaco. Tutto ciò che riguarda dissolvenze,
wipe e trasparenze passa da qui. In termini di codice: un array di float che
moltiplica i pixel prima di comporli sopra a ciò che sta sotto.

**Composito** (*composite*) — sovrapporre più livelli in un unico fotogramma. È
l'equivalente video dei layer di un programma di grafica, con in più l'asse del tempo.

**L-cut / J-cut** — tagli in cui **audio e video non cambiano nello stesso istante**:
senti già la scena successiva mentre vedi ancora quella precedente (J-cut), o
continui a sentire la precedente sulle immagini della nuova (L-cut). I nomi vengono
dalla forma che assumono sulla timeline di una GUI. Sono il trucco più efficace per
rendere invisibile il montaggio di un dialogo. `vedit` non li supporta ancora:
servirebbe poter sfalsare la traccia audio di un segmento rispetto al video.

**Montaggio** (*edit*) — sia l'attività sia il risultato. In inglese *editing* è
l'attività, *the edit* il risultato.

**Export / rendering** — trasformare la descrizione del montaggio nel file finale.
Rendering è il calcolo dei fotogrammi, export è il salvataggio: nella pratica si
usano come sinonimi.

---

## Inquadratura e movimento

**Canvas** — il rettangolo di output in cui tutto viene fatto entrare. In `vedit` è
`output.size`, ed è la ragione per cui puoi mescolare un video 4K e una foto
verticale senza pensarci: entrambi finiscono adattati allo stesso rettangolo.

**Letterbox** — le bande nere sopra e sotto, quando il materiale è più largo del
canvas. **Pillarbox** — le bande ai lati, quando è più stretto (una foto verticale su
un canvas orizzontale). Entrambi sono il prezzo di *non* ritagliare.

**contain / cover / stretch** — le tre risposte possibili a "questo materiale non ha
le proporzioni del canvas". `contain` = ci sta tutto, con le bande; `cover` = riempi
e taglia l'eccesso; `stretch` = deforma. Sono le stesse tre opzioni di `object-fit`
in CSS, e la scelta ha le stesse conseguenze.

**Pan** — l'inquadratura si sposta lateralmente. **Tilt** — si sposta in verticale.
**Zoom** — cambia l'ingrandimento. Nel linguaggio comune i nomi descrivono la
**camera**, non l'immagine: `pan_right` sposta l'inquadratura verso destra, quindi
l'immagine sullo schermo scorre verso *sinistra*.

**Ken Burns** — l'effetto che anima una foto ferma con un lento zoom o una lenta
carrellata. Dal documentarista americano che ne fece il suo marchio per animare
fotografie d'archivio. Regola pratica: se lo noti, è troppo.

**Safe area** (*title safe*, *action safe*) — il rettangolo interno entro cui tenere
il testo perché non venga tagliato o coperto dall'interfaccia del player. Eredità dei
televisori a tubo catodico, che tagliavano i bordi; oggi resta utile perché ogni
piattaforma social sovrappone qualcosa (nomi, pulsanti, didascalie) ai margini.
Regola pratica: lascia libero il 5-10% su ogni lato.

**Lower third** — la scritta in basso che presenta chi sta parlando ("Mario Rossi,
sindaco"). Si chiama così perché occupa il terzo inferiore dello schermo. In `vedit`
è un overlay di testo con `position: ["center", <y verso il basso>]`.

**Watermark** — un logo semitrasparente presente per tutta la durata, per marcare la
paternità del video.

---

## Audio

**Traccia** — un flusso audio indipendente. Un montaggio ne ha di solito almeno due:
l'audio delle riprese e la musica.

**Mix** — la somma delle tracce, ciascuna al suo volume. In `vedit`, `audio.replace:
false` somma la musica all'audio originale, `true` lo sostituisce.

**Fade in / fade out** — il volume che sale da zero o scende a zero. Un taglio netto
sulla musica si sente come un errore; mezzo secondo di dissolvenza no.

**Voce fuori campo** (*voice-over*) — commento parlato registrato a parte, non
proveniente dalla scena.

**Battito** (*beat*) — il colpo regolare su cui batti il piede. **BPM** (*beats per
minute*) è quanti ne passano in un minuto: 120 BPM significa un battito ogni mezzo
secondo. Montare "a tempo" vuol dire far cadere i cambi di scena su quei momenti;
quando succede, il pubblico li sente arrivare e il video "gira".

**Levare** (*off-beat*, *upbeat*) — a metà fra due battiti. Molta musica ballabile ha
metà dei suoi colpi lì, ed è il motivo per cui un montaggio può stare a tempo anche
staccando fra un battito e l'altro: non è un errore, è una scelta.

**Quantizzare** — spostare qualcosa sulla griglia del tempo più vicina. È un termine
preso dai sequencer musicali, dove la stessa operazione rimette in riga una battuta
suonata a mano. In `vedit` lo fa `extract` con i tagli che trova, e lo fa in modo
prudente: solo se erano già vicini al battito.

---

## Template

**Template audio** — un montaggio riutilizzabile: la traccia musicale, il tempo, gli
istanti dei tagli e il formato, senza i media. È l'idea che su CapCut trovi come
"riusare un suono": non prendi in prestito una canzone, prendi in prestito un
montaggio che su quella canzone funziona. Si estrae da un video di riferimento e si
applica ai propri file.

**Slot** — un posto nel montaggio descritto da un template: comincia a un istante
preciso e finisce quando comincia il successivo. Non sa cosa ci finirà dentro — un
video, una foto — sa solo quando comincia, come entra in scena e, se capitasse una
foto, come muoverla.

**Rilevamento dei tagli** (*shot detection*) — capire da un video già montato dove
sono stati fatti gli stacchi. `vedit` confronta gli **istogrammi** dei fotogrammi
consecutivi (quanti pixel di ogni colore) invece dei pixel uno per uno: se la camera
si muove i pixel cambiano posizione ma le quantità restano, mentre a un taglio
cambia tutto. È la differenza fra riconoscere uno stacco e riconoscere un movimento.

---

## Flusso di lavoro

**Proxy** — una copia a bassa risoluzione dei sorgenti, su cui montare per non
aspettare. Si genera una volta e si butta quando serve: l'export finale torna sempre
agli originali. È una cache, con gli stessi problemi di invalidazione di ogni cache —
`vedit` li risolve mettendo l'impronta del sorgente nel nome del proxy.

**Anteprima** (*preview*) — un export veloce e brutto, fatto per guardare il
montaggio, non la qualità. Se non lavori in anteprima, passerai la giornata ad
aspettare.

**Upscaling** — ingrandire materiale più piccolo del canvas. I pixel mancanti vengono
inventati per interpolazione: il risultato è più morbido, mai più nitido. `--check`
avvisa quando sta per succedere.

**Sottotitoli / SRT** — testo sincronizzato, in un formato che è testo semplice a
blocchi (tempo di inizio, tempo di fine, righe). "Sottotitoli" in senso stretto sono
la traduzione dei dialoghi; i *closed caption* includono anche i suoni ("[bussano
alla porta]") e servono all'accessibilità.

**Sync** — l'allineamento fra audio e video, o fra sottotitoli e parlato. Un file
`.srt` scaricato da un'altra edizione dello stesso video è quasi sempre sfasato di
qualche secondo: si sistema spostando *tutti* i tempi della stessa quantità
(`subtitles.offset`).
