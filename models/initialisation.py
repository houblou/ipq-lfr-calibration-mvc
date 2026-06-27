# -*- coding: utf-8 -*-

import threading
from datetime import datetime
from typing import Callable, List, Optional

from core.logger import creer_logger

logger = creer_logger("phase5")


class GestionInitialisation:
    """
    Gère la séquence d'initialisation (Init COM1 + Init COM2), la sélection X
    et la distance lampe-capteur, avant le lancement de la boucle de calibration.
    """

    def __init__(self, gestion_ports) -> None:
        self.gp           = gestion_ports
        self.nb_series:    int   = 5
        self.distance_mm:  float = 0.0

        # ── État initialisation ───────────────────────────────────────────
        self.init1_ok:     bool  = False
        self.init2_ok:     bool  = False
        self.init_validee: bool  = False

        self.n_init1:     Optional[List] = None
        self.m_init1:     Optional[float] = None
        self.v_init1:     Optional[float] = None
        self.t_moy_init1: Optional[float] = None
        self.hr_moy_init1:Optional[float] = None

        self.n_init2:     Optional[List] = None
        self.m_init2:     Optional[float] = None
        self.v_init2:     Optional[float] = None
        self.t_moy_init2: Optional[float] = None
        self.hr_moy_init2:Optional[float] = None

    # ── Initialisation ────────────────────────────────────────────────────────

    def lancer_init(
        self,
        cible: str,
        acq_instance,
        callback_point: Optional[Callable] = None,
        callback_fin:   Optional[Callable] = None,
    ) -> None:
        """
        Lance l'acquisition d'init pour 'cible' ('com1' ou 'com2') dans un thread.
        Utilise acq_instance.lancer_init(cible, ...).
        callback_fin(M, V, T_moy, HR_moy, date, heure) appelé à la fin (sauf arrêt).
        """
        def _run():
            n, m, v, t_moy, hr_moy = acq_instance.lancer_init(
                cible,
                callback_point=callback_point,
            )

            # Acquisition interrompue : on ne valide pas cette init
            if getattr(acq_instance, "arrete", False):
                logger.warning("Init %s interrompue — non enregistrée.", cible.upper())
                if callback_fin:
                    callback_fin(None, None, None, None, None, None)
                return

            date  = datetime.now().strftime("%d/%m/%Y")
            heure = datetime.now().strftime("%H:%M:%S")

            if cible == "com1":
                self.n_init1, self.m_init1, self.v_init1 = n, m, v
                self.t_moy_init1, self.hr_moy_init1 = t_moy, hr_moy
                self.init1_ok = True
                logger.info("Init COM1 — M=%.6f V=%.6f", m, v)
            else:
                self.n_init2, self.m_init2, self.v_init2 = n, m, v
                self.t_moy_init2, self.hr_moy_init2 = t_moy, hr_moy
                self.init2_ok = True
                logger.info("Init COM2 — M=%.6f V=%.6f", m, v)

            # Toute nouvelle acquisition d'init annule une validation précédente
            self.init_validee = False

            if callback_fin:
                callback_fin(m, v, t_moy, hr_moy, date, heure)

        threading.Thread(target=_run, daemon=True,
                          name=f"thread-init-{cible}").start()

    def exporter_inits(self, export_xls) -> None:
        """
        Exporte Init COM1 PUIS Init COM2 dans le fichier Excel.
        Les deux initialisations sont obligatoires, indépendamment du COM
        choisi pour les X séries. Appelé après valider_init().
        """
        dist  = self.distance_mm
        date  = datetime.now().strftime("%d/%m/%Y")
        heure = datetime.now().strftime("%H:%M:%S")

        if self.init1_ok and self.n_init1 is not None:
            export_xls.ajouter_serie(
                self.n_init1, self.m_init1, self.v_init1,
                self.t_moy_init1, self.hr_moy_init1,
                dist, date, heure, label="Init COM1",
            )
        if self.init2_ok and self.n_init2 is not None:
            export_xls.ajouter_serie(
                self.n_init2, self.m_init2, self.v_init2,
                self.t_moy_init2, self.hr_moy_init2,
                dist, date, heure, label="Init COM2",
            )
        logger.info("Colonnes Init COM1 / Init COM2 exportées.")

    def valider_init(self) -> bool:
        """Valide l'init seulement si COM1 ET COM2 sont terminés (obligatoire)."""
        if not (self.init1_ok and self.init2_ok):
            logger.warning("Validation impossible — Init COM1 OK=%s, Init COM2 OK=%s",
                           self.init1_ok, self.init2_ok)
            return False
        self.init_validee = True
        logger.info("Initialisation validée par l'opérateur.")
        return True

    def reinitialiser(self) -> None:
        """Remet l'état d'init à zéro."""
        self.init1_ok = self.init2_ok = self.init_validee = False
        self.n_init1 = self.m_init1 = self.v_init1 = None
        self.n_init2 = self.m_init2 = self.v_init2 = None
        logger.info("État initialisation réinitialisé.")

    # ── Paramètres ────────────────────────────────────────────────────────────

    def definir_nb_series(self, x: int) -> None:
        if x < 1:
            raise ValueError("X doit être >= 1.")
        self.nb_series = x
        logger.info("X = %d séries", x)

    def definir_distance(self, distance_mm: float) -> None:
        if distance_mm < 0:
            raise ValueError("Distance >= 0.")
        self.distance_mm = distance_mm
        logger.info("Distance = %.1f mm", distance_mm)
