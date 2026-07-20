# -*- coding: utf-8 -*-
"""controllers/mesure_controller.py — orchestration du mesurage (X séries + mesure finale) (sans widgets)."""
import threading
from datetime import datetime

from models.acquisition import Acquisition
from models.calibration import BoucleCalibration
from models.audit import (
    EV_CAL_DEBUT, EV_CAL_SERIE, EV_CAL_FIN, EV_CAL_INTERROMPUE, EV_ERREUR,
)
from core.config import NB_POINTS, label_multimetre


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
                f"{label_multimetre('com1')} and {label_multimetre('com2')} initialization must be approved\n"
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

        acq = Acquisition(app.gp, app.gestion_init.nb_points)
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
            f"nb_series={x}  cible={label_multimetre(cible)}  "
            f"dist={app.gestion_init.distance_mm:.1f} mm  attente={attente_s}s",
        )
        app._log(f"Measurement started — {x} series on {label_multimetre(cible)}.", "info")

    def arreter(self) -> None:
        app = self.app
        if app._boucle_courante is not None:
            app._boucle_courante.demander_arret()
            app._vue_mesure_arret_demande()
        elif app._acq_en_cours:
            # Mesure finale : pas de BoucleCalibration. On enregistre l'intention
            # d'arrêt MÊME si l'acquisition n'est pas encore créée (fenêtre de course
            # entre `_acq_en_cours = True` et l'assignation de `_acq_courante` dans
            # _run) ; _run la verra et coupera net avant COM2.
            app._arret_finale = True
            if app._acq_courante is not None:
                app._acq_courante.demander_arret()
            app._vue_mesure_arret_demande()

    def _cb_serie(self, x, m, v, t_moy, hr_moy, perdus=0) -> None:
        app = self.app
        nb = app.gestion_init.nb_series
        dist = app.gestion_init.distance_mm
        app.journal.enregistrer(
            EV_CAL_SERIE,
            f"serie={x}/{nb}  M={m:.6f}  V={v:.6f}  dist={dist:.1f} mm  perdus={perdus}",
        )
        app.after(0, lambda: app._vue_mesure_serie(x, nb, m, v, t_moy, hr_moy, dist, perdus))

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

    # ── Mesure finale (com1 + com2, comme l'init, export direct) ──────────────
    def mesure_finale(self) -> None:
        app = self.app
        if app._acq_en_cours:
            app.afficher_avertissement("Operation in progress", "An acquisition is already running")
            return
        if not app.export_xls:
            app.afficher_avertissement("Export", "Configure the Excel session on the Connection page first")
            return
        # Mesure finale = les DEUX multimètres (comme l'init) -> com1 ET com2 requis.
        if not app._verifier_ports_requis("com1", "com2", "thermo1"):
            return

        app._acq_en_cours = True
        app._arret_finale = False   # intention d'arrêt pour la fenêtre course→thread (cf. arreter)
        app._vue_mesure_finale_demarrage()
        dist = app.gestion_init.distance_mm
        # Mesure finale COM1/COM2 : TOUJOURS NB_POINTS (30) — comme l'init, hors overlock.
        nbp  = NB_POINTS

        def _run():
            interrompu = False
            erreur = None
            series_ok = []          # séries finales réellement exportées (traçabilité)
            try:
                for cible in ("com1", "com2"):
                    if app._arret_finale:      # arrêt demandé (y compris pendant la
                        interrompu = True      # fenêtre de course au démarrage) → on ne
                        break                  # lance PAS l'acquisition. Test en tête de
                    #                            boucle car _reset_buffers() remettrait
                    #                            _arret à False s'il était posé sur l'acq.
                    acq = Acquisition(app.gp, nbp)
                    app._acq_courante = acq
                    base = 0 if cible == "com1" else nbp   # progression cumulée com1→com2

                    def on_pt(i, val, t, hr, c=cible, b=base):
                        def _maj(i=i, val=val, t=t, hr=hr, c=c, b=b):
                            app._monitor.on_final_point(c, i, val, t, hr)
                            app._vue_mesure_finale_point(b + i)
                        app.after(0, _maj)

                    n, m, v, t_moy, hr_moy = acq.lancer(cible=cible, callback_point=on_pt)
                    if acq.arrete:
                        interrompu = True
                        break
                    date  = datetime.now().strftime("%d/%m/%Y")
                    heure = datetime.now().strftime("%H:%M:%S")
                    app.export_xls.ajouter_serie(n, m, v, t_moy, hr_moy, dist, date, heure,
                                                 label=f"Final COM{cible[-1]}")
                    app.journal.enregistrer(
                        EV_CAL_SERIE,
                        f"FINALE {label_multimetre(cible)}  M={m:.6f}  V={v:.6f}  perdus={acq.points_perdus}")
                    app.after(0, lambda c=cible, m=m, v=v, tm=t_moy, hm=hr_moy,
                              p=acq.points_perdus, d=dist:
                              app._vue_mesure_finale_serie(c, m, v, tm, hm, p, d))
                    series_ok.append(label_multimetre(cible))   # série finale réellement exportée (journal)
            except Exception as exc:
                erreur = str(exc)
                app.journal.enregistrer(EV_ERREUR, f"Mesure finale échouée : {exc}")
                app.after(0, lambda e=erreur: app._vue_mesure_finale_erreur(e))
            finally:
                app.after(0, lambda intr=interrompu, err=erreur, so=list(series_ok):
                          self._fin_finale(intr, err, so))

        threading.Thread(target=_run, daemon=True, name="thread-mesure-finale").start()

    def _fin_finale(self, interrompu: bool = False, erreur=None, series_ok=None) -> None:
        app = self.app
        app._acq_en_cours = False
        app._acq_courante = None
        # Traçabilité : consigner EXACTEMENT les séries finales exportées, pour qu'un
        # état « interrompu » ne masque pas qu'une colonne (ex. Final COM1) est déjà
        # écrite et valide dans l'Excel.
        if interrompu or erreur:
            exportees = ", ".join(series_ok) if series_ok else "aucune"
            app.journal.enregistrer(
                EV_CAL_INTERROMPUE,
                f"MESURE FINALE — séries exportées={exportees}"
                + (f" ; erreur={erreur}" if erreur else " ; interrompue avant la fin"))
        app._vue_mesure_finale_termine(interrompu, erreur)
