# -*- coding: utf-8 -*-
"""controllers/live_mesure_controller.py — relie LiveMesureService (Modèle) à
l'afficheur de tension de la topbar (Vue) via after(). Jumeau du ThermoController."""
from core.config import label_multimetre


class LiveMesureController:
    """Marshale les lectures multimètre du service live vers les variables Tk de la topbar."""

    def __init__(self, window, vars_par_cible, service) -> None:
        self._win = window
        self._vars = dict(vars_par_cible)   # 'com1' -> tk.StringVar
        self._service = service

    def demarrer(self) -> None:
        self._service.demarrer(on_mesure=self._on_mesure, on_indispo=self._on_indispo)

    def arreter(self) -> None:
        self._service.arreter()

    @staticmethod
    def _format(cible: str, val) -> str:
        # 'com1' -> 'UR', 'com2' -> 'UL'. Format :.6g -> lisible du très petit (6.1e-08) à ~1.0.
        court = label_multimetre(cible)
        return f"{court}: — V" if val is None else f"{court}: {val:.6g} V"

    def _afficher(self, cible: str, val) -> None:
        var = self._vars.get(cible)
        if var is not None:
            var.set(self._format(cible, val))

    def _on_mesure(self, cible, val) -> None:
        self._win.after(0, lambda c=cible, v=val: self._afficher(c, v))

    def _on_indispo(self, cible) -> None:
        self._win.after(0, lambda c=cible: self._afficher(c, None))
