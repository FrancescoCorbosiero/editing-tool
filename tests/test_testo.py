"""
Test dello stile del testo: font, contorno, sfondo, a capo, allineamento.

I clip di testo sono immagini generate in memoria: nessun file richiesto.
"""

import numpy as np
import pytest

from vedit import fonts
from vedit.models import ConfigError, Project, TextStyle


def stile(**overrides) -> TextStyle:
    base = {"font_size": 30, "color": "white"}
    base.update(overrides)
    return TextStyle(**base)


def clip(text: str, style: TextStyle, canvas_width: int = 800, duration: float = 1.0):
    from vedit.builder import make_text_clip

    return make_text_clip(text, style, canvas_width, duration)


# -- font -------------------------------------------------------------------

def test_esiste_un_font_predefinito():
    # Se questo fallisce, su questa macchina non c'e' nessun font: il messaggio
    # d'errore di vedit deve spiegare come indicarne uno.
    assert fonts.default_font() is not None


def test_un_font_si_indica_anche_per_nome():
    predefinito = fonts.default_font()
    per_nome = fonts.find_font(predefinito.stem)
    assert per_nome == predefinito


def test_il_confronto_dei_nomi_ignora_spazi_e_maiuscole():
    predefinito = fonts.default_font()
    assert fonts.find_font(predefinito.stem.upper()) == predefinito


def test_percorso_relativo_alla_cartella_del_progetto(tmp_path):
    finto = tmp_path / "fonts" / "Mio.ttf"
    finto.parent.mkdir()
    finto.write_bytes(b"non e' un vero font, ma esiste")
    assert fonts.find_font("fonts/Mio.ttf", root=tmp_path) == finto
    assert fonts.find_font("fonts/Assente.ttf", root=tmp_path) is None


def test_il_messaggio_di_errore_spiega_come_uscirne():
    messaggio = fonts.font_error_message("Comic Sans Inesistente")
    assert "Comic Sans Inesistente" in messaggio
    assert "vedit fonts" in messaggio


def test_font_inesistente_e_un_errore_leggibile():
    with pytest.raises(ConfigError, match="Font non trovato"):
        clip("ciao", stile(font="QuestoFontNonEsisteDavvero"))


# -- a capo -----------------------------------------------------------------

def larghezza(riga: str, font_size: int = 30) -> float:
    from PIL import ImageFont

    return ImageFont.truetype(str(fonts.default_font()), font_size).getlength(riga)


def test_le_righe_stanno_dentro_il_limite():
    testo = "Una frase abbastanza lunga da dover andare a capo piu' di una volta di seguito."
    risultato = fonts.wrap_text(testo, fonts.default_font(), 30, max_width=200)
    righe = risultato.split("\n")
    assert len(righe) > 3
    assert all(larghezza(r) <= 200 for r in righe)


def test_le_parole_non_vengono_spezzate():
    # E' il difetto del caption di MoviePy, che produce "larghe / zza".
    testo = "andare a capo da sola entro la larghezza massima consentita"
    righe = fonts.wrap_text(testo, fonts.default_font(), 30, max_width=200).split("\n")
    assert "larghezza" in " ".join(righe)
    for parola in testo.split():
        assert parola in righe or any(parola in r.split() for r in righe)


def test_le_andate_a_capo_esistenti_si_rispettano():
    # Un a capo scritto nel testo e' una scelta di chi l'ha scritto.
    testo = "Prima riga\nSeconda riga"
    assert fonts.wrap_text(testo, fonts.default_font(), 20, max_width=9999) == testo


def test_una_parola_piu_larga_della_riga_viene_spezzata():
    # Meglio spezzarla che vederla uscire dallo schermo.
    lunga = "supercalifragilistichespiralidoso"
    righe = fonts.wrap_text(lunga, fonts.default_font(), 30, max_width=120).split("\n")
    assert len(righe) > 1
    assert "".join(righe) == lunga
    assert all(larghezza(r) <= 120 for r in righe)


# -- resa del testo ---------------------------------------------------------

def test_a_capo_automatico_entro_la_larghezza_massima():
    lungo = "Una frase abbastanza lunga da dover andare a capo almeno una volta."
    stretto = clip(lungo, stile(max_width=0.4), canvas_width=800)
    largo = clip(lungo, stile(max_width=None), canvas_width=800)

    assert stretto.w <= 800 * 0.4 + 4
    assert stretto.h > largo.h        # e' andato a capo: piu' righe, piu' altezza
    assert largo.w > stretto.w


