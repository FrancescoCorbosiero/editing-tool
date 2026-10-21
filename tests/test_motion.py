"""
Test del movimento sulle immagini (effetto Ken Burns).

Serve una vera immagine, ma non un file: si costruisce un ImageClip da un array
numpy in memoria. Le verifiche importanti sono due, e sono geometriche:
il clip prodotto ha sempre le dimensioni del canvas, e non scopre mai i bordi
neri durante il movimento.
"""

import numpy as np
import pytest

from vedit import motion
from vedit.models import ConfigError, Project
from vedit.motion import MotionContext, cover_size, even_up

CANVAS = (320, 180)


def immagine(width: int = 640, height: int = 360, duration: float = 2.0):
    """Un'immagine con un gradiente orizzontale, per riconoscere dove guardiamo."""
    from moviepy import ImageClip

    gradiente = np.linspace(0, 255, width, dtype=np.uint8)
    frame = np.repeat(gradiente[None, :, None], height, axis=0)
    frame = np.repeat(frame, 3, axis=2)
    return ImageClip(frame).with_duration(duration)


def mosso(nome: str, amount: float = 0.25, duration: float = 2.0):
    ctx = MotionContext(amount=amount, size=CANVAS, duration=duration)
    return motion.get(nome).apply(immagine(duration=duration), ctx)


# -- registry e geometria ---------------------------------------------------

def test_il_registry_contiene_i_movimenti_previsti():
    assert set(motion.names()) == {"zoom_in", "zoom_out", "pan_left", "pan_right",
                                   "pan_up", "pan_down"}


def test_un_movimento_sconosciuto_e_un_errore_leggibile():
    with pytest.raises(ValueError, match="Disponibili"):
        motion.get("carrellata_circolare")


def test_arrotondamento_ai_pari():
    # Sempre per eccesso: scendere sotto le misure del canvas scoprirebbe i bordi.
    assert even_up(100) == 100
    assert even_up(101) == 102
    assert even_up(100.2) == 102
    assert even_up(99.9) == 100


def test_le_dimensioni_calcolate_coprono_sempre_il_canvas():
    for source in [(640, 360), (1000, 200), (200, 1000), (321, 181)]:
        w, h = cover_size(source, CANVAS)
        assert w >= CANVAS[0] and h >= CANVAS[1]
        assert w % 2 == 0 and h % 2 == 0


@pytest.mark.parametrize("nome", ["zoom_in", "zoom_out", "pan_left", "pan_right",
                                  "pan_up", "pan_down"])
def test_il_clip_prodotto_ha_le_dimensioni_del_canvas(nome):
    clip = mosso(nome)
    assert tuple(clip.size) == CANVAS
    assert clip.duration == 2.0


@pytest.mark.parametrize("nome", ["zoom_in", "zoom_out", "pan_left", "pan_right",
                                  "pan_up", "pan_down"])
def test_nessun_bordo_nero_durante_il_movimento(nome):
    """
    Il rischio numero uno del Ken Burns: l'immagine si sposta piu' della sua
    eccedenza e si vede il fondo. Il gradiente parte da 0 (nero) solo sulla
    colonna piu' a sinistra, quindi si controllano gli angoli sulla destra e le
    righe: se comparisse il fondo, l'intera riga o colonna sarebbe nera.
    """
    clip = mosso(nome)
    # Si campiona fino a poco prima della fine: a t == durata esatta MoviePy
    # considera il clip gia' terminato e restituisce il fondo nero. Nel render
    # non capita, perche' i fotogrammi cadono sempre prima della fine.
    for t in [0.0, 0.5, 1.0, 1.5, 1.99]:
        frame = clip.get_frame(t)
        assert frame[:, -1].max() > 0, f"bordo destro nero a t={t}"
        assert frame[0].max() > 0, f"riga alta nera a t={t}"
        assert frame[-1].max() > 0, f"riga bassa nera a t={t}"


# -- direzione del movimento ------------------------------------------------

def colonna_media(frame) -> float:
    """Posizione media pesata del gradiente: dice 'dove' stiamo guardando."""
    return float(frame[:, :, 0].mean())


def test_il_pan_si_muove_e_nella_direzione_giusta():
    # pan_right: l'inquadratura va verso destra, quindi vede pixel via via piu'
    # chiari (il gradiente cresce da sinistra a destra).
    clip = mosso("pan_right", amount=0.5)
    inizio, fine = colonna_media(clip.get_frame(0.0)), colonna_media(clip.get_frame(1.99))
    assert fine > inizio + 5

    clip = mosso("pan_left", amount=0.5)
    inizio, fine = colonna_media(clip.get_frame(0.0)), colonna_media(clip.get_frame(1.99))
    assert fine < inizio - 5


def ampiezza(frame) -> float:
    """Quanto gradiente entra nell'inquadratura: cala se si stringe lo zoom."""
    return float(np.ptp(frame[0, :, 0]))


def test_lo_zoom_cambia_la_scala_nel_tempo():
    # Con lo zoom in, la porzione di immagine inquadrata si restringe: il
    # gradiente visibile copre un intervallo di valori piu' stretto.
    clip = mosso("zoom_in", amount=0.5)
    assert ampiezza(clip.get_frame(1.99)) < ampiezza(clip.get_frame(0.0))

    clip = mosso("zoom_out", amount=0.5)
    assert ampiezza(clip.get_frame(1.99)) > ampiezza(clip.get_frame(0.0))


def test_le_dimensioni_intermedie_dello_zoom_restano_pari():
    ctx = MotionContext(amount=0.37, size=CANVAS, duration=2.0)
    clip = motion.get("zoom_in").apply(immagine(), ctx)
    interno = clip.clips[0]
    # Il clip interno viene riscalato a ogni fotogramma: nessuna di quelle
    # dimensioni intermedie deve essere dispari.
    for t in [0.0, 0.33, 0.9, 1.7, 1.99]:
        h, w = interno.get_frame(t).shape[:2]
        assert w % 2 == 0 and h % 2 == 0, f"dimensione dispari a t={t}: {w}x{h}"


# -- validazione ------------------------------------------------------------

def test_motion_solo_sulle_immagini():
    with pytest.raises(ConfigError, match="solo ai segmenti 'image'"):
        Project.from_dict({"timeline": [
            {"type": "video", "src": "a.mp4", "motion": "zoom_in"},
        ]})


def test_motion_inesistente():
    with pytest.raises(ConfigError, match="non esiste"):
        Project.from_dict({"timeline": [
            {"type": "image", "src": "a.jpg", "motion": "zoom_laterale"},
        ]})


def test_amount_fuori_scala():
    # 20 invece di 0.20 e' l'errore di battitura tipico: va intercettato.
    with pytest.raises(ConfigError, match="amount"):
        Project.from_dict({"timeline": [
            {"type": "image", "src": "a.jpg", "motion": "zoom_in", "amount": 20},
        ]})


def test_amount_ha_un_default():
    p = Project.from_dict({"timeline": [
        {"type": "image", "src": "a.jpg", "motion": "zoom_in"},
    ]})
    assert p.timeline[0].amount == 0.15
