# -*- coding: utf-8 -*-
"""core/logger.py — fabrique de logger (console INFO + fichier DEBUG)."""
import logging
import os
from datetime import datetime
from typing import Optional

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def creer_logger(nom: str = "ipq", dossier_log: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(nom)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        fmt="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if dossier_log is None:
        dossier_log = _RACINE

    horodatage_fichier = datetime.now().strftime("%Y%m%d_%H%M%S")
    chemin_log = os.path.join(dossier_log, "logs", f"ipq_{horodatage_fichier}.log")

    try:
        os.makedirs(os.path.dirname(chemin_log), exist_ok=True)
        fh = logging.FileHandler(chemin_log, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.info("Journal démarré : %s", chemin_log)
    except OSError as e:
        logger.warning("Impossible de créer le fichier log : %s", e)

    return logger
