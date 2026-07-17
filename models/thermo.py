# -*- coding: utf-8 -*-
"""models/thermo.py — service de lecture continue du thermohygromètre (thread dédié, sans UI)."""
import threading
import time
from typing import Callable, Optional

from core.logger import creer_logger

logger = creer_logger("thermo")

INTERVALLE_S = 2.0


class ThermoService:
    """Lit T/HR en continu dans son propre thread et pousse via callbacks (ne touche aucun widget)."""

    def __init__(
        self,
        gestion_ports,
        est_occupe: Optional[Callable[[], bool]] = None,
        intervalle_s: float = INTERVALLE_S,
    ) -> None:
        self.gp = gestion_ports
        self._est_occupe = est_occupe or (lambda: False)
        self._intervalle = intervalle_s
        self._actif = False
        self._thread: Optional[threading.Thread] = None

    def demarrer(
        self,
        on_mesure: Callable[[float, float], None],
        on_indispo: Callable[[], None],
        on_erreur: Callable[[Exception], None],
    ) -> None:
        if self._actif:
            return
        self._actif = True
        self._thread = threading.Thread(
            target=self._boucle,
            args=(on_mesure, on_indispo, on_erreur),
            daemon=True,
            name="thread-thermo",
        )
        self._thread.start()

    def arreter(self) -> None:
        # E: Wait for the current read to complete before returning, so that
        # fermer_tout() does not close the port while this thread is reading from it.
        self._actif = False
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._intervalle + 0.5)
        self._thread = None

    def _boucle(self, on_mesure, on_indispo, on_erreur) -> None:
        while self._actif:
            if not self._est_occupe():
                try:
                    if not self.gp.thermo_actif():
                        on_indispo()
                    else:
                        t, hr = self.gp.lire_thermo()
                        on_mesure(t, hr)
                except Exception as exc:
                    logger.exception("Thermohygrometer read failed: %s", exc)
                    on_erreur(exc)
            time.sleep(self._intervalle)
