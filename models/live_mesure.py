# -*- coding: utf-8 -*-
"""models/live_mesure.py — lecture continue des multimètres pour l'afficheur « cadran »
de la topbar (thread dédié, sans UI).

Jumeau du ThermoService : il lit en boucle la valeur de com1/com2 et la pousse via
callbacks, pour offrir un affichage permanent façon multimètre de paillasse,
INDÉPENDAMMENT des acquisitions.

Comme le thermo, il se met en pause pendant une acquisition (est_occupe() -> True) :
interroger le multimètre en parallèle de la boucle d'acquisition lui volerait des
mesures (un HP 3458A en poussée continue pousse UNE valeur par lecture — un read
parasite la détournerait de la série en cours).
"""
import threading
import time
from typing import Callable, Iterable, Optional

from core.logger import creer_logger

logger = creer_logger("phase2")

INTERVALLE_S = 1.0


class LiveMesureService:
    """Lit en continu la valeur des multimètres et la pousse via callbacks (ne touche aucun widget)."""

    def __init__(
        self,
        gestion_ports,
        cibles: Iterable[str] = ("com1", "com2"),
        est_occupe: Optional[Callable[[], bool]] = None,
        intervalle_s: float = INTERVALLE_S,
    ) -> None:
        self.gp = gestion_ports
        self._cibles = tuple(cibles)
        self._est_occupe = est_occupe or (lambda: False)
        self._intervalle = intervalle_s
        self._actif = False
        self._thread: Optional[threading.Thread] = None

    def demarrer(
        self,
        on_mesure: Callable[[str, float], None],
        on_indispo: Callable[[str], None],
    ) -> None:
        if self._actif:
            return
        self._actif = True
        self._thread = threading.Thread(
            target=self._boucle,
            args=(on_mesure, on_indispo),
            daemon=True,
            name="thread-live-mesure",
        )
        self._thread.start()

    def arreter(self) -> None:
        # Attendre la fin de la lecture en cours avant de rendre la main, pour que
        # fermer_tout() ne ferme pas un port pendant que ce thread lit dessus
        # (même garde que ThermoService.arreter).
        self._actif = False
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._intervalle + 0.5)
        self._thread = None

    def _boucle(self, on_mesure, on_indispo) -> None:
        while self._actif:
            if not self._est_occupe():
                for cible in self._cibles:
                    if not self._actif:
                        break
                    # role_connecte gère le bus (série vs VISA) ; en simulation on lit
                    # quand même pour animer l'afficheur avec des valeurs synthétiques.
                    if not (self.gp.mode_simulation or self.gp.role_connecte(cible)):
                        on_indispo(cible)
                        continue
                    valeur = self.gp.lire_com(cible)
                    # Contexte métrologique : sur échec, on affiche « — » (jamais la
                    # dernière valeur recopiée, qui passerait pour une mesure vivante).
                    if valeur is None:
                        on_indispo(cible)
                    else:
                        on_mesure(cible, valeur)
            time.sleep(self._intervalle)
