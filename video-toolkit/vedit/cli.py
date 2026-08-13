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
