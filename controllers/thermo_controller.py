# -*- coding: utf-8 -*-
"""controllers/thermo_controller.py — relie ThermoService (Modèle) à la topbar (Vue) via after()."""


class ThermoController:
    """Marshale les mesures du service thermo vers les variables Tk de la topbar."""

    def __init__(self, window, var_t, var_hr, service) -> None:
        self._win = window
        self._var_t = var_t
        self._var_hr = var_hr
        self._service = service

    def demarrer(self) -> None:
        self._service.demarrer(
            on_mesure=self._on_mesure,
            on_indispo=self._on_indispo,
            on_erreur=self._on_erreur,
        )

    def arreter(self) -> None:
        self._service.arreter()

    def _afficher(self, txt_t: str, txt_hr: str) -> None:
        self._var_t.set(txt_t)
        self._var_hr.set(txt_hr)

    def _on_mesure(self, t, hr) -> None:
        self._win.after(0, lambda: self._afficher(f"T: {t:.1f} °C", f"RH: {hr:.1f} %"))

    def _on_indispo(self) -> None:
        self._win.after(0, lambda: self._afficher("T: — °C", "RH: — %"))

    def _on_erreur(self, exc) -> None:
        self._win.after(0, lambda: self._afficher("T: error", "RH: error"))
