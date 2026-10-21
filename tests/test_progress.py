"""
Test della barra di avanzamento: si simulano gli aggiornamenti che MoviePy
manda al logger, scrivendo su uno StringIO invece che sul terminale.
"""

import io

from vedit.progress import RenderProgress, format_duration


def avanza(progress: RenderProgress, bar: str, total: int, passi: list[int]) -> None:
    """Riproduce la sequenza di chiamate che proglog fa durante un export."""
    progress(**{f"{bar}__total": total})
    for i in passi:
        progress(**{f"{bar}__index": i})


def test_formattazione_delle_durate():
    assert format_duration(0) == "0s"
    assert format_duration(45.4) == "45s"
    assert format_duration(125) == "2m 05s"
    assert format_duration(3700) == "1h 01m"


def test_stampa_percentuale_ed_eta():
    stream = io.StringIO()
    progress = RenderProgress(stream=stream, min_interval=0.0)
    avanza(progress, "frame_index", 100, [10, 50, 100])

    testo = stream.getvalue()
    assert "video" in testo          # 'frame_index' e' la barra dei fotogrammi
    assert "100%" in testo
    assert "rimanenti" in testo      # la stima del residuo appare almeno una volta
    # A lavoro finito la stima sparisce: "~0s rimanenti" e' solo rumore
    assert "rimanenti" not in testo.splitlines()[-1]


def test_gli_aggiornamenti_troppo_ravvicinati_vengono_saltati():
    stream = io.StringIO()
    progress = RenderProgress(stream=stream, min_interval=60.0)
    avanza(progress, "t", 100, [1, 2, 3])
    # Il primo aggiornamento si disegna subito (altrimenti per un minuto non si
    # vedrebbe nulla), i due successivi cadono dentro l'intervallo e si saltano.
    assert len(stream.getvalue().splitlines()) == 1


def test_la_fine_viene_sempre_disegnata():
    stream = io.StringIO()
    progress = RenderProgress(stream=stream, min_interval=60.0)
    avanza(progress, "t", 10, [1, 10])
    assert "100%" in stream.getvalue()


def test_barre_diverse_hanno_etichette_diverse():
    stream = io.StringIO()
    progress = RenderProgress(stream=stream, min_interval=0.0)
    avanza(progress, "chunk", 4, [4])
    avanza(progress, "t", 4, [4])
    testo = stream.getvalue()
    assert "audio" in testo
    assert "video" in testo


def test_fuori_dal_terminale_stampa_righe_separate():
    # StringIO non e' un tty: niente \r, una riga ogni 10% per non allagare i log
    stream = io.StringIO()
    progress = RenderProgress(stream=stream, min_interval=0.0, milestone=10)
    avanza(progress, "t", 100, list(range(0, 101)))
    righe = [r for r in stream.getvalue().splitlines() if r.strip()]
    assert "\r" not in stream.getvalue()
    assert 5 <= len(righe) <= 12


def test_totale_sconosciuto_non_esplode():
    stream = io.StringIO()
    progress = RenderProgress(stream=stream, min_interval=0.0)
    progress(**{"t__index": 3})       # nessun total dichiarato
    assert stream.getvalue() == ""
