# -*- coding: utf-8 -*-
"""core/paths.py — chemins système et horodatages."""
import os
from datetime import datetime

# Racine du programme (dossier contenant main.py), parent de core/. Indépendante
# du répertoire de lancement — même ancrage que les logs (core/logger.py).
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_export_dir() -> str:
    """Dossier des exports réels : <programme>/export.
    Ancré sur la racine du programme (pas le CWD) pour ne plus déverser les
    classeurs à côté du code. Le dossier est créé au besoin par ExportXLS.ouvrir()."""
    return os.path.join(_RACINE, "export")


def nom_fichier_xls(indice_notation: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    indice_safe = (
        indice_notation.strip()
        .replace(" ", "_")
        .replace("/", "-")
        .replace("\\", "-")
    )
    return f"{indice_safe}_{ts}.xlsx"


def horodatage_lisible() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def get_desktop_path() -> str:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        try:
            return winreg.QueryValueEx(key, "Desktop")[0]
        finally:
            key.Close()
    except Exception:
        return os.path.expanduser("~")
