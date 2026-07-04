
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

try:
    import winsound
    WINSOUND_OK = True
except ImportError:
    WINSOUND_OK = False

from core.logger import creer_logger
from core.config import (
    ATTENTE_INTER_SERIE_S,
    BIP_FREQ_START, BIP_FREQ_END, BIP_DUREE_MS,
)

logger = creer_logger("phase4")


# ── Signaux sonores ───────────────────────────────────────────────────────────

class GestionAudio:
    """Bips sonores : séquence d'attente jouée entre deux séries X."""

    @staticmethod
    def bip(frequence: float, duree_ms: int) -> None:
        if WINSOUND_OK:
            try:
                winsound.Beep(int(frequence), int(duree_ms))
            except (RuntimeError, ValueError):
                pass
        else:
            logger.debug("BIP %d Hz %d ms", int(frequence), duree_ms)

    @staticmethod
    def sequence_attente(duree_s: float, nb_bips: int,
                         freq_debut: float, freq_fin: float, duree_bip_ms: int,
                         doit_arreter: Optional[Callable[[], bool]] = None,
                         sur_tick: Optional[Callable[[int], None]] = None) -> bool:
        """
        Joue nb_bips répartis sur duree_s, fréquence croissante freq_debut→freq_fin.
        - doit_arreter() : interrompt la séquence si renvoie True (arrêt thread-safe)
        - sur_tick(restant) : appelé à chaque bip avec le nombre de bips restants
        Retourne True si terminée normalement, False si interrompue.
        """
        if duree_s <= 0 or nb_bips <= 0:
            return True
        intervalle = duree_s / nb_bips
        for k in range(nb_bips):
            if doit_arreter and doit_arreter():
                return False
            ratio = k / max(nb_bips - 1, 1)
            freq  = freq_debut + ratio * (freq_fin - freq_debut)
            GestionAudio.bip(freq, duree_bip_ms)   # bloquant pendant duree_bip_ms
            if sur_tick:
                sur_tick(nb_bips - k - 1)           # bips restants ≈ secondes restantes
            reste = intervalle - duree_bip_ms / 1000.0
            fin = time.time() + max(reste, 0.0)
            while time.time() < fin:
                if doit_arreter and doit_arreter():
                    return False
                time.sleep(min(0.05, fin - time.time()))
        return True


# ── Boucle calibration ────────────────────────────────────────────────────────

class BoucleCalibration:
    """
    Exécute X séries d'acquisition (Phase 2) + export (Phase 3) à chaque itération.

    acquisition    : instance Acquisition réutilisée à chaque série (permet l'arrêt)
    fn_export(n, m, v, t_moy, hr_moy, distance, date, heure, label)
    fn_distance() -> float   (appelé avant chaque série pour la distance courante)
    """

    def __init__(
        self,
        nb_series:        int,
        acquisition,
        fn_export:        Callable,
        fn_distance:      Optional[Callable[[], float]] = None,
        callback_serie:   Optional[Callable[[int, float, float, float, float], None]] = None,
        callback_fin:     Optional[Callable[[List], None]] = None,
        callback_point:   Optional[Callable] = None,
        attente_s:        float = ATTENTE_INTER_SERIE_S,
        callback_attente: Optional[Callable[[int, int], None]] = None,
        cible:            str = "com1",
    ) -> None:
        self.nb_series      = nb_series
        self.acquisition    = acquisition      # instance Acquisition (Phase 2)
        self.cible          = cible            # 'com1' ou 'com2' — seul COM mesuré
        self.fn_export      = fn_export
        self.fn_distance    = fn_distance
        self.callback_serie  = callback_serie  # (x, M, V, T_moy, HR_moy)
        self.callback_fin    = callback_fin    # (resultats)
        self.callback_point  = callback_point  # (i, v1, v2, t=t, hr=hr) — live par point
        self.attente_s       = max(float(attente_s), 0.0)  # attente entre 2 séries
        self.callback_attente = callback_attente  # (prochaine_serie, secondes_restantes)
        self.resultats: List[dict] = []
        self._arret = False
        self.erreur: Optional[str] = None

    def demander_arret(self) -> None:
        """Demande l'arrêt de la boucle ET de l'acquisition en cours."""
        self._arret = True
        if self.acquisition is not None:
            self.acquisition.demander_arret()

    def interrompu(self) -> bool:
        """True si un arrêt a été demandé (accesseur public de l'état d'arrêt)."""
        return self._arret

    def lancer(self) -> None:
        """Démarre la boucle sur X séries dans un thread dédié."""
        t = threading.Thread(target=self._boucle, daemon=True, name="thread-calibration")
        t.start()

    def _attendre_avec_bips(self, prochaine_serie: int) -> None:
        """Attente inter-série : 1 bip/seconde, fréquence croissante (doux → aigu)."""
        duree   = self.attente_s
        nb_bips = max(int(round(duree)), 1)   # ~1 bip par seconde

        def _tick(restant: int) -> None:
            if self.callback_attente:
                self.callback_attente(prochaine_serie, restant)

        logger.info("Attente %.0f s avant la série %d (%d bips).",
                    duree, prochaine_serie, nb_bips)
        GestionAudio.sequence_attente(
            duree, nb_bips,
            BIP_FREQ_START, BIP_FREQ_END, BIP_DUREE_MS,
            doit_arreter=lambda: self._arret,
            sur_tick=_tick,
        )

    def _boucle(self) -> None:
        self.resultats = []
        self.erreur = None

        try:
            for x in range(1, self.nb_series + 1):
                if self._arret:
                    logger.warning("Boucle calibration interrompue avant la série %d.", x)
                    break

                logger.info("Début série %d / %d", x, self.nb_series)

                distance = self.fn_distance() if self.fn_distance else 0.0
                date     = datetime.now().strftime("%d/%m/%Y")
                heure    = datetime.now().strftime("%H:%M:%S")

                n, m, v, t_moy, hr_moy = self.acquisition.lancer(
                    cible=self.cible,
                    callback_point=self.callback_point,
                )

                # Série interrompue en plein milieu : on n'exporte pas de données partielles
                if self.acquisition.arrete or self._arret:
                    logger.warning("Série %d interrompue — non exportée.", x)
                    break

                self.fn_export(n, m, v, t_moy, hr_moy, distance, date, heure, label=f"Series {x}")

                perdus = self.acquisition.points_perdus
                self.resultats.append({
                    "serie": x, "N": n, "M": m, "V": v,
                    "T_moy": t_moy, "HR_moy": hr_moy, "distance": distance,
                    "perdus": perdus,
                })

                if self.callback_serie:
                    self.callback_serie(x, m, v, t_moy, hr_moy, perdus)

                logger.info(
                    "Série %d — M=%.6f V=%.6f T_moy=%.2f HR_moy=%.2f dist=%.1f",
                    x, m, v, t_moy, hr_moy, distance,
                )

                # Attente sonore entre 2 séries (pas après la dernière)
                if x < self.nb_series and not self._arret:
                    self._attendre_avec_bips(x + 1)
        except Exception as exc:
            self.erreur = str(exc)
            logger.exception("Échec de la boucle calibration : %s", exc)

        if self.erreur:
            statut = "en erreur"
        elif self._arret or self.acquisition.arrete:
            statut = "interrompue"
        else:
            statut = "terminée"
        logger.info("Boucle calibration %s — %d série(s) complète(s).", statut, len(self.resultats))

        if self.callback_fin:
            self.callback_fin(self.resultats)
