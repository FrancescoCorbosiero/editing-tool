"""
Trovare un font utilizzabile, che e' il problema numero uno del testo su video.

MoviePy disegna il testo con Pillow, che vuole il **percorso di un file** `.ttf`
o `.otf`: non conosce i nomi dei font installati come farebbe un word processor.
Se non gli si dice niente ripiega su un font interno minimale, che a 60 pixel di
altezza si vede che e' un ripiego. Su altri sistemi la stessa chiamata fallisce
del tutto: e' la ragione per cui in rete si trovano decine di segnalazioni di
"TextClip non funziona".

Questo modulo risolve la faccenda in tre modi, in ordine di precedenza:
  1. un percorso esplicito nel YAML (relativo alla cartella del progetto);
  2. un nome di font, cercato fra quelli installati nel sistema;
  3. un font di sistema scelto da noi fra quelli quasi sempre presenti.

Nessun font viene distribuito con il repo: sono file binari con licenze proprie,
e ogni sistema operativo ne ha gia' di ottimi. `python -m vedit fonts` mostra
cosa e' stato trovato su questa macchina.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

FONT_SUFFIXES = (".ttf", ".otf", ".ttc")

# Cartelle in cui i tre sistemi operativi tengono i font.
SEARCH_DIRS: tuple[str, ...] = (
    # Linux
    "/usr/share/fonts", "/usr/local/share/fonts", "~/.fonts", "~/.local/share/fonts",
    # macOS
    "/System/Library/Fonts", "/Library/Fonts", "~/Library/Fonts",
    # Windows
    "C:/Windows/Fonts", "~/AppData/Local/Microsoft/Windows/Fonts",
)

# Font preferiti, in ordine: i primi sono quelli piu' probabili su Linux, poi
# macOS, poi Windows. Sono tutti caratteri senza grazie, leggibili in sovrimpressione.
PREFERRED = (
    "DejaVuSans", "LiberationSans-Regular", "FreeSans", "NotoSans-Regular",
    "Helvetica", "HelveticaNeue", "SFNSText", "Arial", "arial",
    "segoeui", "Verdana", "verdana",
)


def _normalize(name: str) -> str:
    """Confronto tollerante fra nomi: 'Noto Sans' e 'NotoSans' sono lo stesso font."""
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


@lru_cache(maxsize=1)
def installed_fonts() -> dict[str, Path]:
    """
    Mappa nome normalizzato -> percorso, per tutti i font trovati nel sistema.

    Il risultato viene messo in cache: la scansione delle cartelle di sistema
    puo' costare qualche decina di millisecondi e il set non cambia in corsa.
    """
    found: dict[str, Path] = {}
    for raw in SEARCH_DIRS:
        directory = Path(raw).expanduser()
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.suffix.lower() in FONT_SUFFIXES:
                found.setdefault(_normalize(path.stem), path)
    return found


def default_font() -> Path | None:
    """Il primo font della lista di preferenza presente sul sistema."""
    available = installed_fonts()
    for name in PREFERRED:
        path = available.get(_normalize(name))
        if path is not None:
            return path
    # Nessuno dei preferiti: va bene qualsiasi cosa, purche' esista davvero.
    return next(iter(sorted(available.values())), None)


def find_font(value: str | None, root: Path | None = None) -> Path | None:
    """
    Risolve quello che c'e' scritto nel YAML in un file di font.

    `value` puo' essere un percorso (assoluto o relativo alla cartella del
    progetto) oppure il nome di un font installato. `None` chiede il default.
    """
    if not value:
        return default_font()

    candidate = Path(value).expanduser()
    if candidate.suffix.lower() in FONT_SUFFIXES:
        if not candidate.is_absolute() and root is not None:
            candidate = root / candidate
        return candidate if candidate.exists() else None

    return installed_fonts().get(_normalize(str(value)))


def font_error_message(value: str | None) -> str:
    """Messaggio d'errore che dice anche come uscirne."""
    if value:
        richiesta = f"Font non trovato: '{value}'."
    else:
        richiesta = "Nessun font utilizzabile trovato sul sistema."

    esempi = ", ".join(sorted(installed_fonts())[:6]) or "nessuno"
    return (
        f"{richiesta}\n"
        "  Indica il percorso di un file .ttf/.otf nel campo 'font', oppure il\n"
        "  nome di un font installato. Font disponibili su questa macchina\n"
        f"  (i primi in ordine alfabetico): {esempi}\n"
        "  Elenco completo: python -m vedit fonts"
    )


def wrap_text(text: str, font_path: Path, font_size: int, max_width: float,
              stroke_width: int = 0) -> str:
    """
    Manda a capo il testo alle parole, entro `max_width` pixel.

    Perche' non usiamo quello di MoviePy: il suo `method="caption"` spezza
    *dentro* le parole ("larghe / zza") quando il testo occupa piu' di due
    righe, perche' mescola indici assoluti e relativi mentre accumula le righe.
    Misurare qui con Pillow costa una frazione di millisecondi per battuta e
    da' un risultato corretto - e in piu' il riquadro di sfondo resta largo
    quanto la riga piu' lunga, invece di allargarsi sempre al massimo.

    Le andate a capo gia' presenti nel testo (quelle di un .srt, per esempio)
    vengono rispettate: sono scelte di chi ha scritto, non incidenti.
    """
    from PIL import ImageFont

    font = ImageFont.truetype(str(font_path), font_size)
    limit = max_width - 2 * stroke_width

    def measure(value: str) -> float:
        return font.getlength(value)

    def break_word(word: str) -> list[str]:
        """Ultima risorsa: una parola sola piu' larga della riga va spezzata."""
        pieces, current = [], ""
        for char in word:
            if current and measure(current + char) > limit:
                pieces.append(current)
                current = char
            else:
                current += char
        if current:
            pieces.append(current)
        return pieces

    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if measure(candidate) <= limit:
                current = candidate
                continue

            if current:                    # la riga in corso e' piena: si chiude
                lines.append(current)
                current = ""
            if measure(word) > limit:      # parola piu' larga dell'intera riga
                *pieces, current = break_word(word)
                lines.extend(pieces)
            else:
                current = word
        lines.append(current)

    return "\n".join(lines)


def describe() -> str:
    """Testo del comando `vedit fonts`."""
    available = installed_fonts()
    scelto = default_font()

    lines = [f"Sistema  : {sys.platform}"]
    lines.append(f"Font trovati: {len(available)}")
    lines.append(f"Predefinito : {scelto if scelto else 'NESSUNO (indica un font nel YAML)'}")
    if available:
        lines.append("")
        lines.append("Nomi utilizzabili nel campo 'font':")
        for name in sorted(available):
            lines.append(f"  {name:<28} {available[name]}")
    return "\n".join(lines)
