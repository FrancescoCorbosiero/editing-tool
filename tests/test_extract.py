"""
Test dell'estrazione di un template da un video di riferimento.

Il materiale si costruisce a tavolino: tinte piatte che cambiano a istanti noti,
sopra una cassa a un tempo noto. Cosi' si puo' verificare la cosa che conta -
che i tagli finiscano sui battiti - invece di controllare solo che il comando
non esploda.
"""

import shutil
import subprocess

import pytest

from vedit.beats import BeatGrid
from vedit.extract import (
    MOTION_MIN_SLOT,
    build_slots,
    describe,
    drop_short,
    extract,
    motion_amount,
    render,
    snap,
    subdivisions,
)
from vedit.scenes import ShotList
from vedit.templates import Template, TemplateError

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="serve ffmpeg per generare i video di prova")

COLORI = ["red", "blue", "yellow", "magenta", "cyan", "white"]


def video_montato(tmp_path, durate, bpm: float = 120.0, nome: str = "riferimento.mp4",
                  con_audio: bool = True):
    """
    Un video con tagli agli istanti noti e, sopra, una grancassa a `bpm`.

    L'espressione della cassa e' la stessa di test_beats.py: una sinusoide a
    60 Hz che decade, ripetuta a intervalli regolari.
    """
    path = tmp_path / nome
    ingressi: list[str] = []
    for i, durata in enumerate(durate):
        ingressi += ["-f", "lavfi",
                     "-i", f"color=c={COLORI[i % len(COLORI)]}:s=160x90:r=30:d={durata}"]

    catena = "".join(f"[{i}:v]" for i in range(len(durate)))
    filtro = f"{catena}concat=n={len(durate)}:v=1:a=0[v]"
    comando = ["ffmpeg", "-y", "-v", "error", *ingressi]

    if con_audio:
        periodo = 60.0 / bpm
        totale = sum(durate)
        comando += ["-f", "lavfi",
                    "-i", f"aevalsrc='sin(2*PI*60*t)*exp(-14*mod(t,{periodo:.6f}))'"
                          f":d={totale}:s=44100"]

    comando += ["-filter_complex", filtro, "-map", "[v]"]
    if con_audio:
        comando += ["-map", f"{len(durate)}:a", "-c:a", "aac"]
    comando += ["-pix_fmt", "yuv420p", str(path)]

    subprocess.run(comando, check=True)
    return path


# -- l'allineamento al battito ----------------------------------------------

def test_un_taglio_vicino_al_battito_ci_viene_portato():
    griglia = [0.0, 0.5, 1.0, 1.5, 2.0]
    allineati, spostati, medio = snap([0.52, 1.03], griglia, step=0.5)

    assert allineati == [0.5, 1.0]
    assert spostati == 2
    assert medio == pytest.approx(0.025, abs=0.005)


def test_un_taglio_lontano_dal_battito_resta_dov_e():
    """
    Un taglio a meta' fra due battiti non e' sbagliato: e' in levare, ed e' una
    scelta di chi ha montato. Spostarlo rovinerebbe il montaggio invece di
    ripararlo.
    """
    griglia = [0.0, 0.5, 1.0]
    allineati, spostati, _ = snap([0.75], griglia, step=0.5)

    assert allineati == [0.75]
    assert spostati == 0


def test_senza_griglia_non_si_allinea_niente():
    allineati, spostati, _ = snap([0.31, 0.77], [], step=0.0)
    assert allineati == [0.31, 0.77]
    assert spostati == 0


def test_due_tagli_sullo_stesso_battito_diventano_uno():
    allineati, _, _ = snap([0.48, 0.52], [0.0, 0.5, 1.0], step=0.5)
    assert allineati == [0.5]


def test_la_griglia_si_suddivide_come_richiesto():
    grid = BeatGrid(bpm=120.0, beats=[0.0, 0.5, 1.0, 1.5, 2.0], duration=2.0)

    battiti, passo = subdivisions(grid, divisions=1, duration=2.0)
    assert passo == pytest.approx(0.5)
    assert 1.0 in battiti and 0.75 not in battiti

    mezzi, passo = subdivisions(grid, divisions=2, duration=2.0)
    assert passo == pytest.approx(0.25)
    assert 0.75 in mezzi


def test_senza_battito_non_c_e_niente_su_cui_allineare():
    valori, passo = subdivisions(BeatGrid(bpm=0.0), divisions=2, duration=5.0)
    assert valori == []
    assert passo == 0.0


# -- gli slot troppo corti --------------------------------------------------

def test_gli_slot_troppo_corti_vengono_assorbiti():
    tenuti, scartati = drop_short([1.0, 1.05, 2.0], duration=3.0, minimum=0.25)
    assert tenuti == [1.0, 2.0]
    assert scartati == 1


def test_anche_l_ultimo_slot_deve_essere_abbastanza_lungo():
    tenuti, scartati = drop_short([1.0, 2.95], duration=3.0, minimum=0.25)
    assert tenuti == [1.0]
    assert scartati == 1


# -- il movimento suggerito -------------------------------------------------

def test_il_movimento_cresce_con_la_durata_dello_slot():
    """Stessa quantita' su durate diverse sono due effetti diversi."""
    assert motion_amount(0.5) < motion_amount(2.0) < motion_amount(10.0)
    assert motion_amount(0.1) == pytest.approx(0.05)     # il minimo
    assert motion_amount(100) == pytest.approx(0.25)     # il massimo


def test_gli_slot_brevissimi_restano_fermi():
    """Un movimento di due decimi di secondo si legge come un tremolio."""
    shots = ShotList(duration=2.0)
    slots = build_slots([0.3], shots, duration=0.6)
    assert all(s.motion is None for s in slots)


