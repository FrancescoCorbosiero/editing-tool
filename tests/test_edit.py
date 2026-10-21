"""
Test degli edit: un template, i media nei posti, i testi sopra.

La domanda a cui rispondono: **quello che scrivo nell'edit finisce dove dico?**
Un testo agganciato al posto 3 deve comparire quando entra il posto 3 e sparire
quando entra il 4; un media nella lista deve finire nel suo posto.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from PIL import Image

from vedit.edit import Edit, _position, _slot_range, parse_text, skeleton, text_warnings
from vedit.models import ConfigError, Project, place
from vedit.templates import Template


def crea_template(cartella: Path, istanti=(0.0, 2.0, 4.0, 6.0), durata=8.0,
                  size=(720, 1280), extra: dict | None = None) -> Path:
    """Un template su disco: template.yaml e una traccia vera (serve ffmpeg)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("serve ffmpeg per la traccia del template")
    cartella.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={durata}",
                    str(cartella / "audio.m4a")], check=True)
    dati = {
        "name": cartella.name,
        "duration": durata,
        "audio": {"src": "audio.m4a", "bpm": 120},
        "format": {"size": list(size), "fps": 30},
        "style": {"fit": "contain", "fade_out": 1.0},
        "slots": [{"at": t} for t in istanti],
        **(extra or {}),
    }
    (cartella / "template.yaml").write_text(yaml.safe_dump(dati), encoding="utf-8")
    return cartella


def foto(path: Path, colore=(200, 30, 30), size=(400, 300)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colore).save(path)
    return path


@pytest.fixture
def repo(tmp_path):
    """Un repo in miniatura: templates/prova e edits/video con quattro foto."""
    crea_template(tmp_path / "templates" / "prova")
    edit = tmp_path / "edits" / "video"
    for i, colore in enumerate([(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]):
        foto(edit / "media" / f"{i + 1:02d}.jpg", colore)
    return tmp_path


def scrivi_edit(repo: Path, **dati) -> Path:
    contenuto = {"template": "../../templates/prova",
                 "media": [f"media/{i:02d}.jpg" for i in range(1, 5)], **dati}
    path = repo / "edits" / "video" / "edit.yaml"
    path.write_text(yaml.safe_dump(contenuto, allow_unicode=True), encoding="utf-8")
    return path


# -- i tempi dei testi ------------------------------------------------------

def test_un_testo_su_un_posto_dura_quanto_il_posto(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": 2}]))
    cue = edit.texts[0]
    assert (cue.start, cue.end) == (2.0, 4.0)


def test_un_testo_su_piu_posti_va_dal_primo_alla_fine_dell_ultimo(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": "2-3"}]))
    assert (edit.texts[0].start, edit.texts[0].end) == (2.0, 6.0)


def test_l_ultimo_posto_finisce_con_il_template(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "fine", "slot": 4}]))
    assert edit.texts[0].end == 8.0


def test_con_at_il_testo_dura_fino_al_taglio_dopo(repo):
    # Senza durata il testo cambia sul battito, insieme all'immagine.
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "at": 2.5}]))
    assert (edit.texts[0].start, edit.texts[0].end) == (2.5, 4.0)


def test_con_at_e_duration_decidono_i_secondi(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "at": 1, "duration": 4.5}]))
    assert (edit.texts[0].start, edit.texts[0].end) == (1.0, 5.5)


def test_un_testo_non_va_oltre_la_fine_del_video(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "at": 7, "duration": 9}]))
    assert edit.texts[0].end == 8.0


def test_il_testo_diventa_un_overlay_con_i_tempi_risolti(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[
        {"text": "ciao", "slot": 2, "position": "top", "fade": 0.2},
    ]))
    overlay = edit.bind().data["overlays"][0]
    assert overlay["type"] == "text" and overlay["text"] == "ciao"
    assert (overlay["start"], overlay["duration"]) == (2.0, 2.0)
    assert overlay["position"] == "top"
    assert overlay["fade"] == 0.2
    # Lo stile arriva dal template: bianco con contorno nero, proporzionato al canvas
    assert overlay["color"] == "white" and overlay["font_size"] == 54


# -- i posti dei testi ------------------------------------------------------

