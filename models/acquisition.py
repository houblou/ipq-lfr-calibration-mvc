
import time
from typing import Callable, List, Optional, Tuple

from core.logger import creer_logger
from core.config import ACQ_INTERVAL_S, NB_POINTS
from models import stats

logger = creer_logger("phase2")


class Acquisition:
    """Gère une série de 30 acquisitions et le calcul M / V / T_moy / HR_moy."""

    def __init__(self, gestion_ports) -> None:
        self.gp = gestion_ports
        self.n:       List[Optional[float]] = []
        self.t_vals:  List[float] = []
        self.hr_vals: List[float] = []
        self.moyenne:  Optional[float] = None
        self.variance: Optional[float] = None
        self.t_moy:    Optional[float] = None
        self.hr_moy:   Optional[float] = None

        # ── Contrôle d'arrêt ───────────────────────────────────────────────
        self._arret  = False   # demande d'arrêt (positionné depuis un autre thread)
        self.arrete  = False   # True si la dernière exécution a été interrompue

    def demander_arret(self) -> None:
        """Demande l'arrêt de la boucle en cours (thread-safe : simple flag)."""
        self._arret = True

    def lancer(self, cible: str = "com1", callback_point=None, callback_fin=None):
        """Acquiert 30 points sur UN SEUL multimètre (cible = 'com1' ou 'com2').
        L'autre COM n'est jamais interrogé."""
        return self._boucle(
            f"acquisition {cible.upper()}",
            lambda: (self._lire_avec_retry(cible),),
            callback_point, callback_fin,
        )

    def lancer_init(self, cible: str, callback_point=None, callback_fin=None):
        return self._boucle(
            f"init {cible.upper()}",
            lambda: (self._lire_avec_retry(cible),),
            callback_point, callback_fin,
        )

    def _boucle(self, contexte: str, lire_fn, callback_point, callback_fin):
        self._reset_buffers()
        logger.info("Début %s — %d points, %.0f ms", contexte, NB_POINTS, ACQ_INTERVAL_S * 1000)
        for i in range(1, NB_POINTS + 1):
            if self._arret:
                break
            valeurs = lire_fn()
            self.n.append(valeurs[0])
            # Temperature read BETWEEN measurements to avoid simultaneous GPIB access
            if not self._sleep_interruptible(ACQ_INTERVAL_S / 2):
                break
            # B : un glitch thermo ponctuel (trame RUSKA muette, etc.) ne doit pas
            # tuer la série. On réutilise la dernière valeur connue ; mais si la
            # toute première lecture échoue, on laisse remonter pour échouer proprement.
            try:
                t, hr = self.gp.lire_thermo()
            except Exception as exc:
                if not self.t_vals:
                    raise
                t, hr = self.t_vals[-1], self.hr_vals[-1]
                logger.warning("%s: thermo read failed at point %d, reusing last value: %s",
                               contexte, i, exc)
            self.t_vals.append(t)
            self.hr_vals.append(hr)
            logger.debug("%s N[%d] = %s  T=%.1f HR=%.1f", contexte, i, valeurs, t, hr)
            if callback_point:
                callback_point(i, *valeurs, t, hr)
            if i < NB_POINTS and not self._sleep_interruptible(ACQ_INTERVAL_S / 2):
                break
        return self._finaliser(callback_fin, contexte)

    # ── Internes ────────────────────────────────────────────────────────────

    def _reset_buffers(self) -> None:
        self.n       = []
        self.t_vals  = []
        self.hr_vals = []
        self._arret  = False
        self.arrete  = False

    def _finaliser(self, callback_fin, contexte: str):
        """Calcule les stats et déclenche callback_fin, sauf si arrêt demandé."""
        self.moyenne, self.variance = self._calculer_stats(self.n)
        self.t_moy  = (sum(self.t_vals)  / len(self.t_vals))  if self.t_vals  else 0.0
        self.hr_moy = (sum(self.hr_vals) / len(self.hr_vals)) if self.hr_vals else 0.0

        if self._arret:
            self.arrete = True
            logger.warning("%s INTERROMPUE après %d point(s) — données non finalisées.",
                           contexte, len(self.n))
            return self.n, self.moyenne, self.variance, self.t_moy, self.hr_moy

        logger.info(
            "%s terminée — M=%.6f V=%.6f T_moy=%.2f HR_moy=%.2f",
            contexte, self.moyenne, self.variance, self.t_moy, self.hr_moy,
        )
        if callback_fin:
            callback_fin(self.moyenne, self.variance, self.t_moy, self.hr_moy)

        return self.n, self.moyenne, self.variance, self.t_moy, self.hr_moy

    def _sleep_interruptible(self, duree_s: float, pas_s: float = 0.05) -> bool:
        """
        Attend duree_s en vérifiant le flag d'arrêt toutes les pas_s secondes.
        Retourne True si l'attente s'est terminée normalement, False si arrêt demandé.
        """
        restant = duree_s
        while restant > 0:
            if self._arret:
                return False
            t = pas_s if restant > pas_s else restant
            time.sleep(t)
            restant -= t
        return not self._arret

    def _lire_avec_retry(self, cible: str) -> Optional[float]:
        """Lit un point depuis COM (cible = 'com1' ou 'com2'). Réessai x1 si échec."""
        valeur = self.gp.lire_com(cible)
        if valeur is None and not self._arret:
            logger.warning("Lecture %s échouée — réessai", cible)
            time.sleep(0.1)
            valeur = self.gp.lire_com(cible)
            if valeur is None:
                logger.error("Lecture %s échouée après réessai — point marqué None", cible)
        return valeur

    @staticmethod
    def _calculer_stats(valeurs: List[Optional[float]]) -> Tuple[float, float]:
        """
        Calcule la moyenne M et la variance de population V.

        Note métrologique : le CDC §3.4 définit M = ΣN[i]/30. En pratique, si une
        lecture échoue (point marqué None, cf. Ph2-07), diviser par 30 biaiserait M
        vers le bas. On divise donc par le nombre de points VALIDES — c'est le calcul
        statistiquement correct. En fonctionnement nominal (30 lectures réussies),
        les deux formules sont identiques.
        """
        return stats.moyenne_variance(valeurs)