def test_gli_slot_lunghi_ricevono_un_movimento():
    shots = ShotList(duration=6.0)
    slots = build_slots([3.0], shots, duration=6.0)

    assert slots[0].motion is not None
    assert slots[1].motion is not None
    # Alternati, cosi' dieci foto di fila non zoomano tutte nello stesso verso.
    assert slots[0].motion != slots[1].motion


def test_la_soglia_del_movimento_e_la_durata_dello_slot():
    """Sopra la soglia si muove, sotto no: e' l'unica differenza fra i due."""
    sopra = MOTION_MIN_SLOT + 0.2
    sotto = MOTION_MIN_SLOT - 0.2

    lunghi = build_slots([sopra], ShotList(), duration=sopra * 2)
    brevi = build_slots([sotto], ShotList(), duration=sotto * 2)

    assert all(s.motion is not None for s in lunghi)
    assert all(s.motion is None for s in brevi)


# -- l'estrazione vera ------------------------------------------------------

def test_estrae_un_template_completo(tmp_path):
    sorgente = video_montato(tmp_path, [2.0, 2.0, 2.0])
    result = extract(sorgente, tmp_path / "tpl")

    assert (tmp_path / "tpl" / "template.yaml").exists()
    assert (tmp_path / "tpl" / "audio.m4a").exists()

    template = result.template
    assert len(template.slots) == 3
    assert template.size == (160, 90)
    assert template.fps == 30
    assert template.duration == pytest.approx(6.0, abs=0.1)
    assert abs(template.audio.bpm - 120.0) < 2


def test_gli_slot_cadono_sui_tagli_del_riferimento(tmp_path):
    sorgente = video_montato(tmp_path, [2.0, 1.5, 2.5])
    result = extract(sorgente, tmp_path / "tpl")

    istanti = [s.at for s in result.template.slots]
    assert len(istanti) == 3
    for trovato, atteso in zip(istanti, [0.0, 2.0, 3.5], strict=True):
        assert abs(trovato - atteso) < 0.1, f"slot a {trovato}, atteso {atteso}"


def test_il_template_estratto_si_rilegge(tmp_path):
    """Il giro completo: quello che si scrive deve poter rientrare."""
    sorgente = video_montato(tmp_path, [2.0, 2.0])
    result = extract(sorgente, tmp_path / "tpl")

    riletto = Template.from_yaml(tmp_path / "tpl")
    assert riletto.name == result.template.name
    assert riletto.duration == pytest.approx(result.template.duration)
    assert [s.at for s in riletto.slots] == [s.at for s in result.template.slots]


def test_dal_template_estratto_si_monta_davvero(tmp_path):
    """
    Il giro che conta per chi lo usa: estrai, applichi ai tuoi file, e quello
    che ne esce e' un progetto valido con i tagli al posto giusto.
    """
    from vedit.templates import MediaRef, bind

    sorgente = video_montato(tmp_path, [2.0, 1.5, 2.5])
    result = extract(sorgente, tmp_path / "tpl")

    foto = tmp_path / "foto.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=green:s=320x180:d=1", "-frames:v", "1", str(foto)],
                   check=True)

    bound = bind(result.template, [MediaRef(foto)], root=tmp_path)
    project = bound.project(tmp_path)
    project.validate_positions()
    project.validate_files()

    assert project.cut_positions() == [s.at for s in result.template.slots]


def test_un_video_senza_audio_non_produce_un_template_audio(tmp_path):
    sorgente = video_montato(tmp_path, [1.0, 1.0], con_audio=False)
    with pytest.raises(TemplateError, match="non ha una traccia audio"):
        extract(sorgente, tmp_path / "tpl")


def test_non_si_sovrascrive_un_template_per_sbaglio(tmp_path):
    sorgente = video_montato(tmp_path, [2.0, 2.0])
    extract(sorgente, tmp_path / "tpl")

    with pytest.raises(TemplateError, match="--force"):
        extract(sorgente, tmp_path / "tpl")

    extract(sorgente, tmp_path / "tpl", force=True)      # con --force si puo'


def test_una_griglia_inesistente_si_dice_subito(tmp_path):
    sorgente = video_montato(tmp_path, [1.0, 1.0])
    with pytest.raises(TemplateError, match="Griglia 'terzine' sconosciuta"):
        extract(sorgente, tmp_path / "tpl", grid="terzine")


def test_le_transizioni_richieste_finiscono_negli_slot(tmp_path):
    sorgente = video_montato(tmp_path, [2.0, 2.0, 2.0])
    result = extract(sorgente, tmp_path / "tpl", transition=0.3,
                     transition_type="crossfade")

    slots = result.template.slots
    assert slots[0].transition == 0.0          # il primo non entra da niente
    assert all(s.transition == pytest.approx(0.3) for s in slots[1:])
    assert all(s.transition_type == "crossfade" for s in slots[1:])


def test_il_template_scritto_e_commentato(tmp_path):
    """
    Un template e' un elenco di numeri: senza commenti nessuno lo correggera'.
    """
    sorgente = video_montato(tmp_path, [2.0, 2.0])
    result = extract(sorgente, tmp_path / "tpl")

    testo = (tmp_path / "tpl" / "template.yaml").read_text(encoding="utf-8")
    assert "TEMPLATE AUDIO" in testo
    assert "battiti" in testo
    assert "vedit apply" in testo
    # E deve restare YAML valido, non solo bello da leggere.
    assert render(result.template) is not None


def test_il_riepilogo_dice_quanti_media_servono(tmp_path):
    sorgente = video_montato(tmp_path, [2.0, 1.5, 2.5])
    result = extract(sorgente, tmp_path / "tpl")

    testo = describe(result, tmp_path / "tpl")
    assert "Servono 3 media" in testo
    assert "BPM" in testo
