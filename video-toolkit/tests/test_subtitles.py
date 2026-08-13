"""
Test del parser .srt e del disegno dei sottotitoli.

Il parsing e' testo puro e non richiede niente; il disegno usa un canvas
minuscolo e segmenti 'color', quindi niente file video.
"""

import pytest

from vedit.models import ConfigError, Project
from vedit.subtitles import Cue, SubtitleError, load_srt, overlaps, parse_srt, parse_timestamp

SRT = """1
00:00:01,000 --> 00:00:03,500
Prima battuta

2
00:00:04,000 --> 00:00:06,000
Seconda battuta,
su due righe
"""


# -- parsing ---------------------------------------------------------------

def test_parsing_di_base():
    cues = parse_srt(SRT)
    assert len(cues) == 2
    assert cues[0] == Cue(start=1.0, end=3.5, text="Prima battuta")
    assert cues[1].text == "Seconda battuta,\nsu due righe"
    assert cues[1].duration == 2.0


def test_tempi_in_tutte_le_forme():
    assert parse_timestamp("00:00:01,000") == 1.0
    assert parse_timestamp("00:01:02,500") == 62.5
    assert parse_timestamp("01:00:00,000") == 3600.0
    assert parse_timestamp("00:00:01.250") == 1.25      # punto invece di virgola
    assert parse_timestamp("0:00:02,5") == 2.5          # millisecondi abbreviati


def test_tempo_malformato():
    with pytest.raises(SubtitleError, match="Tempo non riconosciuto"):
        parse_timestamp("un minuto circa")


def test_ritorni_a_capo_windows_e_bom():
    contenuto = "﻿1\r\n00:00:01,000 --> 00:00:02,000\r\nCiao\r\n"
    assert parse_srt(contenuto)[0].text == "Ciao"


def test_blocchi_senza_numero_progressivo():
    contenuto = "00:00:01,000 --> 00:00:02,000\nCiao\n\n00:00:03,000 --> 00:00:04,000\nCiao 2\n"
    assert len(parse_srt(contenuto)) == 2


def test_coordinate_dopo_i_tempi_ignorate():
    # Alcuni programmi appendono la posizione alla riga dei tempi.
    contenuto = "1\n00:00:01,000 --> 00:00:02,000 X1:100 X2:200 Y1:10 Y2:40\nCiao\n"
    assert parse_srt(contenuto)[0].end == 2.0


def test_righe_vuote_multiple_e_spazi():
    contenuto = SRT.replace("\n\n", "\n   \n\n")
    assert len(parse_srt(contenuto)) == 2


def test_blocco_senza_tempi():
    with pytest.raises(SubtitleError, match="senza riga dei tempi"):
        parse_srt("1\nsolo testo, nessun tempo\n")


def test_fine_prima_dell_inizio():
    with pytest.raises(SubtitleError, match="finisce prima"):
        parse_srt("1\n00:00:05,000 --> 00:00:02,000\nCiao\n")


def test_file_su_disco_e_codifiche(tmp_path):
    path = tmp_path / "dialoghi.srt"
    path.write_text(SRT, encoding="utf-8")
    assert len(load_srt(path)) == 2

    # Un srt vecchio salvato in latin-1 non deve far fallire il render
    vecchio = tmp_path / "vecchio.srt"
    vecchio.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nperch\xe8 no\n".encode("latin-1"))
    assert load_srt(vecchio)[0].text == "perchè no"


def test_il_nome_del_file_finisce_nel_messaggio_di_errore(tmp_path):
    path = tmp_path / "rotto.srt"
    path.write_text("1\n00:00:0X,000 --> 00:00:02,000\nCiao\n")
    with pytest.raises(SubtitleError, match="rotto.srt"):
        load_srt(path)


def test_sovrapposizioni():
    cues = [Cue(0, 3, "a"), Cue(2, 4, "b"), Cue(5, 6, "c")]
    assert len(overlaps(cues)) == 1
    assert overlaps([Cue(0, 1, "a"), Cue(1, 2, "b")]) == []


# -- integrazione con il progetto -------------------------------------------

def progetto_con_sottotitoli(tmp_path, **subtitles):
    srt = tmp_path / "dialoghi.srt"
    srt.write_text(SRT)
    data = {"src": "dialoghi.srt"}
    data.update(subtitles)
    project = Project.from_dict({
        "output": {"size": [320, 180], "fps": 10},
        "timeline": [{"type": "color", "duration": 8}],
        "subtitles": data,
    })
    project.root = tmp_path
    return project


def test_i_sottotitoli_diventano_clip(tmp_path):
    from vedit.builder import build, close_all

    project = progetto_con_sottotitoli(tmp_path)
    video = build(project)
    try:
        # il montaggio + due battute
        assert len(video.clips) == 3
        primo = video.clips[1]
        assert primo.start == 1.0
        assert primo.duration == 2.5
    finally:
        close_all()


def test_offset_sposta_tutte_le_battute(tmp_path):
    from vedit.builder import build, close_all

    project = progetto_con_sottotitoli(tmp_path, offset=1.5)
    video = build(project)
    try:
        assert video.clips[1].start == 2.5
    finally:
        close_all()


def test_le_battute_oltre_la_fine_del_video_vengono_scartate(tmp_path):
    from vedit.builder import build, close_all

    project = progetto_con_sottotitoli(tmp_path)
    project.timeline[0].duration = 2.0    # il video finisce prima della seconda battuta
    video = build(project)
    try:
        assert len(video.clips) == 2      # montaggio + una sola battuta
        assert video.clips[1].duration == 1.0   # troncata alla fine del video
    finally:
        close_all()


def test_il_file_srt_mancante_e_segnalato_prima_del_render(tmp_path):
    project = progetto_con_sottotitoli(tmp_path)
    project.subtitles.src = "non-esiste.srt"
    with pytest.raises(ConfigError, match="non-esiste.srt"):
        project.validate_files()


def test_avvisi_nel_riepilogo(tmp_path):
    from vedit.report import analyze

    srt = tmp_path / "dialoghi.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:05,000\nlunga\n\n"
        "2\n00:00:03,000 --> 00:00:03,200\nlampo sovrapposto\n\n"
        "3\n00:09:00,000 --> 00:09:02,000\nfuori dal video\n"
    )
    project = Project.from_dict({
        "timeline": [{"type": "color", "duration": 8}],
        "subtitles": {"src": "dialoghi.srt"},
    })
    project.root = tmp_path

    report = analyze(project)
    assert report.subtitle_count == 3
    testo = " ".join(report.warnings)
    assert "si sovrappongono" in testo
    assert "mezzo secondo" in testo
    assert "dopo la fine del montaggio" in testo
