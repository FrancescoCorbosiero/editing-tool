"""
Test del rilevamento dei tagli.

Come per i battiti, il materiale si genera con ffmpeg a istanti NOTI: un video
di tinte piatte che cambiano a tempi decisi da noi. Cosi' il test puo' dire
"il taglio doveva cadere a 2.0s" invece di limitarsi a controllare che il
codice non esploda.
"""

import shutil
import subprocess

import numpy as np
import pytest

from vedit.scenes import (
    BINS,
    Shot,
    _best_shift,
    analyze,
    build_shots,
    decode_frames,
    detect_cuts,
    differences,
    estimate_drift,
    histograms,
    suggest_motion,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="serve ffmpeg per generare i video di prova")

COLORI = ["red", "green", "blue", "yellow", "magenta", "cyan"]


def video_a_tinte(tmp_path, durate: list[float], nome: str = "tagli", rate: int = 30):
    """
    Un video fatto di tinte piatte che si susseguono, senza audio.

    I tagli cadono alle somme progressive delle durate: e' il dato che i test
    confrontano con quello che trova il rilevatore.
    """
    path = tmp_path / f"{nome}.mp4"
    ingressi = []
    for i, durata in enumerate(durate):
        ingressi += ["-f", "lavfi",
                     "-i", f"color=c={COLORI[i % len(COLORI)]}:s=160x90:r={rate}:d={durata}"]
    catena = "".join(f"[{i}:v]" for i in range(len(durate)))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *ingressi,
         "-filter_complex", f"{catena}concat=n={len(durate)}:v=1:a=0[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


# -- la matematica, senza file ----------------------------------------------

def test_istogrammi_normalizzati():
    frames = np.zeros((3, 4, 4, 3), dtype=np.uint8)
    frames[1] = 255
    hists = histograms(frames)

    # Un istogramma per canale, messi in fila in un vettore solo.
    assert hists.shape == (3, BINS * 3)
    assert np.allclose(hists.sum(axis=1), 1.0)
    # Tutto nero: il primo livello di ognuno dei tre canali si prende un terzo.
    assert hists[0][0] == pytest.approx(1 / 3)
    assert hists[1][BINS - 1] == pytest.approx(1 / 3)      # tutto bianco


def test_la_differenza_e_uno_fra_due_fotogrammi_senza_niente_in_comune():
    frames = np.zeros((2, 4, 4, 3), dtype=np.uint8)
    frames[1] = 255
    assert differences(histograms(frames))[0] == pytest.approx(1.0)


def test_due_fotogrammi_identici_non_differiscono():
    frames = np.full((2, 4, 4, 3), 128, dtype=np.uint8)
    assert differences(histograms(frames))[0] == pytest.approx(0.0)


def test_il_movimento_interno_non_e_un_taglio():
    """
    La ragione per cui si confrontano gli istogrammi e non i pixel: qui il
    contenuto si sposta di mezzo fotogramma, ma la quantita' di chiaro e di
    scuro non cambia. Un confronto pixel per pixel griderebbe al taglio.
    """
    base = np.zeros((10, 20, 20, 3), dtype=np.uint8)
    for i in range(10):
        base[i, :, i:i + 5] = 255      # una banda bianca che scorre

    assert differences(histograms(base)).max() < 0.05


def test_un_lampo_non_diventa_due_inquadrature():
    """min_shot: due tagli a un fotogramma di distanza sono lo stesso taglio."""
    diff = np.zeros(60)
    diff[30] = 1.0
    diff[31] = 0.8

    cuts = detect_cuts(diff, fps=30, min_shot=0.2)
    assert len(cuts) == 1


def test_senza_materiale_non_inventa_tagli():
    assert detect_cuts(np.zeros(0), fps=30) == []
    assert detect_cuts(np.zeros(50), fps=0) == []


def test_le_inquadrature_coprono_tutto_il_video():
    shots = build_shots([2.0, 5.0], duration=8.0)
    assert [(s.start, s.end) for s in shots] == [(0.0, 2.0), (2.0, 5.0), (5.0, 8.0)]
    assert sum(s.duration for s in shots) == pytest.approx(8.0)


# -- lo scorrimento ---------------------------------------------------------

def test_riconosce_di_quanto_e_scivolato_il_contenuto():
    profilo = np.zeros(64)
    profilo[20:30] = 1.0
    spostato = np.roll(profilo, 6)

    assert _best_shift(profilo, spostato) == pytest.approx(-6)
    assert _best_shift(spostato, profilo) == pytest.approx(6)


