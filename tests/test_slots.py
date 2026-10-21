"""
Test di `vedit slots`: cambiare i tagli di un template a orecchio.

La promessa da tenere e' una: **la modifica tocca solo i tagli che nomini**. Un
taglio aggiunto non sposta quelli che c'erano, un posto unito non cambia gli
istanti degli altri, e i numeri si leggono sempre sull'elenco di prima.
"""

import shutil
import subprocess

import numpy as np
import pytest
import yaml
from PIL import Image

from vedit.cli import main
from vedit.extract import render
from vedit.models import ConfigError
from vedit.slots import (
    card_color,
    cards,
    describe,
    describe_change,
    edits_using,
    parse_time,
    renumbering,
    retime,
    snap_time,
)
from vedit.templates import AudioTrack, Template, TemplateError


def tpl(istanti=(0.0, 2.0, 2.5, 3.0, 4.0), durata=6.0, bpm=120.0, offset=0.0,
        extra: dict | None = None) -> Template:
    """Un template in memoria: a 120 BPM un battito dura 0.5s, mezzo battito 0.25s."""
    slots = [{"at": t} for t in istanti]
    for i, campi in (extra or {}).items():
        slots[i].update(campi)
    return Template.from_dict({
        "name": "prova",
        "duration": durata,
        "audio": {"src": "audio.m4a", "bpm": bpm, "offset": offset},
        "format": {"size": [360, 640], "fps": 30},
        "slots": slots,
    })


def istanti(template: Template) -> list[float]:
    return [slot.at for slot in template.slots]


# -- leggere un istante e allinearlo ------------------------------------------

@pytest.mark.parametrize("scritto, atteso", [
    ("4.45", 4.45), ("4,45", 4.45), ("0:04.45", 4.45), ("1:02", 62.0), (3, 3.0),
])
def test_un_istante_si_scrive_come_lo_scrive_una_persona(scritto, atteso):
    assert parse_time(scritto) == pytest.approx(atteso)


def test_un_istante_scritto_male_e_un_errore_leggibile():
    with pytest.raises(ConfigError, match="minuti:secondi"):
        parse_time("quattro")


def test_la_griglia_rimette_il_taglio_sul_battito():
    audio = AudioTrack(src="a.m4a", bpm=120.0, offset=0.0)
    assert snap_time(1.1, audio, 2) == 1.0       # mezzi battiti: passo 0.25
    assert snap_time(1.1, audio, 4) == 1.125     # quarti: passo 0.125
    assert snap_time(1.1, audio, 1) == 1.0
    assert snap_time(1.1, audio, 0) == 1.1       # nessuna griglia


def test_senza_battito_non_c_e_griglia():
    assert snap_time(1.1, AudioTrack(src="a.m4a", bpm=0.0), 2) == 1.1


# -- aggiungere un taglio ----------------------------------------------------

def test_un_taglio_in_piu_non_sposta_gli_altri():
    prima = tpl()
    dopo = retime(prima, cuts=["2.75"]).template
    assert istanti(dopo) == [0.0, 2.0, 2.5, 2.75, 3.0, 4.0]


def test_il_taglio_si_allinea_alla_griglia_e_lo_dice():
    result = retime(tpl(), cuts=["3.4"])
    assert 3.5 in istanti(result.template)
    assert any("3.4 -> 3.500s" in nota for nota in result.notes)


def test_con_grid_off_il_taglio_resta_dove_lo_scrivi():
    result = retime(tpl(), cuts=["3.4"], grid="off")
    assert 3.4 in istanti(result.template)
    assert not result.notes


def test_il_quarto_colpo_del_drop():
    # Il caso da cui e' nato il comando: in `raffica` il basso entra con quattro
    # colpi da mezzo battito, e il riferimento cambiava immagine solo sui primi tre.
    raffica = tpl((0.0, 3.862, 4.06, 4.258, 4.654, 5.051), durata=6.0, bpm=151.5, offset=0.1)
    result = retime(raffica, cuts=["4.45"])
    assert istanti(result.template) == [0.0, 3.862, 4.06, 4.258, 4.456, 4.654, 5.051]
    assert result.added == [4.456]
    assert result.numbers == [0, 1, 2, 3, 5, 6]


