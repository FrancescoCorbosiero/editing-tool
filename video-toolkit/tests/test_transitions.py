"""
Test delle transizioni: registry, matematica della timeline e maschera del wipe.

Si usano solo segmenti 'color', quindi niente file video.
"""

import pytest

from vedit import transitions
from vedit.builder import build, close_all
from vedit.models import ConfigError, Project
from vedit.transitions import TransitionContext


def montaggio(tipo: str, durata: float = 1.0, **extra) -> Project:
    """Due colori da 4s con la transizione richiesta fra il primo e il secondo."""
    secondo = {"type": "color", "duration": 4, "color": [0, 0, 255],
               "transition": durata, "transition_type": tipo}
    secondo.update(extra)
    return Project.from_dict({
        "output": {"size": [160, 90], "fps": 10},
        "timeline": [{"type": "color", "duration": 4, "color": [255, 0, 0]}, secondo],
    })


def durata_montata(tipo: str, durata: float = 1.0, **extra) -> float:
    clip = build(montaggio(tipo, durata, **extra))
    try:
        return clip.duration
    finally:
        close_all()


# -- registry ---------------------------------------------------------------

def test_il_registry_contiene_le_transizioni_previste():
    assert set(transitions.names()) == {
        "crossfade", "fade_through_black", "slide", "wipe", "cut"
    }


def test_una_transizione_sconosciuta_e_un_errore_leggibile():
    with pytest.raises(ValueError, match="Disponibili"):
        transitions.get("dissolvenza-stellare")


def test_solo_slide_e_wipe_usano_la_direzione():
    direzionali = {n for n in transitions.names() if transitions.get(n).directional}
    assert direzionali == {"slide", "wipe"}


def test_registrare_una_transizione_non_richiede_di_toccare_il_builder():
    """Il punto del registry: una funzione nuova entra in gioco da sola."""
    @transitions.register("finta_per_test", overlaps=True)
    def _finta(prev, current, ctx):
        """Non fa nulla, serve solo a dimostrare il meccanismo."""
        return prev, current

    try:
        assert "finta_per_test" in transitions.names()
        # models.py accetta subito il nome nuovo, senza modifiche
        project = montaggio("finta_per_test")
        assert project.timeline[1].transition_type == "finta_per_test"
        clip = build(project)
        close_all()
        assert clip.duration == 7.0    # overlaps=True: 4 + 4 - 1
    finally:
        del transitions.REGISTRY["finta_per_test"]


# -- effetto sulla durata del montaggio -------------------------------------

def test_le_transizioni_con_sovrapposizione_accorciano_il_montaggio():
    assert durata_montata("crossfade") == 7.0
    assert durata_montata("slide") == 7.0
    assert durata_montata("wipe") == 7.0


def test_le_transizioni_senza_sovrapposizione_non_cambiano_la_durata():
    # Il nero della dissolvenza si consuma DENTRO i clip, non fra i clip.
    assert durata_montata("fade_through_black") == 8.0
    assert durata_montata("cut") == 8.0


def test_cut_ignora_la_durata_dichiarata():
    assert durata_montata("cut", durata=3.0) == 8.0


# -- validazione ------------------------------------------------------------

def test_transition_type_inesistente():
    with pytest.raises(ConfigError, match="non esiste"):
        Project.from_dict({"timeline": [
            {"type": "color", "duration": 1},
            {"type": "color", "duration": 1, "transition_type": "teletrasporto"},
        ]})


def test_direzione_non_valida():
    with pytest.raises(ConfigError, match="direction"):
        Project.from_dict({"timeline": [
            {"type": "color", "duration": 1, "direction": "diagonale"},
        ]})


def test_alias_delle_direzioni():
    p = Project.from_dict({"timeline": [
        {"type": "color", "duration": 1, "direction": "up"},
        {"type": "color", "duration": 1, "direction": "destra"},
    ]})
    assert p.timeline[0].direction == "top"
    assert p.timeline[1].direction == "right"


def test_il_segmento_vince_sul_default_campo_per_campo():
    p = Project.from_dict({
        "defaults": {"transition": 0.5, "transition_type": "wipe", "direction": "top"},
        "timeline": [
            {"type": "color", "duration": 2},
            {"type": "color", "duration": 2, "transition_type": "slide"},
        ],
    })
    richiesta = p.timeline[1].transition_request(p.defaults)
    assert richiesta.type == "slide"        # dichiarato sul segmento
    assert richiesta.duration == 0.5        # ereditato dal default
    assert richiesta.direction == "top"     # ereditato dal default


# -- maschera del wipe ------------------------------------------------------

def maschera(direction: str, t: float, durata: float = 1.0):
    ctx = TransitionContext(duration=durata, direction=direction, size=(100, 50))
    mask = transitions._wipe_mask(ctx.size, ctx.duration, direction, clip_duration=4.0)
    return mask.get_frame(t)


def test_la_maschera_del_wipe_parte_chiusa_e_finisce_aperta():
    assert maschera("left", 0.0).max() == 0.0     # niente e' ancora rivelato
    assert maschera("left", 1.0).min() == 1.0     # a fine transizione si vede tutto
    assert maschera("left", 3.0).min() == 1.0     # e resta cosi' per il resto del clip


def test_il_wipe_da_sinistra_rivela_prima_la_sinistra():
    frame = maschera("left", 0.5)
    assert frame[:, 5].mean() == 1.0      # colonna a sinistra: gia' rivelata
    assert frame[:, 95].mean() == 0.0     # colonna a destra: ancora coperta


def test_il_wipe_da_destra_e_speculare():
    frame = maschera("right", 0.5)
    assert frame[:, 5].mean() == 0.0
    assert frame[:, 95].mean() == 1.0


def test_il_wipe_verticale_lavora_sulle_righe():
    frame = maschera("top", 0.5)
    assert frame[2, :].mean() == 1.0      # riga in alto: rivelata
    assert frame[47, :].mean() == 0.0     # riga in basso: coperta
    assert frame.shape == (50, 100)


def test_il_bordo_del_wipe_e_sfumato():
    # Fra la zona rivelata e quella coperta ci sono valori intermedi: senza
    # sfumatura il bordo risulterebbe scalettato.
    frame = maschera("left", 0.5)
    intermedi = ((frame > 0.01) & (frame < 0.99)).sum()
    assert intermedi > 0


# -- slide ------------------------------------------------------------------

def test_lo_slide_muove_il_clip_nel_tempo():
    project = montaggio("slide", direction="left")
    clip = build(project)
    try:
        entrante = clip.clips[-1]
        # A inizio transizione il clip e' fuori campo a sinistra, poi arriva a 0
        assert entrante.pos(0.0)[0] < 0
        assert entrante.pos(1.0)[0] == 0
    finally:
        close_all()