def test_il_testo_corto_non_si_allarga_al_massimo():
    # Con lo sfondo attivo conta: un rettangolo largo mezzo schermo dietro la
    # parola "Ciao" sarebbe orribile.
    corto = clip("Ciao", stile(max_width=0.9, bg_color="black"), canvas_width=800)
    assert corto.w < 200


def test_max_width_in_pixel_o_in_frazione():
    style = stile(max_width=0.5)
    assert style.wrap_width(1920) == 960
    assert stile(max_width=300).wrap_width(1920) == 300
    assert stile().wrap_width(1920) is None


def test_lo_sfondo_semitrasparente_finisce_nella_maschera():
    opaco = clip("Ciao", stile(bg_color="black", bg_opacity=1.0))
    trasparente = clip("Ciao", stile(bg_color="black", bg_opacity=0.4))
    senza = clip("Ciao", stile())

    assert opaco.mask.get_frame(0).mean() == pytest.approx(1.0)
    assert 0.4 <= trasparente.mask.get_frame(0).mean() < 1.0
    # Senza sfondo restano opachi solo i pixel delle lettere
    assert senza.mask.get_frame(0).mean() < 0.4


def test_lo_sfondo_accetta_anche_una_terna_rgb():
    from vedit.text import resolve_background

    assert resolve_background(stile(bg_color=[10, 20, 30], bg_opacity=0.5)) == (10, 20, 30, 128)
    assert resolve_background(stile(bg_color="black", bg_opacity=1.0)) == (0, 0, 0, 255)
    assert resolve_background(stile()) is None


def test_il_padding_allarga_il_riquadro():
    senza = clip("Ciao", stile(bg_color="black"))
    con = clip("Ciao", stile(bg_color="black", padding=20))
    assert con.w == senza.w + 40
    assert con.h == senza.h + 40


def test_il_contorno_ingrandisce_il_disegno():
    senza = clip("Ciao", stile())
    con = clip("Ciao", stile(stroke_color="black", stroke_width=4))
    assert con.w > senza.w


# -- disegno con Pillow -----------------------------------------------------
#
# Questi test guardano i pixel, senza MoviePy: il testo lo disegna text.py.

