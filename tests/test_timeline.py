"""
Test della matematica della timeline (vedit/timeline.py).

Non serve MoviePy: qui si verificano solo numeri, ed e' il motivo per cui il
calcolo vive in un modulo separato dal builder.
"""

import pytest

from vedit.timeline import Placement, clamp_overlap, plan, total_duration


def test_senza_sovrapposizioni_i_segmenti_si_accodano():
    placements = plan([2, 3, 4], [0, 0, 0])
    assert [p.start for p in placements] == [0, 2, 5]
    assert total_duration(placements) == 9


def test_la_sovrapposizione_anticipa_il_segmento():
    # Il secondo clip parte 1s prima della fine del primo: e' la sovrapposizione
    # che rende possibile una dissolvenza incrociata.
    placements = plan([4, 4], [0, 1.0])
    assert placements[1].start == 3.0
    assert placements[1].overlap == 1.0
    assert total_duration(placements) == 7.0


def test_la_sovrapposizione_non_supera_meta_clip():
    # Richiesti 10s fra due clip da 2s: ridotta a 1s (meta' del piu' corto).
    assert clamp_overlap(10.0, 2.0, 2.0) == 1.0
    assert clamp_overlap(10.0, 8.0, 2.0) == 1.0
    assert clamp_overlap(0.5, 8.0, 8.0) == 0.5


def test_sovrapposizione_negativa_azzerata():
    assert clamp_overlap(-3.0, 4.0, 4.0) == 0.0


def test_il_primo_segmento_non_ha_transizione_in_entrata():
    # transitions[0] viene ignorato: non c'e' nulla che preceda il primo clip.
    placements = plan([3, 3], [99.0, 0])
    assert placements[0] == Placement(index=0, start=0.0, end=3.0, overlap=0.0)


def test_liste_di_lunghezza_diversa():
    with pytest.raises(ValueError):
        plan([1, 2], [0])


def test_timeline_vuota():
    with pytest.raises(ValueError):
        plan([], [])
