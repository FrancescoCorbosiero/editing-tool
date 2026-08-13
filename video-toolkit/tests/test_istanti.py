"""
Test del montaggio a istanti (`at`).

Due modi di scrivere un montaggio: a durate (ogni segmento dice quanto dura) o
a istanti (ogni segmento dice quando entra). Il secondo esiste per una ragione
sola, ed e' il primo test qui sotto: spostare un taglio deve spostare QUEL
taglio, non tutti quelli che vengono dopo.
"""

import pytest

from vedit.builder import build, close_all
from vedit.models import ConfigError, Project
from vedit.timeline import durations_from_positions


def progetto(istanti, ultima_durata=1.0, **extra):
    """Un montaggio di colori agli istanti richiesti."""
    timeline = [
        {"type": "color", "at": t, "color": [i * 20 % 255, 0, 0]}
        for i, t in enumerate(istanti)
    ]
    timeline[-1]["duration"] = ultima_durata
    data = {"output": {"size": [160, 90], "fps": 10}, "timeline": timeline}
    data.update(extra)
    return Project.from_dict(data)


def posizioni_montate(project) -> list[float]:
    clip = build(project)
    try:
        return [round(c.start, 4) for c in clip.clips]
    finally:
        close_all()


# -- la ragione per cui esiste ----------------------------------------------

def test_spostare_un_taglio_non_muove_gli_altri():
    prima = posizioni_montate(progetto([0.0, 1.0, 2.0, 3.0]))
    dopo = posizioni_montate(progetto([0.0, 1.0, 2.4, 3.0]))

    assert prima == [0.0, 1.0, 2.0, 3.0]
    assert dopo == [0.0, 1.0, 2.4, 3.0]
    assert prima[3] == dopo[3], "il taglio successivo NON deve essersi mosso"


def test_le_durate_si_deducono_dagli_istanti():
    assert durations_from_positions([0.0, 1.0, 2.5, 4.0], last=2.0) == [1.0, 1.5, 1.5, 2.0]
    assert durations_from_positions([], last=1.0) == []
    assert durations_from_positions([0.0], last=3.0) == [3.0]


def test_la_durata_totale_e_l_ultimo_istante_piu_la_sua_coda():
    clip = build(progetto([0.0, 2.0, 3.0], ultima_durata=1.5))
    try:
        assert clip.duration == pytest.approx(4.5)
    finally:
        close_all()


def test_il_riepilogo_dice_le_stesse_cose_del_montaggio():
    """Se --check e il render divergessero, il riepilogo sarebbe inutile."""
    from vedit.report import analyze

    project = progetto([0.0, 0.8, 2.2], ultima_durata=1.0)
    report = analyze(project)
    inizi_report = [round(r.placement.start, 4) for r in report.rows]

    assert inizi_report == [0.0, 0.8, 2.2]
    clip = build(project)
    try:
        assert clip.duration == pytest.approx(report.duration)
    finally:
        close_all()


# -- errori che si vogliono leggere, non subire -----------------------------

def test_non_si_mescolano_durate_e_istanti():
    with pytest.raises(ConfigError, match="manca 'at'"):
        Project.from_dict({"timeline": [
            {"type": "color", "at": 0, "duration": 1},
            {"type": "color", "duration": 1},          # senza at
        ]}).validate_positions()


def test_il_primo_segmento_parte_da_zero():
    with pytest.raises(ConfigError, match="at: 0"):
        progetto([0.5, 1.5]).validate_positions()


def test_gli_istanti_devono_crescere():
    with pytest.raises(ConfigError, match="non viene dopo"):
        progetto([0.0, 2.0, 1.0]).validate_positions()


def test_istante_negativo():
    with pytest.raises(ConfigError, match="negativo"):
        Project.from_dict({"timeline": [{"type": "color", "at": -1, "duration": 1}]})


def test_le_transizioni_sovrapposte_non_convivono_con_gli_istanti():
    """
    Un crossfade tira indietro il clip che entra: sposterebbe proprio l'istante
    che `at` serve a fissare. Meglio un errore chiaro che un montaggio storto.
    """
    with pytest.raises(ConfigError, match="sovrappone"):
        progetto([0.0, 1.0], defaults={"transition": 0.5,
                                       "transition_type": "crossfade"}).validate_positions()


def test_le_transizioni_che_non_sovrappongono_vanno_bene():
    progetto([0.0, 1.0], defaults={"transition": 0.4,
                                   "transition_type": "fade_through_black"}).validate_positions()
    progetto([0.0, 1.0], defaults={"transition": 0.4,
                                   "transition_type": "cut"}).validate_positions()


# -- il taglio nel sorgente -------------------------------------------------

def test_dal_video_si_prende_esattamente_quanto_serve(tmp_path):
    """Senza `end`, la durata la decide il taglio successivo."""
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("serve ffmpeg")

    sorgente = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=size=160x90:rate=10:duration=6",
                    "-pix_fmt", "yuv420p", str(sorgente)], check=True)

    project = Project.from_dict({
        "output": {"size": [160, 90], "fps": 10},
        "timeline": [
            {"type": "video", "at": 0.0, "src": str(sorgente), "start": 1.0},
            {"type": "video", "at": 1.5, "src": str(sorgente), "start": 4.0, "end": 4.5},
        ],
    })
    project.root = tmp_path

    clip = build(project)
    try:
        assert clip.clips[0].duration == pytest.approx(1.5, abs=0.05)
        assert clip.duration == pytest.approx(2.0, abs=0.05)
    finally:
        close_all()
