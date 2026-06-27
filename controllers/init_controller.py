# -*- coding: utf-8 -*-
"""controllers/init_controller.py — orchestration du flux d'initialisation COM1/COM2 (sans widgets)."""
from models.acquisition import Acquisition
from models.audit import EV_INIT_DEBUT, EV_INIT_FIN, EV_INIT_INTERROMPUE, EV_INIT_VALIDEE


class InitController:
    """Pilote l'init (état, thread, journal) ; délègue tout l'affichage à la Vue."""

    def __init__(self, app) -> None:
        self.app = app

    def lancer(self, cible: str) -> None:
        app = self.app
        if app._acq_en_cours:
            app.afficher_avertissement("Operation in progress", "An acquisition is already running.")
            return
        app.journal.enregistrer(EV_INIT_DEBUT, f"cible=COM{cible[-1]}")
        if not app._verifier_ports_requis(cible, "thermo1"):
            return
        app._acq_en_cours = True
        app._vue_init_demarrage(cible)
        app._acq_courante = acq = Acquisition(app.gp)

        def on_pt(i, valeur, t, hr):
            app.after(0, lambda i=i, v=valeur, t=t, hr=hr: app._maj_init_pt(cible, i, v, t, hr))

        def on_fin(m, v, t_moy, hr_moy, date, heure):
            app.after(0, lambda: self._fin(cible, m, v, t_moy, hr_moy))

        app.gestion_init.lancer_init(cible, acq, callback_point=on_pt, callback_fin=on_fin)

    def _fin(self, cible: str, m, v, t_moy, hr_moy) -> None:
        app = self.app
        app._acq_en_cours = False
        app._acq_courante = None
        app._vue_init_standby()
        if m is None:
            app._init_sequentielle = False
            app.journal.enregistrer(EV_INIT_INTERROMPUE, f"cible={cible.upper()}")
            app._vue_init_interrompu(cible)
            return
        app.journal.enregistrer(
            EV_INIT_FIN,
            f"cible={cible.upper()}  M={m:.6f}  V={v:.6f}  T={t_moy:.2f}°C",
        )
        app._vue_init_resultats(cible, m, v, t_moy, hr_moy)
        if cible == "com1" and app._init_sequentielle:
            app._log("Sequential mode: launching COM2 automatically…", "info")
            app.after(300, lambda: self.lancer("com2"))
            return
        app._init_sequentielle = False
        if app.gestion_init.init1_ok and app.gestion_init.init2_ok:
            app._vue_init_pret()

    def valider(self) -> None:
        app = self.app
        app.gestion_init.definir_distance(app._get_distance())
        if not app.gestion_init.valider_init():
            app.afficher_avertissement(
                "Approval unavailable",
                "Both COM1 and COM2 initialization acquisitions must be completed.",
            )
            return
        if not app.export_xls:
            app.gestion_init.init_validee = False
            app._log("No Excel file is open — initialization not approved.", "err")
            app.afficher_erreur("Export required", "Create the Excel file in the Connection page first.")
            return
        try:
            app.gestion_init.exporter_inits(app.export_xls)
        except (RuntimeError, ValueError) as exc:
            app.gestion_init.init_validee = False
            app._log(f"Initialization export failed: {exc}", "err")
            app.afficher_erreur("Export error", str(exc))
            return
        nb = app.export_xls.serie_courante
        app._log(f"COM1 / COM2 initialization columns exported ({nb-1}, {nb}).", "ok")
        app._vue_init_approuve()
        app.journal.enregistrer(
            EV_INIT_VALIDEE,
            f"dist={app.gestion_init.distance_mm:.1f} mm  "
            f"colonnes_excel={app.export_xls.serie_courante - 1},{app.export_xls.serie_courante}",
        )
        app._log("Initialization approved by operator.", "ok")
        app._statut("Initialization approved — ready for measurement.")
