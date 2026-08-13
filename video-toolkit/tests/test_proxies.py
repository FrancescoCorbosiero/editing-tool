"""
Test del flusso di lavoro con i proxy.

Qui serve un vero file video - un proxy di niente non si genera - ma non si
committa nessun media: il sorgente viene creato al volo con ffmpeg (`testsrc`
di lavfi) dentro una cartella temporanea. Se ffmpeg non c'e', questi test si
saltano invece di fallire.
"""

import shutil
import subprocess

import pytest

from vedit import proxies
from vedit.models import Project

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="serve ffmpeg per generare il sorgente di prova")


@pytest.fixture(scope="module")
def sorgente(tmp_path_factory):
    """Un video 1280x720 di un secondo: abbastanza alto da meritare un proxy."""
    path = tmp_path_factory.mktemp("media") / "ripresa.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path


@pytest.fixture
def progetto(sorgente, tmp_path):
    """Un progetto che usa quel sorgente due volte."""
    project = Project.from_dict({
        "output": {"size": [320, 180], "fps": 10},
        "timeline": [
            {"type": "video", "src": str(sorgente), "start": 0, "end": 0.5},
            {"type": "color", "duration": 1},
            {"type": "video", "src": str(sorgente), "start": 0.5, "end": 1.0},
        ],
    })
    project.root = tmp_path
    return project


# -- impronta ---------------------------------------------------------------

def test_l_impronta_e_stabile(sorgente):
    assert proxies.fingerprint(sorgente) == proxies.fingerprint(sorgente)


def test_l_impronta_cambia_se_cambia_il_contenuto(sorgente, tmp_path):
    copia = tmp_path / "copia.mp4"
    copia.write_bytes(sorgente.read_bytes())
    assert proxies.fingerprint(copia) == proxies.fingerprint(sorgente)

    copia.write_bytes(sorgente.read_bytes() + b"un byte in piu'")
    assert proxies.fingerprint(copia) != proxies.fingerprint(sorgente)


def test_l_impronta_distingue_file_della_stessa_dimensione(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x" * 5000)
    b.write_bytes(b"y" * 5000)
    assert proxies.fingerprint(a) != proxies.fingerprint(b)


# -- percorsi e cache -------------------------------------------------------

def test_il_nome_del_proxy_contiene_altezza_e_impronta(progetto, sorgente):
    path = proxies.proxy_path(progetto, sorgente)
    assert path.parent == progetto.root / "proxies"
    assert "480p" in path.name
    assert proxies.fingerprint(sorgente)[:12] in path.name


def test_altezze_diverse_convivono(progetto, sorgente):
    assert proxies.proxy_path(progetto, sorgente, 480) != \
           proxies.proxy_path(progetto, sorgente, 720)


def test_i_sorgenti_video_sono_elencati_una_volta_sola(progetto, sorgente):
    # Il sorgente compare in due segmenti, il terzo e' un colore.
    assert proxies.video_sources(progetto) == [sorgente]


def test_generazione_e_riuso(progetto, sorgente):
    assert proxies.find_proxy(progetto, sorgente) is None

    primo = proxies.ensure_proxy(progetto, sorgente)
    assert primo.created is True
    assert primo.proxy.exists()
    assert proxies.find_proxy(progetto, sorgente) == primo.proxy

    # Seconda chiamata: il file c'e' gia', non si rigenera niente.
    secondo = proxies.ensure_proxy(progetto, sorgente)
    assert secondo.created is False
    assert secondo.proxy == primo.proxy


def test_force_rigenera(progetto, sorgente):
    proxies.ensure_proxy(progetto, sorgente)
    assert proxies.ensure_proxy(progetto, sorgente, force=True).created is True


def test_un_sorgente_gia_piccolo_non_viene_proxato(progetto, sorgente):
    risultato = proxies.ensure_proxy(progetto, sorgente, height=1080)
    assert risultato.proxy is None
    assert "non serve" in risultato.status


def test_il_proxy_conserva_durata_e_proporzioni(progetto, sorgente):
    from vedit.ffmpeg_tools import probe

    risultato = proxies.ensure_proxy(progetto, sorgente)
    originale, proxy = probe(sorgente), probe(risultato.proxy)

    assert proxy["duration"] == pytest.approx(originale["duration"], abs=0.15)
    assert proxy["height"] == 480
    # Stesse proporzioni: altrimenti il montaggio verrebbe inquadrato diversamente
    assert proxy["width"] / proxy["height"] == pytest.approx(
        originale["width"] / originale["height"], abs=0.01)
    assert risultato.proxy.stat().st_size < sorgente.stat().st_size


# -- uso nel montaggio ------------------------------------------------------

def test_il_builder_usa_il_proxy_quando_c_e(progetto, sorgente):
    from vedit.builder import source_path

    seg = progetto.timeline[0]
    assert source_path(seg, progetto, use_proxy=False) == sorgente

    atteso = proxies.ensure_proxy(progetto, sorgente).proxy
    assert source_path(seg, progetto, use_proxy=True) == atteso


def test_senza_proxy_si_monta_sull_originale_con_un_avviso(progetto, sorgente, caplog):
    from vedit.builder import source_path

    with caplog.at_level("WARNING"):
        scelto = source_path(progetto.timeline[0], progetto, use_proxy=True)

    assert scelto == sorgente
    assert "Nessun proxy" in caplog.text


def test_il_montaggio_dai_proxy_ha_le_stesse_durate(progetto, sorgente):
    """La promessa del flusso: cambia la nitidezza, non il montaggio."""
    from vedit.builder import build, close_all

    proxies.ensure_proxy(progetto, sorgente)
    try:
        originale = build(progetto, use_proxy=False)
        durata_originale = originale.duration
        close_all()
        dal_proxy = build(progetto, use_proxy=True)
        assert dal_proxy.duration == pytest.approx(durata_originale, abs=0.05)
        assert tuple(dal_proxy.size) == tuple(originale.size)
    finally:
        close_all()
