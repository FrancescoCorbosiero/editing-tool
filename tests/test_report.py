"""
Test del riepilogo `render --check`.

Si usano solo segmenti 'color': senza file sorgente ffprobe non viene mai
chiamato, e il test resta istantaneo.
"""

from vedit.models import Project
from vedit.report import analyze, format_report, format_time


def progetto(**overrides) -> Project:
    data = {
        "output": {"size": [640, 360], "fps": 25},
        "timeline": [
            {"type": "color", "duration": 2, "label": "uno"},
            {"type": "color", "duration": 4, "transition": 1.0, "label": "due"},
        ],
    }
    data.update(overrides)
    return Project.from_dict(data)


def test_posizioni_calcolate():
    report = analyze(progetto())
    inizi = [r.placement.start for r in report.rows]
    assert inizi == [0.0, 1.0]          # il secondo anticipa di 1s per la transizione
    assert report.duration == 5.0       # 2 + 4 - 1


def test_avviso_su_transizione_troppo_lunga():
    report = analyze(progetto(timeline=[
        {"type": "color", "duration": 2},
        {"type": "color", "duration": 2, "transition": 5},
    ]))
    assert any("transizione ridotta" in w for w in report.warnings)
    assert report.rows[1].placement.overlap == 1.0


def test_nessun_avviso_su_un_progetto_pulito():
    assert analyze(progetto()).warnings == []


def test_formattazione_del_tempo():
    assert format_time(0) == "0:00.00"
    assert format_time(65.5) == "1:05.50"
    assert format_time(3661) == "1:01:01.00"


def test_il_testo_del_riepilogo_contiene_le_informazioni_chiave():
    testo = format_report(analyze(progetto(), "edits/prova/timeline.yaml"))
    assert "edits/prova/timeline.yaml" in testo
    assert "640x360 @ 25 fps" in testo
    assert "Durata totale" in testo
    assert "uno" in testo and "due" in testo
    assert "Nessun avviso" in testo


def test_le_cifre_del_riepilogo_coincidono_con_quelle_del_montaggio():
    """
    Il riepilogo e il render devono raccontare la stessa storia: entrambi
    passano da timeline.plan(), e questo test lo blocca.
    """
    from vedit.builder import build, close_all

    project = progetto()
    report = analyze(project)
    clip = build(project)
    try:
        assert round(clip.duration, 6) == round(report.duration, 6)
    finally:
        close_all()


def test_con_contain_una_foto_larga_quanto_il_canvas_non_si_ingrandisce(tmp_path):
    """
    720x864 in un canvas 720x1280: con `contain` entra intera senza ingrandirsi,
    e avvisare sarebbe solo rumore. Con `cover` invece va ingrandita.
    """
    from PIL import Image

    foto = tmp_path / "f.png"
    Image.new("RGB", (720, 864), (100, 100, 100)).save(foto)

    def avvisi(fit):
        project = Project.from_dict({
            "output": {"size": [720, 1280]},
            "timeline": [{"type": "image", "src": str(foto), "duration": 1, "fit": fit}],
        })
        return [w for w in analyze(project).warnings if "ingrandito" in w]

    assert avvisi("contain") == []
    assert len(avvisi("cover")) == 1 and "1.5 volte" in avvisi("cover")[0]


def test_il_riepilogo_elenca_i_testi_sopra_il_montaggio():
    project = Project.from_dict({
        "timeline": [{"type": "color", "duration": 4}],
        "overlays": [
            {"type": "text", "text": "ciao", "start": 1, "duration": 2, "position": "top"},
            {"type": "text", "text": "dopo la fine", "start": 9},
        ],
    })
    report = analyze(project)
    primo = report.overlays[0]
    assert (primo.start, primo.end, primo.position) == (1.0, 3.0, "top")
    assert any("dopo la fine del montaggio" in w for w in report.warnings)
    assert "Sopra il montaggio (2)" in format_report(report)
