# edits/

Un **edit** per video: una cartella con il suo `edit.yaml`, i media e i render.

```
edits/mio-video/
├── edit.yaml     quale media va in quale posto del template, e quali testi
├── media/        le immagini, i video e le GIF di questo video  (ignorati da git)
└── output/       i render                                        (ignorati da git)
```

```bash
vedit new edits/mio-video --template templates/raffica   # crea lo scheletro
vedit render edits/mio-video --check                     # cosa cade dove
vedit render edits/mio-video --preview                   # anteprima veloce
vedit render edits/mio-video                             # il video finale
```

L'`edit.yaml` si versiona, i media no: sono pesanti e cambiano a ogni video. La
conseguenza pratica è che per rifare un render in una sessione nuova servono di
nuovo i file: l'edit ricorda **dove** vanno, non li contiene.

Il formato dell'edit è spiegato nel [README principale](../README.md#ledit).