def test_un_taglio_che_c_e_gia_non_cambia_niente():
    result = retime(tpl(), cuts=["2.5"])
    assert not result.changed
    assert any("c'e' gia' un taglio" in nota and "posto 3" in nota for nota in result.notes)


def test_un_taglio_a_meno_di_un_fotogramma_da_un_altro_e_un_errore():
    with pytest.raises(ConfigError, match="meno di un fotogramma"):
        retime(tpl(), cuts=["2.02"], grid="off")


def test_un_taglio_fuori_dal_template_e_un_errore():
    with pytest.raises(ConfigError, match="col punto"):
        retime(tpl(), cuts=["45"])


def test_un_colpo_a_ridosso_dell_inizio_e_il_taglio_che_c_e_gia():
    result = retime(tpl(), cuts=["0.1"])
    assert not result.changed
    assert any("posto 1" in nota for nota in result.notes)


def test_un_taglio_che_sulla_griglia_cadrebbe_oltre_la_fine_e_un_errore():
    with pytest.raises(ConfigError, match="oltre la fine"):
        retime(tpl(durata=5.9), cuts=["5.88"])


# -- dividere e unire --------------------------------------------------------

def test_split_divide_in_parti_uguali():
    assert istanti(retime(tpl(), split=[4]).template) == [0.0, 2.0, 2.5, 3.0, 3.5, 4.0]
    assert istanti(retime(tpl(), split=[4], into=4).template) == [
        0.0, 2.0, 2.5, 3.0, 3.25, 3.5, 3.75, 4.0]


def test_split_non_usa_la_griglia_una_terzina_resta_una_terzina():
    assert istanti(retime(tpl(), split=[4], into=3).template) == [
        0.0, 2.0, 2.5, 3.0, 3.333, 3.667, 4.0]


def test_merge_toglie_il_taglio_con_cui_comincia_il_posto():
    result = retime(tpl(), merge=[3])
    assert istanti(result.template) == [0.0, 2.0, 3.0, 4.0]
    assert result.removed == [2.5]
    assert result.numbers == [0, 1, 1, 2, 3]   # il 3 finisce dentro il 2


def test_i_numeri_sono_quelli_dell_elenco_di_prima():
    # Divide il 2 e unisce il 4 di adesso: non il 4 che verrebbe fuori dopo la divisione.
    result = retime(tpl(), split=[2], merge=[4])
    assert istanti(result.template) == [0.0, 2.0, 2.25, 2.5, 4.0]


def test_il_template_di_partenza_non_si_tocca():
    prima = tpl(extra={2: {"label": "pausa"}})
    retime(prima, merge=[3], split=[1])
    assert istanti(prima) == [0.0, 2.0, 2.5, 3.0, 4.0]
    assert prima.slots[2].label == "pausa"


# -- etichette, suggerimenti, movimenti --------------------------------------

def test_un_posto_unito_lascia_l_etichetta_a_chi_lo_assorbe():
    result = retime(tpl(extra={2: {"label": "pausa"}}), merge=[3])
    assert result.template.slots[1].label == "pausa"


def test_se_chi_assorbe_ha_gia_un_etichetta_quella_unita_si_perde_e_lo_dice():
    result = retime(tpl(extra={1: {"label": "drop"}, 2: {"label": "pausa"}}), merge=[3])
    assert result.template.slots[1].label == "drop"
    assert any("'pausa'" in nota for nota in result.notes)


def test_i_posti_nuovi_ereditano_contenuto_e_fit_ma_non_l_etichetta():
    lungo = tpl((0.0, 4.0), durata=6.0,
                extra={0: {"label": "apertura", "hint": "video", "fit": "cover"}})
    nuovo = retime(lungo, split=[1]).template
    assert [s.at for s in nuovo.slots] == [0.0, 2.0, 4.0]
    assert nuovo.slots[1].hint == "video" and nuovo.slots[1].fit == "cover"
    assert nuovo.slots[1].label == ""
    assert nuovo.slots[0].label == "apertura"


def test_in_un_lampo_non_restano_ne_suggerimento_ne_movimento():
    # Le soglie di extract: sotto 0.45s non conta cosa c'era, sotto 0.6s un
    # movimento non fa in tempo a leggersi.
    lungo = tpl((0.0, 1.0, 2.0), durata=3.0,
                extra={1: {"hint": "image", "motion": "zoom_in"}})
    nuovo = retime(lungo, split=[2], into=4).template
    assert all(slot.hint is None and slot.motion is None for slot in nuovo.slots[1:5])
    assert nuovo.slots[0].at == 0.0


