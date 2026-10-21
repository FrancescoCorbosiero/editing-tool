"""
Interfaccia da riga di comando.

    vedit extract riferimento.mp4 -o templates/nome      # video -> template
    vedit slots templates/nome --cut 4.45 --video        # un taglio in piu', a orecchio
    vedit new edits/video --template templates/nome      # un edit nuovo sul template
    vedit render edits/video --check                     # cosa cade dove, senza render
    vedit render edits/video --preview                   # anteprima veloce
    vedit sheet output/video.mp4 --slots templates/nome  # provini, per controllare
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .ffmpeg_tools import FFmpegError, ensure_ffmpeg, probe
from .models import ConfigError, Project


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def media_durations(media) -> dict[Path, float]:
    """
    Le durate dei video e delle GIF fra i media, lette con ffprobe.

    Servono a scoprire SUBITO che un video e' troppo corto per lo slot in cui e'
    finito, invece che a meta' export. I file che non esistono si saltano: li
    elenca tutti insieme la verifica dei file, con un messaggio migliore di
    quello che darebbe ffprobe.
    """
    durate: dict[Path, float] = {}
    for ref in media:
        percorso = ref.path.resolve()
        if ref.kind == "video" and percorso not in durate and percorso.exists():
            durate[percorso] = probe(percorso)["duration"]
    return durate


def _read_yaml(path: Path) -> object:
    import yaml

    if not path.exists():
        raise ConfigError(f"File non trovato: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_project(args: argparse.Namespace) -> tuple[Project, str]:
    """
    Carica quello che c'e' da renderizzare: un timeline.yaml o un edit.yaml.

    Un edit (un file con `template:`) si espande nel suo progetto, e si stampa
    il piano: quale media in quale posto, quali testi quando. La verifica dei
    file sta qui e non nel builder perche' deve avvenire PRIMA di costruire
    qualsiasi cosa: meglio quattro percorsi sbagliati elencati subito che un
    errore alla volta dopo trenta secondi di lavoro buttato.
    """
    from .edit import MANIFEST, Edit, is_edit

    path = Path(args.project)
    if path.is_dir():
        path = path / MANIFEST
    data = _read_yaml(path)

    if is_edit(data):
        edit = Edit.from_yaml(path)
        bound = edit.bind(media_durations(edit.media))
        # Con --check i testi li elenca gia' il riepilogo, insieme agli altri overlay.
        print(edit.describe(bound, texts=not getattr(args, "check", False)))
        print()
        project = bound.project(edit.root)
    else:
        if getattr(args, "to_yaml", None):
            raise ConfigError(
                "--to-yaml espande un edit nel suo progetto: questo file e' gia' un progetto"
            )
        project = Project.from_yaml(path)

    project.validate_files()
    return project, str(path)


def cmd_render(args: argparse.Namespace) -> int:
    ensure_ffmpeg()

    if args.to_yaml:
        return _edit_to_yaml(args)

    project, label = load_project(args)

    if args.output:
        project.output.path = Path(args.output)

    if args.check:
        # --check non renderizza: niente import di MoviePy, che costa secondi.
        from .report import analyze, format_report

        print(format_report(analyze(project, label)))
        return 0

    from .builder import close_all, render  # import pigro: MoviePy e' lento da caricare

    try:
        target = render(project, dry_run=args.dry_run, preview=args.preview)
    finally:
        close_all()

    if target and target.exists():
        size_mb = target.stat().st_size / 1_000_000
        print(f"\nFatto: {target}  ({size_mb:.1f} MB)")
    return 0


def _edit_to_yaml(args: argparse.Namespace) -> int:
    """Scrive il progetto in cui si espande un edit: la valvola per le modifiche a mano."""
    from .edit import MANIFEST, Edit, is_edit
    from .templates import to_yaml

    path = Path(args.project)
    if path.is_dir():
        path = path / MANIFEST
    if not is_edit(_read_yaml(path)):
        raise ConfigError(
            "--to-yaml espande un edit nel suo progetto: questo file e' gia' un progetto"
        )
    edit = Edit.from_yaml(path)
    target = Path(args.to_yaml)
    target.parent.mkdir(parents=True, exist_ok=True)
    bound = edit.bind(media_durations(edit.media), root=target.parent.resolve())
    target.write_text(to_yaml(bound), encoding="utf-8")
    print(f"Progetto scritto in {target}")
    print(f"  vedit render {target} --preview")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    info = probe(args.path)
    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    print(f"File      : {info['path']}")
    print(f"Durata    : {info['duration']:.2f}s")
    if info["width"]:
        print(f"Risoluzione: {info['width']}x{info['height']} @ {info['fps']} fps")
    print(f"Video     : {info['video_codec']}")
    print(f"Audio     : {info['audio_codec'] or 'assente'}")
    print(f"Dimensione: {info['size_bytes'] / 1_000_000:.1f} MB")
    return 0


def cmd_beats(args: argparse.Namespace) -> int:
    """Legge il battito di una traccia: e' il passo prima di montarci sopra."""
    from .beats import analyze, describe

    ensure_ffmpeg()
    if not Path(args.path).exists():
        raise FileNotFoundError(args.path)

    grid = analyze(args.path, cutoff=args.cutoff, sensitivity=args.sensitivity)
    if args.json:
        print(json.dumps({"bpm": grid.bpm, "period": grid.period,
                          "beats": grid.beats, "onsets": grid.onsets}, indent=2))
    else:
        print(describe(grid, args.path))
    return 0