def inchiostro_di_riferimento(righe: list[str], style: TextStyle) -> int:
    """Quanti pixel di testo produce Pillow disegnando le righe su una tela enorme."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(fonts.default_font()), style.font_size)
    totale = 0
    for riga in righe:
        tela = Image.new("RGBA", (2000, 400), (0, 0, 0, 0))
        ImageDraw.Draw(tela).text(
            (200, 100), riga, font=font, fill=(255, 255, 255, 255),
            stroke_width=style.stroke_width if style.stroke_color else 0,
            stroke_fill=(0, 0, 0, 255) if style.stroke_color else None,
        )
        totale += int((np.asarray(tela)[:, :, 3] > 0).sum())
    return totale


def test_nessuna_riga_resta_tagliata():
    """
    Il difetto di TextClip in MoviePy 2.2: l'ultima riga usciva mozzata in
    basso. Qui ogni pixel che Pillow disegnerebbe su una tela enorme deve
    esserci anche nell'immagine del testo.
    """
    from vedit.text import render_text

    style = stile(font_size=40)
    righe = ["Prima riga", "seconda con le gambe", "pqgyj"]
    rgba = render_text("\n".join(righe), style, canvas_width=2000)
    assert int((rgba[:, :, 3] > 0).sum()) == inchiostro_di_riferimento(righe, style)


def test_nessun_contorno_resta_tagliato():
    from vedit.text import render_text

    style = stile(font_size=40, stroke_color="black", stroke_width=5)
    rgba = render_text("pqgyj ÀÉ", style, canvas_width=2000)
    assert int((rgba[:, :, 3] > 0).sum()) == inchiostro_di_riferimento(["pqgyj ÀÉ"], style)


def test_le_righe_sono_alte_uguale_qualunque_lettera_contengano():
    # "ace" non ha ne' ascendenti ne' discendenti, "Tpg" si': un riquadro di
    # sfondo che cambiasse altezza da una scritta all'altra si noterebbe.
    from vedit.text import render_text

    style = stile(font_size=40, bg_color="black", padding=10)
    assert render_text("ace", style, 800).shape[0] == render_text("Tpg", style, 800).shape[0]


def test_il_riquadro_ha_il_colore_e_l_opacita_chiesti():
    from vedit.text import render_text

    rgba = render_text("Ciao", stile(bg_color=[200, 0, 0], bg_opacity=0.5, padding=12), 800)
    meta = rgba.shape[0] // 2
    # Un pixel nel margine, lontano dalle lettere e dagli angoli arrotondati
    assert tuple(rgba[meta, 3]) == (200, 0, 0, 128)


def test_le_lettere_restano_opache_sopra_un_riquadro_trasparente():
    from vedit.text import render_text

    rgba = render_text("I", stile(font_size=60, bg_color="black", bg_opacity=0.3, padding=10), 800)
    assert rgba[:, :, 3].max() == 255


def test_allineamento_a_sinistra_e_a_destra():
    from vedit.text import render_text

    def primo_pixel(rgba, riga):
        alpha = rgba[riga, :, 3]
        return int(np.argmax(alpha > 0)), int(len(alpha) - np.argmax(alpha[::-1] > 0))

    testo = "riga lunghissima\ncorta"
    sinistra = render_text(testo, stile(font_size=30, align="left"), 800)
    destra = render_text(testo, stile(font_size=30, align="right"), 800)
    alto, basso = sinistra.shape[0] // 4, sinistra.shape[0] * 3 // 4
    # A sinistra le due righe cominciano nello stesso punto, a destra finiscono
    assert abs(primo_pixel(sinistra, alto)[0] - primo_pixel(sinistra, basso)[0]) <= 3
    assert abs(primo_pixel(destra, alto)[1] - primo_pixel(destra, basso)[1]) <= 3


def test_colore_sconosciuto_e_un_errore_leggibile():
    from vedit.text import render_text

    with pytest.raises(ConfigError, match="Colore non riconosciuto"):
        render_text("Ciao", stile(color="verdolino"), 800)


# -- validazione ------------------------------------------------------------

def test_allineamento_non_valido():
    with pytest.raises(ConfigError, match="align"):
        Project.from_dict({
            "timeline": [{"type": "color", "duration": 1}],
            "overlays": [{"type": "text", "text": "ciao", "align": "giustificato"}],
        })


def test_opacita_dello_sfondo_fuori_scala():
    with pytest.raises(ConfigError, match="bg_opacity"):
        Project.from_dict({
            "timeline": [{"type": "color", "duration": 1}],
            "overlays": [{"type": "text", "text": "ciao", "bg_opacity": 5}],
        })


def test_lo_stile_arriva_dal_yaml():
    p = Project.from_dict({
        "timeline": [{"type": "color", "duration": 1}],
        "overlays": [{
            "type": "text", "text": "ciao", "font_size": 90, "color": "yellow",
            "stroke_color": "black", "stroke_width": 3, "bg_color": "black",
            "bg_opacity": 0.35, "max_width": 0.6, "align": "left", "padding": 16,
        }],
    })
    style = p.overlays[0].style
    assert (style.font_size, style.color, style.align) == (90, "yellow", "left")
    assert (style.stroke_color, style.stroke_width) == ("black", 3)
    assert (style.bg_color, style.bg_opacity) == ("black", 0.35)
    assert (style.max_width, style.padding) == (0.6, 16)


# -- anteprima --------------------------------------------------------------

def test_l_anteprima_riscala_anche_posizioni_e_testo():
    """
    Dimezzare solo il canvas manderebbe un titolo a y=820 fuori da un quadro
    alto 540: l'anteprima mostrerebbe un montaggio diverso da quello finale.
    """
    p = Project.from_dict({
        "output": {"size": [1920, 1080]},
        "timeline": [{"type": "color", "duration": 2}],
        "overlays": [{
            "type": "text", "text": "ciao", "font_size": 72, "padding": 18,
            "stroke_color": "black", "stroke_width": 4, "max_width": 600,
            "position": ["center", 820],
        }],
    })
    p.scale(0.5)

    assert p.output.size == (960, 540)
    assert p.overlays[0].position == ("center", 410)
    style = p.overlays[0].style
    assert (style.font_size, style.padding, style.stroke_width) == (36, 9, 2)
    assert style.max_width == 300           # era in pixel: si dimezza


def test_le_misure_in_frazione_non_si_riscalano():
    # 0.8 significa gia' "l'80% del canvas", qualunque sia il canvas.
    p = Project.from_dict({
        "timeline": [{"type": "color", "duration": 1}],
        "overlays": [{"type": "text", "text": "ciao", "max_width": 0.8}],
    })
    p.scale(0.5)
    assert p.overlays[0].style.max_width == 0.8


def test_le_dimensioni_dell_anteprima_restano_pari():
    # libx264 rifiuta le dimensioni dispari: 1079 // 2 = 539 farebbe fallire l'export.
    p = Project.from_dict({
        "output": {"size": [1921, 1079]},
        "timeline": [{"type": "color", "duration": 1}],
    })
    p.scale(0.5)
    assert p.output.size == (960, 538)