def test_una_transizione_che_non_ci_sta_piu_e_un_errore_del_template():
    con_dissolvenza = tpl(extra={3: {"transition": 0.4, "transition_type": "crossfade"}})
    with pytest.raises(TemplateError, match="non c'e' spazio"):
        retime(con_dissolvenza, cuts=["2.75"])


# -- errori ------------------------------------------------------------------

def test_gli_errori_si_raccolgono_tutti():
    with pytest.raises(ConfigError) as exc:
        retime(tpl(), split=[9], merge=[1, 7], cuts=["boh", "45"])
    messaggio = str(exc.value)
    for pezzo in ("--split 9", "--merge 1", "--merge 7", "'boh'", "--cut 45"):
        assert pezzo in messaggio, pezzo


def test_into_deve_essere_almeno_due():
    with pytest.raises(ConfigError, match="--into"):
        retime(tpl(), split=[2], into=1)


# -- riepiloghi --------------------------------------------------------------

def test_il_riepilogo_dice_cosa_e_cambiato_e_come_tornare_indietro():
    prima = tpl()
    result = retime(prima, cuts=["2.75"])
    testo = describe_change(prima, result, "templates/prova")
    assert "5 posti -> 6" in testo
    assert "+ taglio a 2.750s: comincia il posto 4" in testo
    assert "i posti dal 4 al 5 ora sono dal 5 al 6" in testo
    assert "vedit slots templates/prova --merge 4" in testo


def test_il_comando_per_tornare_indietro_torna_davvero_indietro():
    prima = tpl()
    aggiunto = retime(prima, split=[4], cuts=["2.25"])
    assert istanti(retime(aggiunto.template, merge=[3, 6]).template) == istanti(prima)
    assert "--merge 3 6" in describe_change(prima, aggiunto, "t")

    tolto = retime(prima, merge=[3])
    assert "--cut 2.5 --grid off" in describe_change(prima, tolto, "t")
    assert istanti(retime(tolto.template, cuts=["2.5"], grid="off").template) == istanti(prima)


def test_la_rinumerazione_in_parole():
    prima = tpl()
    assert renumbering(prima, retime(prima, merge=[3])) == [
        "i posti dal 4 al 5 ora sono dal 3 al 4"]
    assert renumbering(prima, retime(prima, cuts=["3.5"])) == ["il posto 5 ora e' il 6"]


def test_l_elenco_dei_posti():
    testo = describe(tpl(extra={0: {"label": "apertura", "hint": "video"}}), "templates/prova")
    assert "prova: 5 posti in 6.00s (120 BPM" in testo
    assert "apertura" in testo and "video" in testo
    assert "vedit slots templates/prova --cut" in testo
    assert "--split 4" in testo and "--merge 5" in testo


def test_gli_esempi_dell_elenco_esistono_nel_template():
    testo = describe(tpl((0.0, 1.0, 2.0), durata=3.0), "t")
    assert "--cut 1.5" in testo and "--split 3" in testo and "--merge 3" in testo
    assert "--merge 5" not in testo
    assert "--merge" not in describe(tpl((0.0,), durata=3.0), "t")


def test_un_template_riscritto_si_rilegge_uguale():
    result = retime(tpl(extra={0: {"label": "apertura", "hint": "video"}}), cuts=["2.75"])
    riletto = Template.from_dict(yaml.safe_load(render(result.template)))
    assert istanti(riletto) == istanti(result.template)
    assert riletto.slots[0].label == "apertura" and riletto.slots[0].hint == "video"


def test_gli_edit_che_usano_il_template(tmp_path):
    cartella = tmp_path / "templates" / "prova"
    cartella.mkdir(parents=True)
    (cartella / "template.yaml").write_text(render(tpl()), encoding="utf-8")
    template = Template.from_yaml(cartella)

    for nome, dati in {
        "a": "template: ../../templates/prova\n",
        "b": "template: ../../templates/altro\n",
        "c": "template: ../../templates/prova/template.yaml\n",
        "d": "template: [rotto\n",
    }.items():
        (tmp_path / "edits" / nome).mkdir(parents=True)
        (tmp_path / "edits" / nome / "edit.yaml").write_text(dati, encoding="utf-8")

    trovati = [p.parent.name for p in edits_using(template, tmp_path / "edits")]
    assert trovati == ["a", "c"]


