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


def cmd_render(args: argparse.Namespace) -> int:
    from .builder import close_all, render  # import pigro: MoviePy e' lento da caricare

    ensure_ffmpeg()
    project = Project.from_yaml(args.project)

    if args.output:
        project.output.path = Path(args.output)

    try:
        target = render(project, dry_run=args.dry_run, preview=args.preview)
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
    p_render.set_defaults(func=cmd_render)

    p_probe = sub.add_parser("probe", help="mostra i metadati di un file")
    p_probe.add_argument("path")
    p_probe.add_argument("--json", action="store_true")
    p_probe.set_defaults(func=cmd_probe)

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