def test_su_due_immagini_senza_niente_in_comune_non_si_pronuncia():
    """Meglio "non lo so" che un movimento inventato."""
    a = np.zeros(64)
    a[10:20] = 1.0
    b = np.random.default_rng(0).normal(size=64) * 0.01
    assert _best_shift(a, b) == 0.0


def test_lo_scorrimento_si_misura_in_frazione_del_quadro():
    primo = np.zeros((20, 40), dtype=np.uint8)
    primo[:, 5:15] = 255
    ultimo = np.zeros((20, 40), dtype=np.uint8)
    ultimo[:, 15:25] = 255        # il contenuto si e' spostato di 10 su 40 = 0.25

    dx, dy = estimate_drift(primo, ultimo)
    assert dx == pytest.approx(0.25)
    assert dy == pytest.approx(0.0)


def test_il_movimento_suggerito_e_quello_della_camera_non_del_contenuto():
    """Se il contenuto va a destra, e' la camera che va a sinistra."""
    assert suggest_motion((0.3, 0.0), "zoom_in") == "pan_left"
    assert suggest_motion((-0.3, 0.0), "zoom_in") == "pan_right"
    assert suggest_motion((0.0, 0.3), "zoom_in") == "pan_up"
    assert suggest_motion((0.0, -0.3), "zoom_in") == "pan_down"
    # Sotto la soglia non c'e' movimento da imitare: vale il ripiego.
    assert suggest_motion((0.01, 0.01), "zoom_in") == "zoom_in"


# -- su file veri -----------------------------------------------------------

def test_trova_i_tagli_dove_sono(tmp_path):
    path = video_a_tinte(tmp_path, [2.0, 1.5, 2.5, 1.0])
    result = analyze(path)

    attesi = [2.0, 3.5, 6.0]
    assert len(result.cuts) == len(attesi), f"trovati {result.cuts}"
    for trovato, atteso in zip(result.cuts, attesi, strict=True):
        assert abs(trovato - atteso) < 0.07, f"taglio a {trovato}, atteso {atteso}"


def test_un_video_di_una_sola_inquadratura_non_ha_tagli(tmp_path):
    path = video_a_tinte(tmp_path, [3.0])
    result = analyze(path)

    assert result.cuts == []
    assert result.count == 1
    assert result.shots[0].duration == pytest.approx(3.0, abs=0.1)


def test_legge_il_formato_del_video(tmp_path):
    path = video_a_tinte(tmp_path, [1.0, 1.0])
    result = analyze(path)

    assert result.size == (160, 90)
    assert result.fps == pytest.approx(30)
    assert result.duration == pytest.approx(2.0, abs=0.1)


def test_i_fotogrammi_decodificati_sono_piccoli_e_a_colori(tmp_path):
    path = video_a_tinte(tmp_path, [1.0])
    frames = decode_frames(path)

    assert frames.ndim == 4
    assert frames.shape[1:] == (36, 64, 3)
    assert frames.dtype == np.uint8


def test_distingue_due_colori_di_uguale_luminosita(tmp_path):
    """
    Il caso che la versione in scala di grigi sbagliava: il rosso pieno e il
    verde scuro del CSS hanno praticamente la stessa luminosita\'.
    """
    path = tmp_path / "stessa_luce.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=red:s=160x90:r=30:d=1.5",
         "-f", "lavfi", "-i", "color=c=green:s=160x90:r=30:d=1.5",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    result = analyze(path)

    assert len(result.cuts) == 1, f"trovati {result.cuts}"
    assert abs(result.cuts[0] - 1.5) < 0.07


def test_il_riepilogo_regge_un_video_senza_inquadrature():
    from vedit.scenes import ShotList, describe

    testo = describe(ShotList(), "vuoto.mp4")
    assert "Nessuna inquadratura" in testo


def test_il_riepilogo_elenca_le_inquadrature():
    from vedit.scenes import ShotList, describe

    result = ShotList(cuts=[1.0], shots=[Shot(0, 0.0, 1.0), Shot(1, 1.0, 3.0)],
                      duration=3.0, fps=30, size=(1920, 1080))
    testo = describe(result, "prova.mp4")

    assert "2 inquadrature" in testo
    assert "1920x1080" in testo
