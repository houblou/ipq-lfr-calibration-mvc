# -*- coding: utf-8 -*-
"""core/config.py — constantes de domaine (série, acquisition, audio, seuils)."""

BAUD_RATE_DEFAULT    = 9600
PARITY_DEFAULT       = 'N'
STOP_BITS_DEFAULT    = 1
DATA_BITS_DEFAULT    = 8
TIMEOUT_PORT_DEFAULT = 2.0

POLL_INTERVAL_S       = 0.5
ACQ_INTERVAL_S        = 0.9
NB_POINTS             = 30
NB_POINTS_MIN         = 2      # overlock : plancher (variance exige >= 2 points)
NB_POINTS_MAX         = 50     # overlock : plafond materiel
ATTENTE_INTER_SERIE_S = 60
BIP_FREQ_START        = 700
BIP_FREQ_END          = 1400
BIP_DUREE_MS          = 110

V_SEUIL_ALERTE        = 0.01

# ── Étiquettes d'affichage des deux multimètres (nom paillasse) ─────────────────
# Les clés internes restent 'com1'/'com2' PARTOUT dans le code (attributs, dicts,
# bus) ; seule la présentation à l'opérateur change. com1 → UR, com2 → UL.
LABELS_MULTIMETRE = {"com1": "UR", "com2": "UL"}


def label_multimetre(cible: str) -> str:
    """Nom paillasse d'un rôle multimètre : 'com1' → 'UR', 'com2' → 'UL'.
    Repli en majuscules pour toute cible non mappée (ex. 'thermo1' → 'THERMO1')."""
    return LABELS_MULTIMETRE.get(cible, cible.upper())
