"""
Il confine architetturale: i moduli "leggeri" non devono tirarsi dietro MoviePy.

Non e' pignoleria. `probe`, `init` e `render --check` devono rispondere subito,
e i test di validazione girano in millisecondi solo finche' nessuno aggiunge un
`from moviepy import ...` in cima al modulo sbagliato. Questo test lo impedisce.
"""

import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent   # la cartella che contiene vedit/

MODULI_LEGGERI = ["vedit.models", "vedit.timeline", "vedit.transitions",
                  "vedit.report", "vedit.ffmpeg_tools"]


def importa_e_controlla(modulo: str) -> subprocess.CompletedProcess:
    # Serve un interprete pulito: se MoviePy e' gia' in sys.modules per colpa di
    # un altro test, il controllo non direbbe piu' nulla.
    codice = (
        f"import importlib, sys; importlib.import_module('{modulo}');"
        "print('moviepy' in sys.modules)"
    )
    return subprocess.run([sys.executable, "-c", codice], capture_output=True,
                          text=True, cwd=RADICE)


def test_i_moduli_leggeri_non_importano_moviepy():
    colpevoli = []
    for modulo in MODULI_LEGGERI:
        result = importa_e_controlla(modulo)
        assert result.returncode == 0, f"{modulo} non si importa: {result.stderr}"
        if result.stdout.strip() != "False":
            colpevoli.append(modulo)
    assert not colpevoli, f"questi moduli importano MoviePy: {colpevoli}"


def test_il_builder_invece_moviepy_lo_importa():
    # Controprova: se questo test fallisse, il precedente non proverebbe nulla.
    result = importa_e_controlla("vedit.builder")
    assert result.stdout.strip() == "True"
