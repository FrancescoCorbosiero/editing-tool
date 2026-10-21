"""
Test del foglio dei provini: tanti fotogrammi di un video in un'immagine.

E' lo strumento con cui si controlla un render senza riprodurlo: deve prendere
i fotogrammi negli istanti chiesti, non altrove.
"""

import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from vedit.sheet import contact_sheet, grab, regular_times, tile_height

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="serve ffmpeg per generare il video di prova")


def video_rosso_poi_blu(tmp_path):
    """Due secondi rossi e due blu, in verticale."""
    path = tmp_path / "rb.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=red:s=180x320:r=30:d=2",
         "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=2",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


def test_gli_istanti_regolari_stanno_a_meta_degli_intervalli():
    assert regular_times(4.0, every=1.0) == [0.5, 1.5, 2.5, 3.5]
    assert regular_times(0.0) == []
    assert len(regular_times(600.0)) <= 48          # un video lungo non fa miniature minuscole


def test_il_provino_mantiene_le_proporzioni(tmp_path):
    assert tile_height(video_rosso_poi_blu(tmp_path), 90) == 160


def test_il_fotogramma_e_quello_dell_istante_chiesto(tmp_path):
    video = video_rosso_poi_blu(tmp_path)
    rosso = grab(video, 1.0, 90, 160).mean(axis=(0, 1))
    blu = grab(video, 3.0, 90, 160).mean(axis=(0, 1))
    assert rosso[0] > 150 and rosso[2] < 80
    assert blu[2] > 150 and blu[0] < 80


def test_il_foglio_ha_un_provino_per_istante(tmp_path):
    video = video_rosso_poi_blu(tmp_path)
    uscita = contact_sheet(video, [1.0, 3.0], ["1) 1.00s", "2) 3.00s"],
                           tmp_path / "provini.png", width=90, columns=2)
    foglio = np.asarray(Image.open(uscita))
    assert foglio.shape[1] == 2 * (90 + 4) + 4
    # Il primo provino e' rosso, il secondo blu
    assert foglio[40, 40, 0] > 150 and foglio[40, 40 + 94, 2] > 150