def cmd_shots(args: argparse.Namespace) -> int:
    """Legge i tagli di un video: e' il passo prima di estrarne un template."""
    from .scenes import analyze, describe

    ensure_ffmpeg()
    if not Path(args.path).exists():
        raise FileNotFoundError(args.path)

    result = analyze(args.path, sensitivity=args.sensitivity, min_shot=args.min_shot)
    if args.json:
        print(json.dumps({
            "duration": result.duration,
            "fps": result.fps,
            "cuts": result.cuts,
            "shots": [{"start": s.start, "end": s.end, "duration": round(s.duration, 4)}
                      for s in result.shots],
        }, indent=2))
    else:
        print(describe(result, args.path))
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Estrae un template audio da un video di riferimento."""
    from .extract import describe, extract

    ensure_ffmpeg()
    source = Path(args.video)
    if not source.exists():
        raise FileNotFoundError(source)

    destination = Path(args.output) if args.output else Path("templates") / source.stem

    result = extract(
        source, destination,
        name=args.name or destination.name,
        grid=args.grid,
        sensitivity=args.sensitivity,
        min_slot=args.min_slot,
        transition=args.transition,
        transition_type=args.transition_type,
        force=args.force,
    )
    print(describe(result, destination))
    return 0


def cmd_templates(args: argparse.Namespace) -> int:
    """Elenca i template disponibili: quali montaggi si possono riusare."""
    from .extract import available
    from .templates import Template

    cartelle = available(args.directory)
    if not cartelle:
        print(f"Nessun template in {args.directory}/.")
        print("Creane uno da un video che ti piace:")
        print("  python -m vedit extract riferimento.mp4")
        return 0

    print(f"Template in {args.directory}/:\n")
    for cartella in cartelle:
        try:
            template = Template.from_yaml(cartella)
        except ConfigError as exc:
            print(f"  {cartella.name:<24} (non leggibile: {exc})")
            continue
        tempo = f"{template.audio.bpm:g} BPM" if template.audio.bpm else "senza battito"
        print(f"  {cartella.name:<24} {template.duration:6.2f}s  "
              f"{len(template.slots):3d} slot  {tempo:<14} "
              f"{template.size[0]}x{template.size[1]}  {template.style.fit}")
    return 0


def cmd_slots(args: argparse.Namespace) -> int:
    """I posti di un template: elencarli, cambiare i tagli, guardarli sulla musica."""
    from .extract import render as render_template
    from .slots import describe, describe_change, edits_using, renumbering, retime
    from .templates import MANIFEST, Template

    template = Template.from_yaml(args.template)
    nome = Path(args.template).as_posix()
    if nome.endswith(f"/{MANIFEST}"):
        nome = nome[: -len(MANIFEST) - 1]

    if args.cut or args.split or args.merge:
        result = retime(template, cuts=args.cut or [], split=args.split or [],
                        into=args.into, merge=args.merge or [], grid=args.grid)
        print(describe_change(template, result, nome))
        if result.changed:
            (template.root / MANIFEST).write_text(render_template(result.template),
                                                  encoding="utf-8")
            edits = edits_using(template, "edits")
            if edits:
                # Un edit mette i media nei posti in ordine e aggancia i testi ai
                # numeri: con i posti cambiati, gli uni e gli altri vanno rivisti.
                print(f"\nQuesti edit usano {template.name}, e i numeri dei posti sono cambiati:")
                print("\n".join(f"  {path.as_posix()}" for path in edits))
                for riga in renumbering(template, result):
                    print(f"  ({riga})")
                print("Nella lista 'media' serve un file per ogni posto nuovo, e i 'slot:' dei "
                      "testi vanno spostati di conseguenza. Controlla con:")
                print(f"  vedit render {edits[0].parent.as_posix()} --check")
        template = result.template
    elif not args.video:
        print(describe(template, nome))
        return 0

    if args.video:
        target = _slots_video(template, Path(args.output) if args.output
                              else Path("output") / f"{template.name}-posti.mp4")
        print(f"\nI posti numerati sulla musica: {target}")
    return 0


def _slots_video(template, output: Path) -> Path:
    """
    Il template montato con un cartello numerato per posto, sulla sua traccia.

    E' il modo di sentire dove cade ogni taglio prima di metterci dei media, e di
    poterne parlare: "il 4 va diviso" invece di "verso il quarto secondo". Va a
    meta' risoluzione e al massimo a 30 fps, perche' serve a guardare il ritmo,
    non i dettagli; 30 e non i 24 dell'anteprima, perche' a 24 fps un taglio
    puo' cadere fino a 20 ms fuori posto, e qui il posto e' l'unica cosa che conta.
    """
    import tempfile

    from .builder import close_all, render  # import pigro: MoviePy e' lento
    from .slots import cards
    from .templates import MediaRef, bind

    ensure_ffmpeg()
    size = (max(2, template.size[0] // 4 * 2), max(2, template.size[1] // 4 * 2))
    # ignore_cleanup_errors: su Windows un file appena letto puo' essere ancora
    # aperto quando la cartella temporanea viene cancellata.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        files = cards(template, tmp, width=size[0])
        bound = bind(template, [MediaRef(path=f) for f in files], output=output,
                     size=size, fps=min(template.fps, 30), root=Path.cwd())
        project = bound.project(Path.cwd())
        project.output.preset = "ultrafast"
        try:
            target = render(project)
        finally:
            close_all()
    return target


def _parse_size(value: str | None) -> tuple[int, int] | None:
    """`1080x1920` -> (1080, 1920)."""
    if not value:
        return None
    parts = value.lower().replace(":", "x").split("x")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise ConfigError(f"--size vuole un formato tipo 1080x1920 (ricevuto '{value}')")
    return int(parts[0]), int(parts[1])


def cmd_apply(args: argparse.Namespace) -> int:
    """Applica un template ai propri media e monta il risultato."""
    from .templates import Template, bind, describe_bound, expand_media, to_yaml

    ensure_ffmpeg()
    template = Template.from_yaml(args.template)
    media = expand_media(args.media)

    mancanti = [str(m.path) for m in media if not m.path.exists()]
    if mancanti:
        raise ConfigError("File non trovati:\n" + "\n".join(f"  - {p}" for p in mancanti))

    durate = media_durations(media)
    destinazione = Path(args.to_yaml).parent if args.to_yaml else Path.cwd()
    bound = bind(
        template, media,
        output=args.output,
        size=_parse_size(args.size),
        fps=args.fps,
        keep_audio=args.keep_audio,
        volume=args.volume,
        strict=args.strict,
        root=destinazione,
        durations=durate,
    )

    print(describe_bound(template, bound))

    if args.to_yaml:
        target = Path(args.to_yaml)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(to_yaml(bound), encoding="utf-8")
        print(f"\nProgetto scritto in {target}")
        print(f"  python -m vedit render {target} --preview")
        return 0

    project = bound.project(destinazione)
    project.validate_files()

    if args.check:
        from .report import analyze, format_report

        print()
        print(format_report(analyze(project, f"{args.template} + {len(media)} media")))
        return 0

    from .builder import close_all, render  # import pigro: MoviePy e' lento

    try:
        target = render(project, dry_run=args.dry_run, preview=args.preview)
    finally:
        close_all()

    if target and target.exists():
        print(f"\nFatto: {target}  ({target.stat().st_size / 1_000_000:.1f} MB)")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    """Crea un edit nuovo su un template: lo scheletro commentato, posto per posto."""
    from .edit import MANIFEST, skeleton
    from .templates import Template, expand_media

    template = Template.from_yaml(args.template)
    root = Path(args.directory)
    target = root / MANIFEST
    if target.exists() and not args.force:
        raise ConfigError(f"Esiste gia': {target}  (usa --force per sovrascriverlo)")

    media = expand_media(args.media) if args.media else None
    for cartella in ("media", "output"):
        (root / cartella).mkdir(parents=True, exist_ok=True)
        (root / cartella / ".gitkeep").touch()
    target.write_text(
        skeleton(template, template.root, root.resolve(), root.name, media), encoding="utf-8"
    )

    print(f"Creato {target}  ({len(template.slots)} posti da riempire)")
    if not media:
        print(f"Metti i tuoi file in {root / 'media'}/ e scrivili nella lista 'media', poi:")
    print(f"  vedit render {target} --check")
    return 0


def cmd_sheet(args: argparse.Namespace) -> int:
    """Il foglio dei provini di un video: tutto il video in un'immagine."""
    from .sheet import contact_sheet, regular_times

    ensure_ffmpeg()
    source = Path(args.video)
    if not source.exists():
        raise FileNotFoundError(source)

    if args.slots:
        from .templates import Template

        template = Template.from_yaml(args.slots)
        gaps = template.gaps()
        times = [slot.at + gap / 2 for slot, gap in zip(template.slots, gaps, strict=True)]
        labels = [f"{i + 1}) {t:.2f}s" for i, t in enumerate(times)]
    elif args.shots:
        from .scenes import analyze

        shots = analyze(source).shots
        times = [shot.middle for shot in shots]
        labels = [f"{shot.index + 1}) {shot.start:.2f}s" for shot in shots]
    else:
        times = regular_times(probe(source)["duration"], args.every)
        labels = [f"{t:.2f}s" for t in times]

    output = Path(args.output) if args.output else Path("output") / f"{source.stem}-provini.png"
    contact_sheet(source, times, labels, output, width=args.width, columns=args.columns)
    print(f"Provini: {output}  ({len(times)} fotogrammi)")
    return 0