@pytest.mark.parametrize(("scritto", "atteso"), [
    (None, "center"),
    ("TOP", "top"),
    (0.25, {"x": 0.5, "y": 0.25}),
    ([0.2, 0.9], {"x": 0.2, "y": 0.9}),
])
def test_le_posizioni_si_scrivono_in_tanti_modi(scritto, atteso):
    assert _position(scritto, "texts[0]") == atteso


@pytest.mark.parametrize("sbagliato", ["sopra", 1.5, [0.5], [0.5, 2], True])
def test_una_posizione_sbagliata_dice_come_si_scrive(sbagliato):
    with pytest.raises(ConfigError, match="top, center, bottom"):
        _position(sbagliato, "texts[0]")


def test_le_posizioni_pronte_stanno_nella_safe_area():
    canvas = (720, 1280)
    x, y = place("top", (300, 100), canvas)
    assert x == 210 and y == round(1280 * 0.12)
    x, y = place("bottom", (300, 100), canvas)
    assert y + 100 == round(1280 * 0.78)          # il bordo basso sopra l'ultimo 22%
    assert place("center", (300, 100), canvas) == (210, 590)


def test_in_frazioni_si_centra_sul_punto_senza_uscire_dallo_schermo():
    canvas = (720, 1280)
    assert place({"x": 0.5, "y": 0.5}, (300, 100), canvas) == (210, 590)
    # Vicino al bordo il testo viene tenuto dentro
    assert place({"x": 1.0, "y": 0.0}, (300, 100), canvas) == (420, 0)


def test_i_pixel_e_le_forme_di_moviepy_passano_come_sono():
    assert place((40, 50), (300, 100), (720, 1280)) == (40, 50)
    assert place(("center", "top"), (300, 100), (720, 1280)) == ("center", "top")


# -- gli errori -------------------------------------------------------------

def test_un_posto_che_non_esiste(repo):
    with pytest.raises(ConfigError, match="il template ha i posti da 1 a 4"):
        Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": 7}]))


@pytest.mark.parametrize("scritto", ["3-1", "0", "a-b", "2.5"])
def test_un_intervallo_di_posti_sbagliato(scritto):
    with pytest.raises(ConfigError):
        _slot_range(scritto, 4, "texts[0]")


def test_un_testo_senza_quando(repo):
    with pytest.raises(ConfigError, match="manca QUANDO"):
        Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao"}]))


def test_un_numero_scritto_a_parole_e_un_errore_leggibile(repo):
    with pytest.raises(ConfigError, match="at deve essere un numero"):
        Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "at": "dopo"}]))
    with pytest.raises(ConfigError, match="start deve essere un numero"):
        Edit.from_yaml(scrivi_edit(repo, media=[{"src": "media/01.jpg", "start": "inizio"}]))


def test_un_testo_con_slot_e_at_insieme(repo):
    with pytest.raises(ConfigError, match="non tutti e due"):
        Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": 1, "at": 1}]))


def test_un_campo_scritto_male_si_dice_subito(repo):
    # "postion" invece di "position": senza questo controllo il testo
    # finirebbe al centro in silenzio, e nessuno capirebbe perche'.
    with pytest.raises(ConfigError, match="postion"):
        Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": 1, "postion": "top"}]))


def test_uno_stile_sbagliato_si_dice_con_il_numero_del_testo(repo):
    with pytest.raises(ConfigError, match=r"texts\[0\].*align"):
        Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": 1, "align": "storto"}]))


def test_tutti_gli_errori_insieme(repo):
    with pytest.raises(ConfigError) as info:
        Edit.from_yaml(scrivi_edit(repo, texts=[
            {"text": "uno", "slot": 9},
            {"text": "due"},
        ]))
    assert "texts[0]" in str(info.value) and "texts[1]" in str(info.value)


def test_un_testo_scritto_come_stringa_spiega_la_forma_giusta(repo):
    with pytest.raises(ConfigError, match="una mappa"):
        Edit.from_yaml(scrivi_edit(repo, texts=["ciao"]))


def test_un_edit_senza_template(repo):
    path = repo / "edits" / "video" / "edit.yaml"
    path.write_text(yaml.safe_dump({"media": ["media/01.jpg"]}), encoding="utf-8")
    with pytest.raises(ConfigError, match="template"):
        Edit.from_yaml(path)


def test_un_edit_senza_media(repo):
    with pytest.raises(ConfigError, match="non ha media"):
        Edit.from_yaml(scrivi_edit(repo, media=[]))


