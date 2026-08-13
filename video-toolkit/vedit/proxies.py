"""
Proxy: copie leggere dei sorgenti, per montare senza aspettare.

Montare su file 4K e' insopportabile perche' ogni fotogramma va decodificato,
ridimensionato e ricomposto: la macchina passa il tempo a fare lavoro che
verra' buttato via al prossimo tentativo. Il rimedio standard nei software di
montaggio si chiama **proxy**: si genera una volta una versione a bassa
risoluzione di ogni sorgente, si monta su quella, e l'export finale torna agli
originali. Il montaggio non cambia - tagli, transizioni e durate lavorano sul
tempo, non sui pixel - cambia solo quanto si aspetta.

    python -m vedit proxy progetto.yaml           # genera i proxy
    python -m vedit render progetto.yaml --preview --use-proxy
    python -m vedit render progetto.yaml          # export finale: originali

I proxy finiscono in `proxies/`, accanto al file di progetto, e il nome contiene
un'impronta del contenuto del sorgente: se il file originale cambia, cambia
l'impronta, il proxy vecchio non viene piu' trovato e ne nasce uno nuovo. Non
serve nessun controllo di "e' aggiornato?", e non c'e' modo di montare per
sbaglio su un proxy che non corrisponde piu' al suo originale.

Modulo senza MoviePy: qui si ragiona su file e si chiama ffmpeg.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg_tools import make_proxy, probe
from .models import Project

PROXY_DIR_NAME = "proxies"
DEFAULT_HEIGHT = 480

# Quanto leggere da testa e coda per l'impronta.
CHUNK = 1024 * 1024


def fingerprint(path: Path) -> str:
    """
    Impronta del contenuto di un file: dimensione + primo e ultimo MiB.

    Non si legge tutto il file di proposito. Su un video di 20 GB l'hash
    completo costerebbe decine di secondi *ogni volta* che si controlla la
    cache, cioe' esattamente il tempo che i proxy servono a risparmiare.
    Dimensione esatta piu' due estremi di un mega bastano ampiamente: due
    riprese diverse che coincidono su tutti e tre non esistono nella pratica,
    e una riesportazione dello stesso video cambia sempre almeno la coda.
    """
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())

    with path.open("rb") as fh:
        digest.update(fh.read(CHUNK))
        if size > 2 * CHUNK:
            fh.seek(-CHUNK, 2)
            digest.update(fh.read(CHUNK))

    return digest.hexdigest()


def proxy_dir(project: Project) -> Path:
    """La cartella dei proxy, accanto al file di progetto."""
    return project.root / PROXY_DIR_NAME


def proxy_path(project: Project, source: Path, height: int = DEFAULT_HEIGHT) -> Path:
    """
    Dove sta (o dove andra') il proxy di questo sorgente.

    L'altezza fa parte del nome: cambiare `--height` non invalida i proxy
    gia' fatti, li affianca.
    """
    source = project.resolve(source)
    return proxy_dir(project) / f"{source.stem}-{height}p-{fingerprint(source)[:12]}.mp4"


def video_sources(project: Project) -> list[Path]:
    """I sorgenti video del progetto, senza ripetizioni e nell'ordine d'uso."""
    seen: dict[Path, None] = {}
    for seg in project.timeline:
        if seg.type == "video" and seg.src is not None:
            seen.setdefault(project.resolve(seg.src), None)
    return list(seen)


def find_proxy(project: Project, source: Path, height: int = DEFAULT_HEIGHT) -> Path | None:
    """Il proxy di questo sorgente, se e' gia' stato generato."""
    resolved = project.resolve(source)
    if not resolved.exists():
        return None
    candidate = proxy_path(project, resolved, height)
    return candidate if candidate.exists() else None


@dataclass
class ProxyResult:
    """Esito della generazione di un singolo proxy."""

    source: Path
    proxy: Path | None
    created: bool
    skipped_reason: str = ""

    @property
    def status(self) -> str:
        if self.skipped_reason:
            return self.skipped_reason
        return "creato" if self.created else "gia' presente"


def ensure_proxy(project: Project, source: Path, height: int = DEFAULT_HEIGHT,
                 force: bool = False) -> ProxyResult:
    """Genera il proxy di un sorgente, se non c'e' gia' (o se `force`)."""
    source = project.resolve(source)
    target = proxy_path(project, source, height)

    if target.exists() and not force:
        return ProxyResult(source=source, proxy=target, created=False)

    info = probe(source)
    if info.get("height") and info["height"] <= height:
        # Un sorgente gia' piccolo non ha bisogno di essere rimpicciolito:
        # si monta direttamente su di lui.
        return ProxyResult(source=source, proxy=None, created=False,
                           skipped_reason=f"gia' a {info['height']}p, non serve")

    make_proxy(source, target, height=height)
    return ProxyResult(source=source, proxy=target, created=True)


def build_all(project: Project, height: int = DEFAULT_HEIGHT, force: bool = False,
              on_start=None, on_done=None) -> list[ProxyResult]:
    """
    Genera i proxy di tutti i sorgenti video del progetto.

    I due callback servono a raccontare cosa succede mentre succede: generare
    un proxy di un file lungo puo' durare minuti, e un comando muto sembra
    bloccato.
    """
    results = []
    for source in video_sources(project):
        if on_start is not None:
            on_start(source)
        result = ensure_proxy(project, source, height=height, force=force)
        if on_done is not None:
            on_done(result)
        results.append(result)
    return results


def total_size(results: list[ProxyResult]) -> int:
    """Byte occupati dai proxy prodotti o riusati."""
    return sum(r.proxy.stat().st_size for r in results if r.proxy and r.proxy.exists())
