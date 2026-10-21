"""
Test del parsing/validazione: sono veloci perche' non toccano MoviePy.
Lancia con:  pytest -q
"""

import pytest

from vedit.models import ConfigError, Project


def minimal(**overrides) -> dict:
    data = {
        "timeline": [
            {"type": "color", "duration": 2, "color": [0, 0, 0]},
        ]
    }
    data.update(overrides)
    return data


def test_progetto_minimo():
    p = Project.from_dict(minimal())
    assert len(p.timeline) == 1
    assert p.output.size == (1920, 1080)
    assert p.defaults.fit == "cover"


def test_timeline_vuota_e_errore():
    with pytest.raises(ConfigError, match="almeno un segmento"):
        Project.from_dict({"timeline": []})


def test_segmento_senza_type():
    with pytest.raises(ConfigError, match="type"):
        Project.from_dict({"timeline": [{"src": "a.mp4"}]})


def test_video_senza_src():
    with pytest.raises(ConfigError, match="src"):
        Project.from_dict({"timeline": [{"type": "video"}]})


def test_end_prima_di_start():
    with pytest.raises(ConfigError, match="end deve essere maggiore"):
        Project.from_dict({"timeline": [{"type": "video", "src": "a.mp4", "start": 10, "end": 5}]})


def test_fit_non_valido():
    with pytest.raises(ConfigError, match="fit"):
        Project.from_dict({"timeline": [{"type": "image", "src": "a.jpg", "fit": "zoom"}]})


def test_color_senza_duration():
    with pytest.raises(ConfigError, match="duration"):
        Project.from_dict({"timeline": [{"type": "color"}]})


def test_speed_negativa():
    with pytest.raises(ConfigError, match="speed"):
        Project.from_dict({"timeline": [{"type": "video", "src": "a.mp4", "speed": 0}]})


def test_output_personalizzato():
    p = Project.from_dict(minimal(output={"size": [1080, 1920], "fps": 60, "crf": 18}))
    assert p.output.size == (1080, 1920)
    assert p.output.fps == 60
    assert p.output.crf == 18


def test_transizione_del_segmento_vince_sul_default():
    p = Project.from_dict(minimal(
        defaults={"transition": 0.5},
        timeline=[
            {"type": "color", "duration": 2},
            {"type": "color", "duration": 2, "transition": 1.5},
        ],
    ))
    assert p.defaults.transition == 0.5
    assert p.timeline[0].transition is None   # eredita il default
    assert p.timeline[1].transition == 1.5


def test_audio_opzionale():
    p = Project.from_dict(minimal())
    assert p.audio is None
    p2 = Project.from_dict(minimal(audio={"src": "m.mp3", "volume": 0.3, "replace": True}))
    assert p2.audio is not None
    assert p2.audio.volume == 0.3
    assert p2.audio.replace is True
