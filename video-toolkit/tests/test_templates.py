"""
Test dei template audio: lettura, validazione e applicazione ai media.

La domanda a cui rispondono quasi tutti: **il montaggio che esce dal template
cade dove dice il template?** Se la risposta e' no, un template non serve a
niente, perche' il suo unico valore e' che i tagli stanno sui battiti.
"""

import shutil
import subprocess

import pytest

from vedit.models import Project
from vedit.templates import (
    AudioTrack,
    Bound,
    MediaRef,
    Slot,
    Template,
    TemplateError,
    assign,
    bind,
    describe_bound,
    expand_media,
    media_kind,
    to_yaml,
)


def traccia(tmp_path, nome: str = "audio.m4a", durata: float = 12.0):
    """Una traccia audio finta, che deve solo esistere ed essere leggibile."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("serve ffmpeg")
    path = tmp_path / nome
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={durata}", str(path)], check=True)
    return path


def template(tmp_path, istanti=(0.0, 2.0, 5.0), durata=8.0, **extra) -> Template:
    """Un template minimo, con la traccia sul disco."""
    traccia(tmp_path)
    dati = {
        "name": "prova",
        "duration": durata,
        "audio": {"src": "audio.m4a", "bpm": 120.0, "offset": 0.0},
        "format": {"size": [640, 360], "fps": 30},
        "slots": [{"at": t, **extra} for t in istanti],
    }
    tpl = Template.from_dict(dati)
    tpl.root = tmp_path
    return tpl


def video(tmp_path, nome: str, durata: float = 5.0):
    if shutil.which("ffmpeg") is None:
        pytest.skip("serve ffmpeg")
    path = tmp_path / nome
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"testsrc=size=320x180:rate=30:duration={durata}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


# -- lettura e validazione --------------------------------------------------

def test_gli_istanti_devono_crescere(tmp_path):
    with pytest.raises(TemplateError, match="non viene dopo"):
        template(tmp_path, istanti=(0.0, 3.0, 1.0))


def test_il_primo_slot_parte_da_zero(tmp_path):
    with pytest.raises(TemplateError, match="at: 0"):
        template(tmp_path, istanti=(0.5, 2.0))


def test_uno_slot_oltre_la_fine_non_si_vedrebbe_mai(tmp_path):
    with pytest.raises(TemplateError, match="non si vedrebbe mai"):
        template(tmp_path, istanti=(0.0, 9.0), durata=8.0)


def test_un_template_senza_traccia_non_e_un_template_audio():
    with pytest.raises(TemplateError, match="sezione 'audio'"):
        Template.from_dict({"duration": 5.0, "slots": [{"at": 0.0}]})


def test_un_template_senza_slot_non_ha_posti(tmp_path):
    with pytest.raises(TemplateError, match="almeno uno slot"):
        Template.from_dict({
            "duration": 5.0,
            "audio": {"src": "a.m4a"},
            "slots": [],
        })


def test_una_transizione_piu_lunga_dello_spazio_fra_due_tagli(tmp_path):
    with pytest.raises(TemplateError, match="non c'e' spazio"):
        template(tmp_path, istanti=(0.0, 0.5), transition=1.0,
                 transition_type="crossfade")


def test_i_nomi_sbagliati_si_leggono_subito(tmp_path):
    with pytest.raises(TemplateError, match="motion 'zoom_laterale' non esiste"):
        template(tmp_path, motion="zoom_laterale")
    with pytest.raises(TemplateError, match="transition_type 'tendina' non esiste"):
        template(tmp_path, transition=0.2, transition_type="tendina")


# -- le misure --------------------------------------------------------------

def test_ogni_slot_possiede_il_tempo_fino_al_successivo(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 2.0, 5.0), durata=8.0)
    assert tpl.gaps() == pytest.approx([2.0, 3.0, 3.0])


def test_uno_slot_con_dissolvenza_chiede_piu_materiale(tmp_path):
    """
    Il tempo che possiede e' quello fra due tagli; quello che deve MOSTRARE e'
    di piu', perche' entra in anticipo.
    """
    tpl = template(tmp_path, istanti=(0.0, 2.0, 5.0), durata=8.0,
                   transition=0.5, transition_type="crossfade")
    assert tpl.gaps() == pytest.approx([2.0, 3.0, 3.0])
    assert tpl.spans() == pytest.approx([2.0, 3.5, 3.5])


def test_i_battiti_per_slot_si_leggono_dal_tempo(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 2.0), durata=4.0)   # 120 BPM = 0.5s
    assert tpl.beats_per_slot == pytest.approx([4.0, 4.0])


# -- i media ----------------------------------------------------------------

def test_il_secondo_di_partenza_si_scrive_con_la_chiocciola():
    ref = MediaRef.parse("riprese.mp4@12.5")
    assert ref.path.name == "riprese.mp4"
    assert ref.start == 12.5


def test_una_chiocciola_che_non_precede_un_numero_e_parte_del_nome():
    ref = MediaRef.parse("foto@casa.jpg")
    assert ref.path.name == "foto@casa.jpg"
    assert ref.start == 0.0


def test_il_tipo_si_deduce_dall_estensione():
    from pathlib import Path

    assert media_kind(Path("a.JPG")) == "image"
    assert media_kind(Path("a.mov")) == "video"


def test_una_cartella_si_espande_in_ordine_alfabetico(tmp_path):
    for nome in ("c.jpg", "a.jpg", "b.png"):
        (tmp_path / nome).write_bytes(b"x")
    (tmp_path / "appunti.txt").write_text("non e' un media")

    refs = expand_media([str(tmp_path)])
    assert [r.path.name for r in refs] == ["a.jpg", "b.png", "c.jpg"]


def test_una_cartella_senza_media_e_un_errore(tmp_path):
    (tmp_path / "appunti.txt").write_text("niente")
    with pytest.raises(TemplateError, match="non contiene media"):
        expand_media([str(tmp_path)])


# -- l'assegnazione ---------------------------------------------------------

def test_con_pochi_media_si_ricomincia_da_capo(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 1.0, 2.0, 3.0))
    media = [MediaRef(tmp_path / "a.jpg"), MediaRef(tmp_path / "b.jpg")]

    scelti, avvisi = assign(tpl, media)
    assert [m.path.name for m in scelti] == ["a.jpg", "b.jpg", "a.jpg", "b.jpg"]
    assert any("si ripetono" in a for a in avvisi)


def test_con_strict_il_numero_deve_essere_esatto(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 1.0, 2.0))
    with pytest.raises(TemplateError, match="strict"):
        assign(tpl, [MediaRef(tmp_path / "a.jpg")], strict=True)


def test_i_media_di_troppo_restano_fuori(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 1.0))
    media = [MediaRef(tmp_path / f"{n}.jpg") for n in "abc"]

    scelti, avvisi = assign(tpl, media)
    assert len(scelti) == 2
    assert any("restano fuori" in a for a in avvisi)


def test_senza_media_non_si_monta_niente(tmp_path):
    with pytest.raises(TemplateError, match="almeno un media"):
        assign(template(tmp_path), [])


# -- l'applicazione ---------------------------------------------------------

def test_il_progetto_generato_mette_i_tagli_dove_dice_il_template(tmp_path):
    """La proprieta' che giustifica tutto: gli istanti sopravvivono."""
    tpl = template(tmp_path, istanti=(0.0, 2.0, 5.0), durata=8.0)
    media = [MediaRef(tmp_path / f"{n}.jpg") for n in "abc"]

    bound = bind(tpl, media, root=tmp_path)
    assert [s["at"] for s in bound.data["timeline"]] == [0.0, 2.0, 5.0]

    # E il Project che ne esce li conferma, perche' e' lui che verra' montato.
    project = Project.from_dict(bound.data)
    assert project.cut_positions() == [0.0, 2.0, 5.0]


