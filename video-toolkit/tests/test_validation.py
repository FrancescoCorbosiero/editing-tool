"""
Test della validazione "in blocco": un progetto sbagliato in quattro punti
deve produrre quattro messaggi, non farne scoprire uno per esecuzione.
"""

import pytest

from vedit.models import ConfigError, Project


def test_gli_errori_dei_segmenti_sono_riportati_tutti():
    with pytest.raises(ConfigError) as exc:
        Project.from_dict({
            "timeline": [
                {"type": "video", "src": "a.mp4", "start": 10, "end": 5},
                {"type": "color"},                       # manca duration
                {"type": "image", "src": "b.jpg", "fit": "zoom"},   # fit inesistente
            ]
        })

    message = str(exc.value)
    assert "timeline[0]" in message
    assert "timeline[1]" in message
    assert "timeline[2]" in message
    assert "(3)" in message   # il conteggio in testa al messaggio


def test_errori_di_sezioni_diverse_nello_stesso_messaggio():
    with pytest.raises(ConfigError) as exc:
        Project.from_dict({
            "defaults": {"fit": "inesistente"},
            "timeline": [{"type": "color", "duration": 1}],
            "overlays": [{"type": "text"}],       # manca il campo text
            "audio": {"volume": 0.5},             # manca src
        })

    message = str(exc.value)
    assert "defaults.fit" in message
    assert "overlays[0]" in message
    assert "audio" in message


def test_un_solo_errore_resta_un_messaggio_semplice():
    # Con un errore solo non si stampa l'intestazione con il conteggio.
    with pytest.raises(ConfigError) as exc:
        Project.from_dict({"timeline": [{"type": "color"}]})
    assert str(exc.value).startswith("timeline[0]")


def test_file_mancanti_elencati_tutti(tmp_path):
    presente = tmp_path / "c_e.jpg"
    presente.write_bytes(b"finto")

    project = Project.from_dict({
        "timeline": [
            {"type": "image", "src": "c_e.jpg", "duration": 1},
            {"type": "video", "src": "manca.mp4", "label": "clip"},
        ],
        "overlays": [{"type": "image", "src": "logo-assente.png"}],
        "audio": {"src": "musica-assente.mp3"},
    })
    project.root = tmp_path

    mancanti = project.missing_files()
    assert len(mancanti) == 3
    assert not any("c_e.jpg" in m for m in mancanti)

    with pytest.raises(ConfigError, match="File referenziati ma non trovati"):
        project.validate_files()


def test_font_verificato_solo_se_e_un_percorso(tmp_path):
    project = Project.from_dict({
        "timeline": [{"type": "color", "duration": 1}],
        "overlays": [
            {"type": "text", "text": "ciao", "font": "DejaVu Sans"},   # nome di sistema
            {"type": "text", "text": "ciao", "font": "fonts/manca.ttf"},
        ],
    })
    project.root = tmp_path

    mancanti = project.missing_files()
    assert len(mancanti) == 1
    assert "manca.ttf" in mancanti[0]


def test_durata_del_segmento_con_e_senza_sorgente():
    project = Project.from_dict({
        "defaults": {"image_duration": 3},
        "timeline": [
            {"type": "image", "src": "a.jpg"},                       # eredita il default
            {"type": "video", "src": "a.mp4", "start": 2, "end": 8},
            {"type": "video", "src": "a.mp4", "start": 2, "end": 8, "speed": 2.0},
            {"type": "video", "src": "a.mp4"},                       # durata = quella del file
        ],
    })
    d = project.defaults
    assert project.timeline[0].timeline_duration(d) == 3
    assert project.timeline[1].timeline_duration(d) == 6
    # A velocita' doppia sei secondi di sorgente ne occupano tre sul montaggio
    assert project.timeline[2].timeline_duration(d) == 3
    assert project.timeline[3].timeline_duration(d) is None
    assert project.timeline[3].timeline_duration(d, source_duration=10) == 10
