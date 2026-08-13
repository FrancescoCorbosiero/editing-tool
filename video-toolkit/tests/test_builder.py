"""
Test del builder che non richiedono file sorgente: usano segmenti 'color',
generati in memoria. Verificano la matematica delle transizioni.
"""

from vedit.builder import build, close_all
from vedit.models import Project


def build_durata(durate, transizioni) -> float:
    """Costruisce una timeline di soli colori e restituisce la durata finale."""
    timeline = []
    for i, d in enumerate(durate):
        seg = {"type": "color", "duration": d}
        if i > 0:
            seg["transition"] = transizioni[i - 1]
        timeline.append(seg)
    project = Project.from_dict({
        "output": {"size": [320, 180], "fps": 12},
        "timeline": timeline,
    })
    clip = build(project)
    durata = clip.duration
    close_all()
    return durata


def test_senza_transizioni_le_durate_si_sommano():
    assert build_durata([2, 3, 4], [0, 0]) == 9


def test_la_transizione_accorcia_il_totale():
    # 2 + 3 + 4 = 9, meno 1s di sovrapposizione = 8
    assert build_durata([2, 3, 4], [1.0, 0]) == 8.0


def test_transizioni_multiple():
    # 4 + 4 + 4 = 12, meno 1 meno 2 = 9
    assert build_durata([4, 4, 4], [1.0, 2.0]) == 9.0


def test_transizione_limitata_a_meta_clip():
    # Transizione richiesta 10s fra clip da 2s: viene ridotta a 1s (meta' del piu' corto)
    assert build_durata([2, 2], [10.0]) == 3.0


def test_clip_singolo():
    assert build_durata([5], []) == 5
