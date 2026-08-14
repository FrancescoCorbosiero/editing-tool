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


def test_una_dissolvenza_non_puo_partire_prima_del_taglio_precedente():
    """
    Il limite fisico: si dissolve DA qualcosa, e quel qualcosa deve essere in
    scena. Una dissolvenza piu' lunga dello spazio fra i due istanti comincerebbe
    prima che esista il clip da cui dissolvere.
    """
    with pytest.raises(ConfigError, match="non puo' cominciare prima"):
        progetto([0.0, 0.4], defaults={"transition": 0.9,
                                       "transition_type": "crossfade"}).validate_positions()


def test_le_transizioni_che_non_sovrappongono_vanno_bene():
    progetto([0.0, 1.0], defaults={"transition": 0.4,
                                   "transition_type": "fade_through_black"}).validate_positions()
    progetto([0.0, 1.0], defaults={"transition": 0.4,
                                   "transition_type": "cut"}).validate_positions()


# -- dissolvenze senza perdere il tempo di musica ---------------------------

def test_una_dissolvenza_non_sposta_gli_istanti():
    """
    Il punto di tutto il montaggio a tempo: mettere un crossfade su un taglio
    che cade sul battito non deve spostare quel taglio (ne' i successivi).
    Il clip che entra parte in ANTICIPO, e a `at` e' completamente in scena.
    """
    secco = progetto([0.0, 1.0, 2.0], defaults={"transition_type": "cut"})
    dissolto = progetto([0.0, 1.0, 2.0], defaults={"transition": 0.4,
                                                   "transition_type": "crossfade"})

    from vedit.report import analyze

    tagli_secchi = [round(r.placement.start, 4) for r in analyze(secco).rows]
    righe = analyze(dissolto).rows

    assert tagli_secchi == [0.0, 1.0, 2.0]
    # I clip partono prima, ma l'istante dichiarato non si e' mosso di un frame:
    # e' li' che la dissolvenza finisce di entrare.
    assert [round(r.placement.start, 4) for r in righe] == [0.0, 0.6, 1.6]
    # L'ultimo mostra il secondo che ha dichiarato, 0.4 dei quali se ne vanno
    # nell'entrata: finisce quindi a 2.6, non a 3.
    assert [round(r.placement.end, 4) for r in righe] == [1.0, 2.0, 2.6]


def test_a_durate_lo_stesso_progetto_perderebbe_il_tempo():
    """
    Il confronto che spiega perche' esistono due modi di posizionare.

    Stessi tre segmenti, stessa dissolvenza. A durate ogni sovrapposizione
    ANTICIPA tutto quello che viene dopo, e i tagli che erano sul battito non ci
    sono piu'; a istanti restano dove sono stati messi.
    """
    from vedit.report import analyze

    istanti = progetto([0.0, 1.0, 2.0],
                       defaults={"transition": 0.4, "transition_type": "crossfade"})

    a_durate = Project.from_dict({
        "output": {"size": [160, 90], "fps": 10},
        "defaults": {"transition": 0.4, "transition_type": "crossfade"},
        "timeline": [{"type": "color", "duration": 1.0} for _ in range(3)],
    })

    tagli_a_istanti = [round(r.placement.start, 4) for r in analyze(istanti).rows]
    tagli_a_durate = [round(r.placement.start, 4) for r in analyze(a_durate).rows]

    assert tagli_a_istanti == [0.0, 0.6, 1.6]
    assert tagli_a_durate == [0.0, 0.6, 1.2]     # il terzo taglio si e' spostato


def test_la_dissolvenza_non_sposta_i_tagli_nemmeno_nel_montaggio_vero():
    """Il riepilogo lo dice; qui si controlla che il render faccia lo stesso."""
    dissolto = progetto([0.0, 1.0, 2.0], ultima_durata=1.0,
                        defaults={"transition": 0.4, "transition_type": "crossfade"})
    clip = build(dissolto)
    try:
        assert [round(c.start, 4) for c in clip.clips] == [0.0, 0.6, 1.6]
        assert clip.duration == pytest.approx(2.6)
    finally:
        close_all()


def test_il_clip_che_entra_prende_piu_sorgente(tmp_path):
    """
    Entrare in anticipo significa avere bisogno di piu' materiale: il segmento
    possiede un secondo di montaggio ma con 0.4s di dissolvenza ne deve mostrare
    1.4, altrimenti l'ultimo pezzo resterebbe scoperto.
    """
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
        "defaults": {"transition": 0.4, "transition_type": "crossfade"},
        "timeline": [
            {"type": "video", "at": 0.0, "src": str(sorgente), "start": 0.0},
            # Nessun `end`: quanto sorgente serve lo decide il montaggio.
            {"type": "video", "at": 1.0, "src": str(sorgente), "start": 3.0},
            {"type": "video", "at": 2.0, "src": str(sorgente), "start": 0.0, "end": 1.0},
        ],
    })
    project.root = tmp_path

    clip = build(project)
    try:
        # Possiede un secondo (da 1.0 a 2.0) ma ne mostra 1.4: 0.4 di anticipo.
        assert clip.clips[1].duration == pytest.approx(1.4, abs=0.05)
        assert clip.clips[1].start == pytest.approx(0.6, abs=0.001)
        # L'ultimo ha un solo secondo di sorgente (0 -> 1) e 0.4 se ne vanno
        # nell'entrata: il montaggio finisce a 2.6.
        assert clip.duration == pytest.approx(2.6, abs=0.05)
    finally:
        close_all()


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
