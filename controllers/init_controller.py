# -*- coding: utf-8 -*-
"""controllers/init_controller.py — orchestration du flux d'initialisation COM1/COM2 (sans widgets)."""
from models.acquisition import Acquisition
from models.audit import (
    EV_INIT_DEBUT, EV_INIT_FIN, EV_INIT_INTERROMPUE, EV_INIT_VALIDEE, EV_EXPORT_EXCEL,
)
from core.config import NB_POINTS, label_multimetre


class InitController:
    """Pilote l'init (état, thread, journal) ; délègue tout l'affichage à la Vue."""

    def __init__(self, app) -> None:
        self.app = app

    def lancer(self, cible: str) -> None:
        app = self.app
        if app._acq_en_cours:
            app.afficher_avertissement("Operation in progress", "An acquisition is already running.")
            return
        app.journal.enregistrer(EV_INIT_DEBUT, f"cible={label_multimetre(cible)}")
        if not app._verifier_ports_requis(cible, "thermo1"):
            return
        app._acq_en_cours = True
        app._vue_init_demarrage(cible)
        # Init COM1/COM2 : TOUJOURS NB_POINTS (30) — indépendant de l'overlock X-série.
        app._acq_courante = acq = Acquisition(app.gp, NB_POINTS)

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
            app.journal.enregistrer(EV_INIT_INTERROMPUE, f"cible={label_multimetre(cible)}")
            app._vue_init_interrompu(cible)
            return
        app.journal.enregistrer(
            EV_INIT_FIN,
            f"cible={label_multimetre(cible)}  M={m:.6f}  V={v:.6f}  T={t_moy:.2f}°C",
        )
        app._vue_init_resultats(cible, m, v, t_moy, hr_moy)
        if cible == "com1" and app._init_sequentielle:
            app._log(f"Sequential mode: launching {label_multimetre('com2')} automatically…", "info")
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
                f"Both {label_multimetre('com1')} and {label_multimetre('com2')} initialization acquisitions must be completed.",
            )
            return
        if not app.export_xls:
            app.gestion_init.init_validee = False
            app._log("No session configured — validate the connection first.", "err")
            app.afficher_erreur("Session required", "Configure the session on the Connection page first.")
            return
        # Overlock : on applique le nombre de points par X-série AFFICHÉ (spinbox) avant de
        # dimensionner la feuille — sinon la feuille serait taillée sur la valeur par défaut
        # du modèle. Une saisie invalide annule l'approbation (rien n'est écrit).
        pts = app._lire_nb_points()
        if pts is None:
            app.gestion_init.init_validee = False
            return
        app.gestion_init.definir_nb_points(pts)
        app.var_nb_points.set(app.gestion_init.nb_points)   # WYSIWYG : valeur bornée
        # Le fichier Excel est CRÉÉ ICI, à l'approbation : l'init est persistée immédiatement
        # (jamais gardée seulement en mémoire). La feuille est dimensionnée sur le nombre de
        # points par X-série choisi à ce stade (max(30, points)) ; pour utiliser plus de
        # points il faut les régler AVANT d'approuver. On refuse d'écraser des séries de
        # mesure déjà écrites (re-approbation après démarrage d'un mesurage).
        exp = app.export_xls
        if exp.est_ouvert() and exp.serie_courante > 2:
            # Des séries de MESURE sont déjà écrites : on REFUSE de reconstruire la feuille
            # (ouvrir l'écraserait). L'init reste VALIDE (init_validee CONSERVÉ) — la session
            # est correctement initialisée, on interdit seulement la ré-init en place. Ne PAS
            # révoquer init_validee ici, sinon la mesure finale/les X-séries seraient bloquées.
            app._log("Measurement already recorded — cannot re-initialize in place.", "err")
            app.afficher_erreur(
                "Measurement in progress",
                "Measurement series are already recorded. Create a new session to re-initialize.")
            return
        if not exp.ouvrir(nb_points=max(NB_POINTS, app.gestion_init.nb_points)):
            app.gestion_init.init_validee = False
            app._log("Unable to create the Excel file.", "err")
            app.afficher_erreur("Export", "Unable to create the Excel file.")
            return
        try:
            app.gestion_init.exporter_inits(exp)
        except (RuntimeError, ValueError) as exc:
            app.gestion_init.init_validee = False
            app._log(f"Initialization export failed: {exc}", "err")
            app.afficher_erreur("Export error", str(exc))
            return
        app.journal.enregistrer(EV_EXPORT_EXCEL, f"Fichier créé : {exp.chemin_fichier}")
        nb = exp.serie_courante
        app._log(f"{label_multimetre('com1')} / {label_multimetre('com2')} initialization columns written ({nb-1}, {nb}).", "ok")
        app._vue_init_approuve()
        app.journal.enregistrer(
            EV_INIT_VALIDEE,
            f"dist={app.gestion_init.distance_mm:.1f} mm  "
            f"colonnes_excel={exp.serie_courante - 1},{exp.serie_courante}",
        )
        app._log("Initialization approved by operator.", "ok")
        app._statut("Initialization approved — ready for measurement.")
