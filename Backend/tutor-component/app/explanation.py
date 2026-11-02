"""Explicación del informe generada por el Tutor.

En esta entrega ``LLM_PROVIDER=mock``: el texto es determinista y se construye
a partir del ``summary`` que calcula el Analysis Worker. Se guarda en el
documento la primera vez que se lee el resultado, para no regenerarlo en cada
consulta. Un proveedor real de LLM queda fuera de esta entrega (sección 13).
"""

from __future__ import annotations

from typing import Any

_LABELS = {
    "es": {
        "white": "Blancas",
        "black": "Negras",
        "best": ("mejor", "mejores"),
        "good": ("buena", "buenas"),
        "inaccuracy": ("imprecisión", "imprecisiones"),
        "mistake": ("error", "errores"),
        "blunder": ("error grave", "errores graves"),
        "and": "y",
    },
    "en": {
        "white": "White",
        "black": "Black",
        "best": ("best", "best"),
        "good": ("good", "good"),
        "inaccuracy": ("inaccuracy", "inaccuracies"),
        "mistake": ("mistake", "mistakes"),
        "blunder": ("blunder", "blunders"),
        "and": "and",
    },
}

_CATEGORIES = ("best", "good", "inaccuracy", "mistake", "blunder")


def _language(language: str | None) -> str:
    return "en" if str(language or "").lower().startswith("en") else "es"


def _counts(side: Any) -> dict[str, int]:
    data = side if isinstance(side, dict) else {}
    counts: dict[str, int] = {}
    for category in _CATEGORIES:
        value = data.get(category)
        counts[category] = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    return counts


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _join(parts: list[str], conjunction: str) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f" {conjunction} " + parts[-1]


def _side_phrase(label: str, counts: dict[str, int], words: dict[str, Any]) -> str:
    parts = []
    for category in _CATEGORIES:
        singular, plural = words[category]
        count = counts[category]
        parts.append(f"{count} {singular if count == 1 else plural}")
    return f"{label}: {_join(parts, words['and'])}."


def build_explanation(
    summary: Any,
    language: str = "es",
    detail_level: str = "standard",
) -> str:
    """Genera el texto del informe de forma determinista.

    ``language`` sigue el campo de la petición (``es`` por defecto; cualquier
    variante que empiece por ``en`` se responde en inglés). ``detail_level``
    admite ``brief``, ``standard`` (por defecto) y ``detailed``; otros valores
    se tratan como ``standard`` para no romper al frontend.
    """
    lang = _language(language)
    words = _LABELS[lang]
    level = str(detail_level or "").lower()
    mode = "brief" if level.startswith("brief") else "detailed" if level.startswith("detail") else "standard"

    data = summary if isinstance(summary, dict) else {}
    white = _counts(data.get("white"))
    black = _counts(data.get("black"))
    white_loss = _number((data.get("white") or {}).get("averageCpLoss") if isinstance(data.get("white"), dict) else 0)
    black_loss = _number((data.get("black") or {}).get("averageCpLoss") if isinstance(data.get("black"), dict) else 0)

    pieces = [
        _side_phrase(words["white"], white, words),
        _side_phrase(words["black"], black, words),
    ]

    if mode != "brief":
        if lang == "en":
            pieces.append(
                "Average loss per move: "
                f"{_format_number(white_loss)} cp for White and "
                f"{_format_number(black_loss)} cp for Black."
            )
        else:
            pieces.append(
                "Pérdida media por jugada: "
                f"{_format_number(white_loss)} cp con blancas y "
                f"{_format_number(black_loss)} cp con negras."
            )

        if white_loss == black_loss:
            pieces.append(
                "Both sides were equally precise."
                if lang == "en"
                else "Ambos bandos tuvieron una precisión parecida."
            )
        else:
            more_precise = words["white"] if white_loss < black_loss else words["black"]
            if lang == "en":
                pieces.append(f"Overall, {more_precise} played more precisely.")
            else:
                pieces.append(
                    f"En conjunto, el bando de {more_precise.lower()} fue más preciso."
                )

    if mode == "detailed":
        if lang == "en":
            pieces.append(
                "Each move is compared with the engine's best option at the requested "
                "depth: an inaccuracy costs 50 centipawns or more, a mistake 100 or "
                "more and a blunder 300 or more."
            )
        else:
            pieces.append(
                "Cada jugada se compara con la mejor opción del motor a la profundidad "
                "solicitada: una imprecisión cuesta 50 centipeones o más, un error 100 "
                "o más y un error grave 300 o más."
            )

    return " ".join(pieces)