def test_due_testi_nello_stesso_punto_nello_stesso_momento(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, texts=[
        {"text": "uno", "slot": 1, "position": "top"},
        {"text": "due", "at": 1.0, "position": "top"},
        {"text": "tre", "slot": 1, "position": "bottom"},       # altrove: nessun problema
    ]))
    avvisi = text_warnings(edit.texts)
    assert len(avvisi) == 1 and "texts[0] e texts[1]" in avvisi[0]


# -- i media ----------------------------------------------------------------

def test_i_media_finiscono_nei_posti_in_ordine(repo):
    edit = Edit.from_yaml(scrivi_edit(repo))
    project = edit.project()
    assert [Path(s.src).name for s in project.timeline] == ["01.jpg", "02.jpg", "03.jpg", "04.jpg"]
    assert project.cut_positions() == [0.0, 2.0, 4.0, 6.0]
    # I percorsi del progetto sono relativi alla cartella dell'edit
    assert project.timeline[0].src == Path("media/01.jpg")
    project.validate_files()


def test_un_media_puo_cambiare_le_scelte_del_template(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, media=[
        "media/01.jpg",
        {"src": "media/02.jpg", "fit": "cover", "motion": "zoom_in", "amount": 0.1},
        "media/03.jpg", "media/04.jpg",
    ]))
    timeline = edit.bind().data["timeline"]
    assert timeline[0]["fit"] == "contain"                 # dal template
    assert timeline[1]["motion"] == "zoom_in" and timeline[1]["amount"] == 0.1
    assert "fit" not in timeline[1]                        # il movimento riempie da solo


def test_un_media_con_la_chiocciola_parte_da_quel_secondo(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, media=["media/clip.mp4@12.5", "media/01.jpg"]))
    assert edit.media[0].start == 12.5
    assert edit.media[0].path == (repo / "edits" / "video" / "media" / "clip.mp4").resolve()


def test_un_media_scritto_male(repo):
    with pytest.raises(ConfigError, match="campi sconosciuti"):
        Edit.from_yaml(scrivi_edit(repo, media=[{"src": "media/01.jpg", "strat": 3}]))


def test_fit_e_motion_sbagliati_si_dicono_con_il_numero_del_media(repo):
    with pytest.raises(ConfigError, match=r"media\[1\]: fit"):
        Edit.from_yaml(scrivi_edit(repo, media=["media/01.jpg", {"src": "media/02.jpg", "fit": "zoom"}]))
    with pytest.raises(ConfigError, match=r"media\[0\]: motion 'giravolta'"):
        Edit.from_yaml(scrivi_edit(repo, media=[{"src": "media/01.jpg", "motion": "giravolta"}]))


def test_motion_none_toglie_il_movimento_del_template(repo):
    edit = Edit.from_yaml(scrivi_edit(repo, media=[{"src": "media/01.jpg", "motion": "none"}]))
    assert edit.media[0].motion == ""
    assert "motion" not in edit.bind().data["timeline"][0]


def test_lo_stile_del_template_arriva_nel_progetto(repo):
    project = Edit.from_yaml(scrivi_edit(repo)).project()
    assert project.defaults.fit == "contain"
    assert project.fade_out == 1.0


def test_l_output_va_nella_cartella_dell_edit(repo):
    project = Edit.from_yaml(scrivi_edit(repo)).project()
    assert project.resolve(project.output.path) == (
        repo / "edits" / "video" / "output" / "video.mp4").resolve()


def test_in_un_altro_formato_il_testo_resta_proporzionato(repo):
    # Il template e' 720 di larghezza: esportando a 1080 tutto scala di 1.5
    edit = Edit.from_yaml(scrivi_edit(repo, size=[1080, 1920], texts=[
        {"text": "ciao", "slot": 1, "font_size": 60, "padding": 10},
    ]))
    overlay = edit.bind().data["overlays"][0]
    assert overlay["font_size"] == 90 and overlay["padding"] == 15


def test_l_edit_si_espande_in_un_progetto_valido(repo):
    """Il vincolo del repo: quello che un edit produce si scrive anche a mano."""
    from vedit.templates import to_yaml

    edit = Edit.from_yaml(scrivi_edit(repo, texts=[{"text": "ciao", "slot": "1-2"}]))
    testo = to_yaml(edit.bind())
    riletto = Project.from_dict(yaml.safe_load(testo))
    assert riletto.overlays[0].text == "ciao"
    assert riletto.overlays[0].position == "center"
    assert riletto.cut_positions() == [0.0, 2.0, 4.0, 6.0]