def test_l_ultimo_slot_dice_dove_finisce(tmp_path):
    """
    Tutti gli altri li chiude il taglio successivo; l'ultimo no, e senza una
    durata esplicita il montaggio non saprebbe dove fermarsi.
    """
    tpl = template(tmp_path, istanti=(0.0, 2.0, 5.0), durata=8.0)
    bound = bind(tpl, [MediaRef(tmp_path / "a.jpg")], root=tmp_path)

    assert bound.data["timeline"][-1]["duration"] == pytest.approx(3.0)
    Project.from_dict(bound.data).validate_positions()      # non deve sollevare


def test_la_traccia_del_template_sostituisce_l_audio_dei_media(tmp_path):
    tpl = template(tmp_path)
    bound = bind(tpl, [MediaRef(video(tmp_path, "v.mp4"))], root=tmp_path)

    assert bound.data["audio"]["replace"] is True
    assert all(s["mute"] for s in bound.data["timeline"] if s["type"] == "video")


def test_con_keep_audio_le_due_tracce_si_sommano(tmp_path):
    tpl = template(tmp_path)
    bound = bind(tpl, [MediaRef(video(tmp_path, "v.mp4"))], root=tmp_path, keep_audio=True)

    assert bound.data["audio"]["replace"] is False
    assert not any(s["mute"] for s in bound.data["timeline"] if s["type"] == "video")


def test_il_formato_si_puo_cambiare_quando_si_applica(tmp_path):
    tpl = template(tmp_path)
    bound = bind(tpl, [MediaRef(tmp_path / "a.jpg")], size=(1080, 1920), fps=25,
                 root=tmp_path)

    assert bound.data["output"]["size"] == [1080, 1920]
    assert bound.data["output"]["fps"] == 25


def test_il_movimento_vale_solo_per_le_foto(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 2.0), motion="zoom_in")
    bound = bind(tpl, [MediaRef(tmp_path / "a.jpg"), MediaRef(video(tmp_path, "v.mp4"))],
                 root=tmp_path)

    foto, ripresa = bound.data["timeline"]
    assert foto["motion"] == "zoom_in"
    assert "motion" not in ripresa      # un video si muove gia' per conto suo


