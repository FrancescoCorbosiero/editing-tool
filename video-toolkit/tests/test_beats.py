"""
Test del rilevamento del battito.

Il materiale di prova si genera con ffmpeg a tempo NOTO, cosi' il test puo'
verificare il risultato invece di limitarsi a controllare che non esploda:
`aevalsrc` costruisce una cassa sintetica - una sinusoide a 60 Hz che decade -
che si ripete a un intervallo deciso da noi.
"""

import shutil
import subprocess

import numpy as np
import pytest

from vedit.beats import (
    BeatGrid,
    analyze,
    build_grid,
    decode,
    describe,
    detect_onsets,
    estimate_tempo,
    onset_envelope,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="serve ffmpeg per generare l'audio di prova")


def traccia(tmp_path, expr: str, nome: str, durata: int = 12):
    path = tmp_path / f"{nome}.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"aevalsrc={expr}:d={durata}:s=44100", str(path)], check=True)
    return path


def cassa(bpm: float) -> str:
    """Una grancassa a `bpm` battiti al minuto."""
    periodo = 60.0 / bpm
    return f"'sin(2*PI*60*t)*exp(-14*mod(t,{periodo:.6f}))'"


# -- tempo ------------------------------------------------------------------

@pytest.mark.parametrize("bpm", [90, 120, 140])
def test_riconosce_il_tempo(tmp_path, bpm):
    grid = analyze(traccia(tmp_path, cassa(bpm), f"cassa{bpm}"))
    assert abs(grid.bpm - bpm) < 1.5, f"atteso {bpm}, trovato {grid.bpm}"


def test_la_griglia_cade_sui_colpi(tmp_path):
    """Il tempo giusto non basta: la griglia deve stare anche in FASE."""
    grid = analyze(traccia(tmp_path, cassa(120), "fase"))
    veri = np.arange(0, 12, 0.5)          # i colpi sono a 0, 0.5, 1.0, ...
    errori = [min(abs(np.array(grid.beats) - v)) for v in veri[:20]]
    assert max(errori) < 0.03, f"griglia sfasata di {max(errori)*1000:.0f} ms"


def test_il_charleston_non_raddoppia_il_tempo(tmp_path):
    """
    Con un colpo secco a meta' di ogni battito, un rilevatore ingenuo legge il
    doppio del tempo. E' l'errore che rende inutilizzabili le griglie.
    """
    mix = ("'sin(2*PI*60*t)*exp(-14*mod(t,0.5))*0.9"
           "+random(0)*exp(-40*mod(t+0.25,0.5))*0.35"
           "+sin(2*PI*440*t)*0.25'")
    grid = analyze(traccia(tmp_path, mix, "mix"))
    assert abs(grid.bpm - 120) < 2, f"trovato {grid.bpm}, probabile errore di ottava"


def test_il_passa_basso_serve_davvero(tmp_path):
    """Documenta perche' isoliamo la cassa: senza filtro il tempo si sbaglia."""
    mix = ("'sin(2*PI*60*t)*exp(-14*mod(t,0.5))*0.9"
           "+random(0)*exp(-40*mod(t+0.25,0.5))*0.6"
           "+sin(2*PI*440*t)*0.4'")
    path = traccia(tmp_path, mix, "mix2")
    con = onset_envelope(decode(path, cutoff=150))
    senza = onset_envelope(decode(path, cutoff=None))
    bpm_con, _ = estimate_tempo(con)
    bpm_senza, _ = estimate_tempo(senza)
    assert abs(bpm_con - 120) < 2
    assert abs(bpm_con - 120) <= abs(bpm_senza - 120)


# -- colpi ------------------------------------------------------------------

def test_trova_i_colpi(tmp_path):
    onsets = detect_onsets(onset_envelope(decode(traccia(tmp_path, cassa(120), "colpi"))))
    assert 20 <= len(onsets) <= 26        # 24 colpi in 12 secondi
    intervalli = np.diff(onsets)
    assert abs(np.median(intervalli) - 0.5) < 0.03


def test_due_colpi_vicini_contano_uno(tmp_path):
    env = onset_envelope(decode(traccia(tmp_path, cassa(120), "gap")))
    fitti = detect_onsets(env, min_gap=0.01)
    radi = detect_onsets(env, min_gap=0.3)
    assert len(radi) <= len(fitti)


# -- casi limite ------------------------------------------------------------

def test_silenzio_non_esplode(tmp_path):
    grid = analyze(traccia(tmp_path, "'0'", "silenzio", durata=3))
    assert grid.bpm == 0 or grid.beats == [] or len(grid.onsets) == 0
    assert "battito" in describe(grid, "silenzio.wav").lower()


def test_traccia_troppo_corta():
    assert estimate_tempo(np.zeros(3)) == (0.0, 0.0)
    assert build_grid(0, 0, 10) == []


# -- la griglia come oggetto ------------------------------------------------

def test_operazioni_sulla_griglia():
    grid = BeatGrid(bpm=120, beats=[0.5, 1.0, 1.5, 2.0], duration=3.0)
    assert grid.period == 0.5
    assert grid.at(0) == 0.5
    assert grid.at(4) == 2.5             # oltre la fine della griglia
    assert grid.nearest(1.1) == 1.0
    assert grid.nearest(1.3) == 1.5


def test_il_referto_dice_le_cose_utili(tmp_path):
    testo = describe(analyze(traccia(tmp_path, cassa(120), "referto")), "prova.wav")
    assert "BPM" in testo
    assert "Battiti" in testo
    assert "battito" in testo            # la conversione battiti -> secondi