# -- lo scheletro -----------------------------------------------------------

def test_lo_scheletro_ha_un_posto_per_slot_e_si_rilegge(repo):
    template = Template.from_yaml(repo / "templates" / "prova")
    root = repo / "edits" / "nuovo"
    root.mkdir(parents=True)
    testo = skeleton(template, template.root, root, "nuovo")
    dati = yaml.safe_load(testo)

    assert dati["template"] == "../../templates/prova"      # relativo: il repo si sposta
    assert len(dati["media"]) == 4
    assert dati["texts"] == []
    assert "dura 2.00s" in testo


def test_lo_scheletro_usa_i_media_che_gli_si_danno(repo):
    from vedit.templates import expand_media

    template = Template.from_yaml(repo / "templates" / "prova")
    root = repo / "edits" / "video"
    media = expand_media([str(root / "media")])
    dati = yaml.safe_load(skeleton(template, template.root, root, "video", media))
    assert dati["media"] == ["media/01.jpg", "media/02.jpg", "media/03.jpg", "media/04.jpg"]
    Edit.from_dict(dati, root=root, name="video").project().validate_files()


# -- dal comando ------------------------------------------------------------

def test_render_check_su_un_edit(repo, capsys):
    from vedit.cli import main

    path = scrivi_edit(repo, texts=[{"text": "ciao", "slot": 2, "position": "top"}])
    assert main(["render", str(path.parent), "--check"]) == 0
    uscita = capsys.readouterr().out
    assert "Sopra il montaggio (1)" in uscita
    assert "ciao" in uscita and "top" in uscita


def test_to_yaml_scrive_il_progetto_dell_edit(repo):
    from vedit.cli import main

    path = scrivi_edit(repo, texts=[{"text": "ciao", "slot": 2}])
    target = repo / "edits" / "video" / "timeline.yaml"
    assert main(["render", str(path), "--to-yaml", str(target)]) == 0
    progetto = Project.from_yaml(target)
    progetto.validate_files()
    assert progetto.overlays[0].start == 2.0


def test_new_crea_l_edit_con_le_sue_cartelle(repo, capsys):
    from vedit.cli import main

    root = repo / "edits" / "altro"
    assert main(["new", str(root), "--template", str(repo / "templates" / "prova")]) == 0
    assert (root / "edit.yaml").exists()
    assert (root / "media" / ".gitkeep").exists() and (root / "output" / ".gitkeep").exists()
    # Una seconda volta no, a meno di --force
    assert main(["new", str(root), "--template", str(repo / "templates" / "prova")]) == 1


def test_new_accetta_i_media_anche_dopo_le_opzioni(repo):
    """
    Il comando come lo scrive chiunque: prima la cartella, poi --template, poi
    i file. Fino a Python 3.11 argparse rifiutava i file dopo l'opzione.
    """
    from vedit.cli import main

    root = repo / "edits" / "ordinato"
    media = repo / "edits" / "video" / "media"
    assert main(["new", str(root), "--template", str(repo / "templates" / "prova"),
                 str(media / "02.jpg"), str(media / "01.jpg")]) == 0
    dati = yaml.safe_load((root / "edit.yaml").read_text(encoding="utf-8"))
    assert [Path(m).name for m in dati["media"][:2]] == ["02.jpg", "01.jpg"]


def test_un_opzione_sconosciuta_resta_un_errore(repo):
    from vedit.cli import main

    with pytest.raises(SystemExit):
        main(["new", str(repo / "edits" / "x"), "--template", str(repo / "templates" / "prova"),
              "--colore", "rosso"])


def test_un_media_mancante_si_dice_prima_di_renderizzare(repo, capsys):
    from vedit.cli import main

    (repo / "edits" / "video" / "media" / "03.jpg").unlink()
    path = scrivi_edit(repo)
    assert main(["render", str(path), "--check"]) == 1
    assert "03.jpg" in capsys.readouterr().err


def test_parse_text_da_solo(repo):
    template = Template.from_yaml(repo / "templates" / "prova")
    cue = parse_text({"text": "ciao", "slot": 3, "color": "yellow"}, template, 0)
    assert cue.style == {"color": "yellow"}
