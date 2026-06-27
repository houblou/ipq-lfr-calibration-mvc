# -*- coding: utf-8 -*-
"""models/stats.py — calculs statistiques purs (sans UI). Variance de POPULATION, ignore les None."""
import math
from typing import List, Optional, Tuple


def _valides(valeurs: List[Optional[float]]) -> List[float]:
    return [v for v in valeurs if v is not None]


def moyenne(valeurs: List[Optional[float]]) -> Optional[float]:
    vals = _valides(valeurs)
    return sum(vals) / len(vals) if vals else None


def moyenne_variance(valeurs: List[Optional[float]]) -> Tuple[float, float]:
    vals = _valides(valeurs)
    n = len(vals)
    if n == 0:
        return 0.0, 0.0
    m = sum(vals) / n
    v = sum((x - m) ** 2 for x in vals) / n
    return m, v


def moyenne_sigma(valeurs: List[Optional[float]]) -> Optional[Tuple[float, float]]:
    vals = _valides(valeurs)
    if not vals:
        return None
    m = sum(vals) / len(vals)
    sigma = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))
    return m, sigma


def alerte_variance(variance: Optional[float], seuil: float) -> bool:
    return (variance or 0.0) > seuil
