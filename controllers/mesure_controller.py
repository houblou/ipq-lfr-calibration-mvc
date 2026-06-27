# -*- coding: utf-8 -*-
"""controllers/mesure_controller.py — orchestration du mesurage (X séries) (sans widgets)."""
from models.acquisition import Acquisition
from models.calibration import BoucleCalibration
from models.audit import (
    EV_CAL_DEBUT, EV_CAL_SERIE, EV_CAL_FIN, EV_CAL_INTERROMPUE, EV_ERREUR,
)


class MesureController:
    """Pilote la boucle de mesurage (état, thread, journal) ; délègue l'affichage à la Vue."""

    def __init__(self, app) -> None:
        self.app = app
        self._serie_x = 0

    def lancer(self) -> None:
        app = self.app
        if app._acq_en_cours:
            app.afficher_avertissement("Operation in progress", "An acquisition is already running")
            return
        if not app.export_xls:
            app.afficher_avertissement("Export", "Configure the Excel session on the Connection page first")
            return
        if not app.gestion_init.init_validee:
            app.afficher_avertissement(
                "Initialization required",
                "COM1 and COM2 initialization must be approved\n"
                "on the Initialization page before measurement can start.",
            )
            return

        cible = app.var_com_mesure.get() or "com1"
        if not app._verifier_ports_requis(cible, "thermo1"):
            return

        x = app._lire_nb_series()
        if x is None:
            return
        attente_s = app._lire_attente_s()

        app.gestion_init.definir_nb_series(x)
        app.gestion_init.definir_distance(app._get_distance())
        app._vue_mesure_demarrage(x, cible)
        self._serie_x = 0

        def _on_pt_cal(i, val, t, hr):
            if i == 1:
                self._serie_x += 1
            xi = self._serie_x
            app.after(0, lambda xi=xi, ii=i, vi=val, ti=t, hri=hr:
                      app._monitor.on_serie_point(xi, ii, vi, ti, hri))

        def _on_attente(prochaine, restant):
            app.after(0, lambda p=prochaine, r=restant: app._vue_mesure_attente(p, r, x))

        acq = Acquisition(app.gp)
        boucle = BoucleCalibration(
            nb_series=x,
            acquisition=acq,
            fn_export=app.export_xls.ajouter_serie,
            fn_distance=lambda: app.gestion_init.distance_mm,
            callback_serie=self._cb_serie,
            callback_fin=self._cb_fin,
            callback_point=_on_pt_cal,
            cible=cible,
            attente_s=attente_s,
            callback_attente=_on_attente,
        )
        app._acq_courante = acq
        app._boucle_courante = boucle
        app._acq_en_cours = True
        boucle.lancer()
        app.journal.enregistrer(
            EV_CAL_DEBUT,
            f"nb_series={x}  cible={cible.upper()}  "
            f"dist={app.gestion_init.distance_mm:.1f} mm  attente={attente_s}s",
        )
        app._log(f"Measurement started — {x} series on {cible.upper()}.", "info")

    def arreter(self) -> None:
        app = self.app
        if app._boucle_courante is not None:
            app._boucle_courante.demander_arret()
            app._vue_mesure_arret_demande()

    def _cb_serie(self, x, m, v, t_moy, hr_moy) -> None:
        app = self.app
        nb = app.gestion_init.nb_series
        dist = app.gestion_init.distance_mm
        app.journal.enregistrer(
            EV_CAL_SERIE,
            f"serie={x}/{nb}  M={m:.6f}  V={v:.6f}  dist={dist:.1f} mm",
        )
        app.after(0, lambda: app._vue_mesure_serie(x, nb, m, v, t_moy, hr_moy, dist))

    def _cb_fin(self, resultats) -> None:
        self.app.after(0, lambda: self._fin(len(resultats)))

    def _fin(self, nb_completes: int) -> None:
        app = self.app
        boucle = app._boucle_courante
        interrompu = boucle is not None and boucle.interrompu()
        erreur = boucle.erreur if boucle is not None else None
        app._acq_en_cours = False
        app._acq_courante = None
        app._boucle_courante = None
        app._vue_mesure_boutons_repos()
        if erreur:
            app.journal.enregistrer(EV_ERREUR, f"Calibration échouée : {erreur}  séries_ok={nb_completes}")
            app._vue_mesure_erreur(erreur, nb_completes)
        elif interrompu:
            app.journal.enregistrer(EV_CAL_INTERROMPUE, f"séries_complètes={nb_completes}")
            app._vue_mesure_interrompu(nb_completes)
        else:
            app.journal.enregistrer(EV_CAL_FIN, f"séries_complètes={nb_completes}")
            app._vue_mesure_termine(nb_completes)