# -- i cartelli del video dei posti ------------------------------------------

def test_due_posti_vicini_hanno_colori_e_luce_diversi():
    for i in range(40):
        a, b = np.array(card_color(i)), np.array(card_color(i + 1))
        assert np.abs(a - b).max() > 40
        assert (a.max() > b.max()) == (i % 2 == 0)


def test_un_cartello_per_posto_col_numero_scritto(tmp_path):
    files = cards(tpl(), tmp_path, width=90)
    assert [f.name for f in files] == ["001.png", "002.png", "003.png", "004.png", "005.png"]
    for i, path in enumerate(files):
        pixels = np.asarray(Image.open(path).convert("RGB"))
        assert pixels.shape == (160, 90, 3)
        # Il fondo e' il colore del posto; il numero e' bianco: senza numero
        # non ci sarebbero pixel chiarissimi.
        assert tuple(pixels[2, 2]) == card_color(i)
        assert (pixels.min(axis=2) > 230).sum() > 20


# -- il comando --------------------------------------------------------------

def scrivi(tmp_path, template: Template):
    cartella = tmp_path / "templates" / "prova"
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "template.yaml").write_text(render(template), encoding="utf-8")
    return cartella


def test_vedit_slots_elenca_senza_toccare_niente(tmp_path, capsys):
    cartella = scrivi(tmp_path, tpl())
    prima = (cartella / "template.yaml").read_text(encoding="utf-8")
    assert main(["slots", str(cartella)]) == 0
    assert "5 posti" in capsys.readouterr().out
    assert (cartella / "template.yaml").read_text(encoding="utf-8") == prima


def test_vedit_slots_riscrive_il_template(tmp_path, capsys, monkeypatch):
    cartella = scrivi(tmp_path, tpl())
    (tmp_path / "edits" / "video").mkdir(parents=True)
    (tmp_path / "edits" / "video" / "edit.yaml").write_text(
        "template: ../../templates/prova\nmedia: [a.jpg]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["slots", "templates/prova", "--split", "4", "--cut", "0:01.1"]) == 0
    out = capsys.readouterr().out
    assert istanti(Template.from_yaml(cartella)) == [0.0, 1.0, 2.0, 2.5, 3.0, 3.5, 4.0]
    assert "edits/video/edit.yaml" in out           # chi usa il template lo sa
    assert "--merge 2 6" in out


def test_vedit_slots_con_un_errore_non_scrive_niente(tmp_path, capsys):
    cartella = scrivi(tmp_path, tpl())
    prima = (cartella / "template.yaml").read_text(encoding="utf-8")
    assert main(["slots", str(cartella), "--merge", "1"]) == 1
    assert "--merge 1" in capsys.readouterr().err
    assert (cartella / "template.yaml").read_text(encoding="utf-8") == prima


def test_il_video_dei_posti_stacca_sugli_istanti(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("serve ffmpeg")
    template = Template.from_dict({
        "name": "prova", "duration": 2.0,
        "audio": {"src": "audio.m4a", "bpm": 120.0},
        "format": {"size": [160, 96], "fps": 30},
        "slots": [{"at": 0.0}, {"at": 0.5}, {"at": 1.25}],
    })
    cartella = scrivi(tmp_path, template)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", str(cartella / "audio.m4a")], check=True)
    video = tmp_path / "posti.mp4"
    assert main(["slots", str(cartella), "--video", "-o", str(video)]) == 0

    from moviepy import VideoFileClip

    clip = VideoFileClip(str(video))
    try:
        assert clip.size == [80, 48]                 # meta' risoluzione
        assert clip.duration == pytest.approx(2.0, abs=0.05)
        for at in (0.5, 1.25):
            prima = clip.get_frame(at - 0.05).mean(axis=(0, 1))
            dopo = clip.get_frame(at + 0.05).mean(axis=(0, 1))
            assert np.abs(prima - dopo).max() > 20, f"nessun taglio a {at}"
    finally:
        clip.close()