def cmd_fonts(args: argparse.Namespace) -> int:
    """Elenca i font utilizzabili: senza un font il testo su video non si disegna."""
    from .fonts import describe

    print(describe())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vedit",
        description="Montaggio video dichiarativo: da un file YAML a un mp4.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log dettagliato")
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="renderizza un edit o un progetto")
    p_render.add_argument("project",
                          help="un edit.yaml (o la sua cartella) oppure un timeline.yaml")
    p_render.add_argument("-o", "--output", help="sovrascrive output.path del YAML")
    p_render.add_argument("--preview", action="store_true",
                          help="anteprima veloce a bassa risoluzione")
    p_render.add_argument("--dry-run", action="store_true",
                          help="costruisce la timeline senza esportare (valida il YAML)")
    p_render.add_argument("--check", action="store_true",
                          help="valida il progetto e stampa il riepilogo della timeline, "
                               "senza costruire ne' esportare nulla")
    p_render.add_argument("--to-yaml",
                          help="per un edit: scrive il timeline.yaml in cui si espande, "
                               "da correggere a mano, invece di renderizzare")
    p_render.set_defaults(func=cmd_render)

    p_probe = sub.add_parser("probe", help="mostra i metadati di un file")
    p_probe.add_argument("path")
    p_probe.add_argument("--json", action="store_true")
    p_probe.set_defaults(func=cmd_probe)

    p_beats = sub.add_parser("beats", help="trova il tempo e i battiti di una traccia audio")
    p_beats.add_argument("path", help="file audio o video da analizzare")
    p_beats.add_argument("--cutoff", type=int, default=150,
                         help="taglio del passa-basso in Hz: piu' basso isola meglio "
                              "la cassa, piu' alto prende anche i rullanti (default: 150)")
    p_beats.add_argument("--sensitivity", type=float, default=1.5,
                         help="quanto e' facile che un suono conti come colpo: "
                              "abbassala se ne trova pochi (default: 1.5)")
    p_beats.add_argument("--json", action="store_true", help="stampa i tempi in JSON")
    p_beats.set_defaults(func=cmd_beats)

    p_shots = sub.add_parser("shots", help="trova i tagli di un video: dove cambia scena")
    p_shots.add_argument("path", help="video da analizzare")
    p_shots.add_argument("--sensitivity", type=float, default=4.0,
                         help="quanto deve cambiare l'immagine per contare come taglio: "
                              "abbassala se ne trova pochi (default: 4)")
    p_shots.add_argument("--min-shot", type=float, default=0.2,
                         help="durata minima di un'inquadratura, in secondi (default: 0.2)")
    p_shots.add_argument("--json", action="store_true", help="stampa i tagli in JSON")
    p_shots.set_defaults(func=cmd_shots)

    p_extract = sub.add_parser(
        "extract",
        help="estrae un template audio da un video di riferimento",
        description="Prende un video che ti piace e ne ricava la ricetta: la musica, "
                    "il tempo, gli istanti dei tagli, il formato. I media restano fuori: "
                    "quelli li porterai tu con `vedit apply`.",
    )
    p_extract.add_argument("video", help="il video di riferimento")
    p_extract.add_argument("-o", "--output",
                           help="cartella del template (default: templates/<nome del video>)")
    p_extract.add_argument("--name", help="nome del template (default: quello della cartella)")
    p_extract.add_argument("--grid", choices=("beat", "half", "quarter", "off"), default="half",
                           help="a cosa allineare i tagli: solo ai battiti, anche ai mezzi "
                                "(default) o ai quarti; 'off' li lascia come sono")
    p_extract.add_argument("--sensitivity", type=float, default=4.0,
                           help="quanto deve cambiare l'immagine per contare come taglio "
                                "(default: 4, guarda prima con `vedit shots`)")
    p_extract.add_argument("--min-slot", type=float, default=0.15,
                           help="durata minima di uno slot: i tagli piu' fitti vengono "
                                "scartati (default: 0.15, appena sotto il mezzo battito "
                                "di una canzone veloce)")
    p_extract.add_argument("--transition", type=float, default=0.0,
                           help="durata della transizione fra gli slot (default: 0, "
                                "cioe' stacco netto)")
    p_extract.add_argument("--transition-type", default="crossfade",
                           help="tipo di transizione, se --transition e' > 0 "
                                "(default: crossfade)")
    p_extract.add_argument("--force", action="store_true",
                           help="sovrascrive un template gia' presente")
    p_extract.set_defaults(func=cmd_extract)

    p_apply = sub.add_parser(
        "apply",
        help="applica un template ai tuoi media e monta il video",
        description="Prende un template e i tuoi file, e li monta. I media vanno negli "
                    "slot nell'ordine in cui li scrivi; una cartella si espande nei file "
                    "che contiene, in ordine alfabetico. Con `file.mp4@12.5` scegli da "
                    "quale secondo prendere quella ripresa.",
    )
    p_apply.add_argument("template", help="cartella del template (o il suo template.yaml)")
    p_apply.add_argument("media", nargs="+",
                         help="i tuoi file, o cartelle che li contengono")
    p_apply.add_argument("-o", "--output", help="file finale (default: output/<template>.mp4)")
    p_apply.add_argument("--preview", action="store_true",
                         help="anteprima veloce a bassa risoluzione")
    p_apply.add_argument("--check", action="store_true",
                         help="mostra il montaggio che verrebbe fuori, senza esportarlo")
    p_apply.add_argument("--dry-run", action="store_true",
                         help="costruisce la timeline senza esportare")
    p_apply.add_argument("--to-yaml",
                         help="invece di renderizzare, scrive il progetto in un "
                              "timeline.yaml da correggere a mano")
    p_apply.add_argument("--size",
                         help="cambia il formato del template, es. 1080x1920 per il verticale")
    p_apply.add_argument("--fps", type=int, help="cambia il frame rate del template")
    p_apply.add_argument("--keep-audio", action="store_true",
                         help="tiene anche l'audio dei tuoi video, sotto la traccia "
                              "del template (default: lo toglie)")
    p_apply.add_argument("--volume", type=float,
                         help="volume della traccia del template (1 = com'e')")
    p_apply.add_argument("--strict", action="store_true",
                         help="pretende esattamente un media per slot, invece di ripeterli")
    p_apply.set_defaults(func=cmd_apply)

    p_new = sub.add_parser(
        "new",
        help="crea un edit nuovo su un template",
        description="Crea una cartella con un edit.yaml commentato posto per posto, e le "
                    "sottocartelle media/ e output/. Se gli passi dei file (o una cartella), "
                    "li mette gia' nei posti, in ordine.",
    )
    p_new.add_argument("directory", help="la cartella dell'edit, es. edits/mio-video")
    p_new.add_argument("--template", required=True, help="la cartella del template")
    p_new.add_argument("media", nargs="*", help="i media da mettere nei posti (facoltativi)")
    p_new.add_argument("--force", action="store_true", help="sovrascrive un edit.yaml esistente")
    p_new.set_defaults(func=cmd_new)

    p_sheet = sub.add_parser(
        "sheet",
        help="il foglio dei provini di un video: tanti fotogrammi in un'immagine",
    )
    p_sheet.add_argument("video", help="il video da guardare")
    p_sheet.add_argument("-o", "--output",
                         help="l'immagine da scrivere (default: output/<video>-provini.png)")
    quali = p_sheet.add_mutually_exclusive_group()
    quali.add_argument("--every", type=float,
                       help="un provino ogni tot secondi (default: scelto sulla durata)")
    quali.add_argument("--shots", action="store_true",
                       help="un provino per inquadratura (per guardare un riferimento)")
    quali.add_argument("--slots", metavar="TEMPLATE",
                       help="un provino a meta' di ogni posto del template (per controllare "
                            "un render)")
    p_sheet.add_argument("--columns", type=int, default=6, help="provini per riga (default: 6)")
    p_sheet.add_argument("--width", type=int, default=180,
                         help="larghezza di ogni provino in pixel (default: 180)")
    p_sheet.set_defaults(func=cmd_sheet)

    p_templates = sub.add_parser("templates", help="elenca i template disponibili")
    p_templates.add_argument("directory", nargs="?", default="templates",
                             help="cartella che li contiene (default: templates)")
    p_templates.set_defaults(func=cmd_templates)

    p_slots = sub.add_parser(
        "slots",
        help="mostra i posti di un template e ne cambia i tagli",
        description="Senza opzioni elenca i posti. --cut, --split e --merge cambiano i "
                    "tagli e riscrivono il template.yaml: i numeri dei posti sono sempre "
                    "quelli dell'elenco di prima del comando. --video monta i posti "
                    "numerati sulla musica, per vedere e sentire dove cade ogni taglio.",
    )
    p_slots.add_argument("template", help="cartella del template (o il suo template.yaml)")
    p_slots.add_argument("--cut", nargs="+", action="extend", metavar="ISTANTE",
                         help="un taglio in piu' a questo istante (4.45 o 0:04.45), "
                              "allineato alla griglia del battito")
    p_slots.add_argument("--split", nargs="+", action="extend", type=int, metavar="POSTO",
                         help="divide il posto in parti uguali: due, o quante dice --into")
    p_slots.add_argument("--into", type=int, default=2,
                         help="in quante parti dividere con --split (default: 2)")
    p_slots.add_argument("--merge", nargs="+", action="extend", type=int, metavar="POSTO",
                         help="unisce il posto a quello prima: toglie il taglio con cui comincia")
    p_slots.add_argument("--grid", choices=("beat", "half", "quarter", "off"), default="half",
                         help="dove allineare i --cut: battiti, mezzi battiti (default), "
                              "quarti, o 'off' per lasciarli dove li scrivi")
    p_slots.add_argument("--video", action="store_true",
                         help="monta i posti numerati sulla musica (dopo le modifiche, "
                              "se ce ne sono)")
    p_slots.add_argument("-o", "--output",
                         help="il video dei posti (default: output/<template>-posti.mp4)")
    p_slots.set_defaults(func=cmd_slots)

    p_fonts = sub.add_parser("fonts", help="elenca i font utilizzabili per testo e sottotitoli")
    p_fonts.set_defaults(func=cmd_fonts)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Fino a Python 3.11 argparse non sa riprendere una lista di file DOPO
    # un'opzione: `vedit new edits/x --template t a.jpg b.jpg` lascia fuori
    # a.jpg e b.jpg come "argomenti non riconosciuti", mentre dalla 3.12 li
    # assegna ai media. Qui si raccolgono a mano, cosi' l'ordine non conta su
    # nessuna versione.
    args, extra = parser.parse_known_args(argv)
    if extra:
        if args.command in ("new", "apply") and not any(e.startswith("-") for e in extra):
            args.media = [*args.media, *extra]
        else:
            parser.error(f"argomenti non riconosciuti: {' '.join(extra)}")
    setup_logging(args.verbose)

    try:
        return args.func(args)
    except (ConfigError, FFmpegError, FileNotFoundError) as exc:
        print(f"\nErrore: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrotto.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