def test_un_video_corto_viene_rallentato_per_arrivare_in_fondo(tmp_path):
    """
    Il taglio successivo cade sul battito, e quel battito non si sposta per
    fare spazio a un video corto: si allunga il video.
    """
    corto = video(tmp_path, "corto.mp4", durata=1.0)
    tpl = template(tmp_path, istanti=(0.0, 2.0), durata=4.0)

    bound = bind(tpl, [MediaRef(corto)], root=tmp_path,
                 durations={corto.resolve(): 1.0})

    assert bound.data["timeline"][0]["speed"] == pytest.approx(0.5, abs=0.001)
    assert any("rallentato" in a for a in bound.warnings)


def test_un_video_troppo_corto_e_un_errore_leggibile(tmp_path):
    corto = video(tmp_path, "lampo.mp4", durata=0.2)
    tpl = template(tmp_path, istanti=(0.0, 4.0), durata=8.0)

    with pytest.raises(TemplateError, match="fermo immagine"):
        bind(tpl, [MediaRef(corto)], root=tmp_path, durations={corto.resolve(): 0.2})


def test_un_punto_di_partenza_oltre_la_fine_del_file(tmp_path):
    clip = video(tmp_path, "v.mp4", durata=3.0)
    tpl = template(tmp_path)

    with pytest.raises(TemplateError, match="non c'e' niente dopo"):
        bind(tpl, [MediaRef(clip, start=5.0)], root=tmp_path,
             durations={clip.resolve(): 3.0})


def test_senza_la_traccia_il_template_non_e_applicabile(tmp_path):
    tpl = template(tmp_path)
    (tmp_path / "audio.m4a").unlink()

    with pytest.raises(TemplateError, match="senza la sua traccia"):
        bind(tpl, [MediaRef(tmp_path / "a.jpg")], root=tmp_path)


def test_il_progetto_generato_si_puo_salvare_e_rileggere(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 2.0), durata=4.0)
    bound = bind(tpl, [MediaRef(tmp_path / "a.jpg")], root=tmp_path)

    testo = to_yaml(bound)
    (tmp_path / "timeline.yaml").write_text(testo, encoding="utf-8")

    riletto = Project.from_yaml(tmp_path / "timeline.yaml")
    assert riletto.cut_positions() == [0.0, 2.0]


def test_i_percorsi_dentro_la_cartella_restano_relativi(tmp_path):
    """Un progetto con percorsi relativi si puo' spostare; con gli assoluti no."""
    tpl = template(tmp_path, istanti=(0.0, 2.0), durata=4.0)
    (tmp_path / "foto.jpg").write_bytes(b"x")

    bound = bind(tpl, [MediaRef(tmp_path / "foto.jpg")], root=tmp_path)
    assert bound.data["timeline"][0]["src"] == "foto.jpg"
    assert bound.data["audio"]["src"] == "audio.m4a"


def test_il_piano_di_montaggio_si_legge_prima_di_esportare(tmp_path):
    tpl = template(tmp_path, istanti=(0.0, 2.0), durata=4.0)
    bound = bind(tpl, [MediaRef(tmp_path / "a.jpg")], root=tmp_path)

    testo = describe_bound(tpl, bound)
    assert "prova" in testo
    assert "a.jpg" in testo
    assert "120 BPM" in testo


def test_un_template_si_rilegge_da_disco(tmp_path):
    """Il giro completo: si scrive un template.yaml, si rilegge, e torna."""
    traccia(tmp_path)
    (tmp_path / "template.yaml").write_text(
        "name: giro\n"
        "duration: 6.0\n"
        "audio:\n  src: audio.m4a\n  bpm: 100\n"
        "format:\n  size: [720, 1280]\n  fps: 24\n"
        "slots:\n  - at: 0.0\n  - at: 3.0\n    motion: pan_up\n",
        encoding="utf-8",
    )

    tpl = Template.from_yaml(tmp_path)
    assert tpl.name == "giro"
    assert tpl.size == (720, 1280)
    assert tpl.fps == 24
    assert tpl.slots[1].motion == "pan_up"
    assert tpl.gaps() == pytest.approx([3.0, 3.0])


def test_bound_e_una_struttura_non_un_dizionario_libero(tmp_path):
    """Il Bound sa costruirsi il Project: e' l'unico modo previsto di usarlo."""
    tpl = template(tmp_path, istanti=(0.0, 2.0), durata=4.0)
    bound = bind(tpl, [MediaRef(tmp_path / "a.jpg")], root=tmp_path)

    assert isinstance(bound, Bound)
    project = bound.project(tmp_path)
    assert project.root == tmp_path.resolve()
    assert len(project.timeline) == 2


def test_lo_slot_conserva_solo_quello_che_si_discosta_dal_normale():
    """Un template scritto per intero sarebbe illeggibile: si scrive il diverso."""
    assert Slot(at=1.5).to_dict() == {"at": 1.5}
    assert Slot(at=1.5, motion="zoom_in", amount=0.2).to_dict() == {
        "at": 1.5, "motion": "zoom_in", "amount": 0.2,
    }


def test_il_battito_di_una_traccia_si_converte_in_istanti():
    audio = AudioTrack(src="a.m4a", bpm=120.0, offset=0.25)
    assert audio.period == pytest.approx(0.5)
    assert audio.beat_of(2.25) == pytest.approx(4.0)
