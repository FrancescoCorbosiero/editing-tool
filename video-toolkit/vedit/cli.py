"""
Interfaccia da riga di comando.

    python -m vedit render projects/demo/timeline.yaml
    python -m vedit render projects/demo/timeline.yaml --preview
    python -m vedit probe assets/input.mp4
    python -m vedit init progetti/mio-video
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from .ffmpeg_tools import FFmpegError, ensure_ffmpeg, probe
from .models import ConfigError, Project

TEMPLATE = Path(__file__).resolve().parent.parent / "projects" / "demo" / "timeline.yaml"


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def load_project(args: argparse.Namespace) -> Project:
    """
    Carica il progetto e verifica in blocco che i file referenziati esistano.

    La verifica sta qui e non nel builder perche' deve avvenire PRIMA di
    costruire qualsiasi cosa: meglio quattro percorsi sbagliati elencati
    subito che un errore alla volta dopo trenta secondi di lavoro buttato.
    """
    project = Project.from_yaml(args.project)
    project.validate_files()
    return project


def cmd_render(args: argparse.Namespace) -> int:
    ensure_ffmpeg()
    project = load_project(args)

    if args.output:
        project.output.path = Path(args.output)

    if args.check:
        # --check non renderizza: niente import di MoviePy, che costa secondi.
        from .report import analyze, format_report

        print(format_report(analyze(project, args.project)))
        return 0

    from .builder import close_all, render  # import pigro: MoviePy e' lento da caricare

    try:
        target = render(project, dry_run=args.dry_run, preview=args.preview,
                        use_proxy=args.use_proxy)
    finally:
        close_all()

    if target and target.exists():
        size_mb = target.stat().st_size / 1_000_000
        print(f"\nFatto: {target}  ({size_mb:.1f} MB)")
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


def cmd_proxy(args: argparse.Namespace) -> int:
    """Genera le copie leggere dei sorgenti su cui montare."""
    import time

    from .proxies import build_all, proxy_dir, total_size

    ensure_ffmpeg()
    project = load_project(args)

    started = time.monotonic()
    print(f"Proxy a {args.height}p in {proxy_dir(project)}\n")

    # La riga "in corso" si riscrive solo se siamo in un terminale: dentro un
    # file di log il ritorno carrello non cancella niente e sporca l'output.
    tty = sys.stdout.isatty()

    def annuncia(source: Path) -> None:
        if tty:
            print(f"  {source.name:<40} in corso...", end="\r", flush=True)

    def riporta(result) -> None:
        print(f"  {result.source.name:<40} {result.status}".ljust(70))

    results = build_all(project, height=args.height, force=args.force,
                        on_start=annuncia, on_done=riporta)

    creati = sum(1 for r in results if r.created)
    elapsed = time.monotonic() - started
    print(
        f"\n{len(results)} {'sorgente' if len(results) == 1 else 'sorgenti'} · "
        f"{creati} generati ora · {total_size(results) / 1_000_000:.1f} MB in "
        f"{proxy_dir(project).name}/ · {elapsed:.1f}s"
    )
    if results:
        print("Ora monta con: python -m vedit render "
              f"{args.project} --preview --use-proxy")
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
              f"{template.size[0]}x{template.size[1]}")
    return 0


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

    # Le durate servono a scoprire SUBITO che un video e' troppo corto per lo
    # slot in cui e' finito, invece che a meta' export.
    durate: dict[Path, float] = {}
    for ref in media:
        percorso = ref.path.resolve()
        if ref.kind == "video" and percorso not in durate:
            durate[percorso] = probe(percorso)["duration"]

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


def cmd_fonts(args: argparse.Namespace) -> int:
    """Elenca i font utilizzabili: senza un font il testo su video non si disegna."""
    from .fonts import describe

    print(describe())
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "timeline.yaml"

    if target.exists() and not args.force:
        print(f"Esiste gia': {target}  (usa --force per sovrascrivere)", file=sys.stderr)
        return 1

    shutil.copy(TEMPLATE, target)
    print(f"Creato {target}")
    print("Metti i tuoi file in assets/ e lancia:")
    print(f"  python -m vedit render {target} --preview")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vedit",
        description="Montaggio video dichiarativo: da un file YAML a un mp4.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log dettagliato")
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="renderizza un progetto")
    p_render.add_argument("project", help="percorso del timeline.yaml")
    p_render.add_argument("-o", "--output", help="sovrascrive output.path del YAML")
    p_render.add_argument("--preview", action="store_true",
                          help="anteprima veloce a bassa risoluzione")
    p_render.add_argument("--dry-run", action="store_true",
                          help="costruisce la timeline senza esportare (valida il YAML)")
    p_render.add_argument("--check", action="store_true",
                          help="valida il progetto e stampa il riepilogo della timeline, "
                               "senza costruire ne' esportare nulla")
    p_render.add_argument("--use-proxy", action="store_true",
                          help="monta sui proxy invece che sui sorgenti originali "
                               "(generali prima con `vedit proxy`)")
    p_render.set_defaults(func=cmd_render)

    p_probe = sub.add_parser("probe", help="mostra i metadati di un file")
    p_probe.add_argument("path")
    p_probe.add_argument("--json", action="store_true")
    p_probe.set_defaults(func=cmd_probe)

    p_proxy = sub.add_parser("proxy", help="genera copie leggere dei sorgenti su cui montare")
    p_proxy.add_argument("project", help="percorso del timeline.yaml")
    p_proxy.add_argument("--height", type=int, default=480,
                         help="altezza dei proxy in pixel (default: 480)")
    p_proxy.add_argument("--force", action="store_true",
                         help="rigenera anche i proxy gia' presenti")
    p_proxy.set_defaults(func=cmd_proxy)

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
    p_extract.add_argument("--min-slot", type=float, default=0.25,
                           help="durata minima di uno slot: i tagli piu' fitti vengono "
                                "scartati (default: 0.25)")
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

    p_templates = sub.add_parser("templates", help="elenca i template disponibili")
    p_templates.add_argument("directory", nargs="?", default="templates",
                             help="cartella che li contiene (default: templates)")
    p_templates.set_defaults(func=cmd_templates)

    p_fonts = sub.add_parser("fonts", help="elenca i font utilizzabili per testo e sottotitoli")
    p_fonts.set_defaults(func=cmd_fonts)

    p_init = sub.add_parser("init", help="crea un nuovo progetto da template")
    p_init.add_argument("directory")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
