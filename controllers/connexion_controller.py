# -*- coding: utf-8 -*-
"""controllers/connexion_controller.py — connexion instruments + création de session Excel (sans widgets)."""
import os

from models.export_xls import ExportXLS
from models.audit import EV_CONNEXION, EV_EXPORT_EXCEL, EV_ERREUR
from core.paths import get_desktop_path, get_export_dir
from core.config import label_multimetre


class ConnexionController:
    """Pilote la découverte/connexion des ports et la création de session ; délègue l'affichage à la Vue."""

    def __init__(self, app) -> None:
        self.app = app

    def rafraichir_ports(self) -> None:
        app = self.app
        app._vue_ports_disponibles(app.gp.lister_instruments())   # série (COMx) + VISA (GPIB…)

    def connecter(self, cible: str) -> None:
        app = self.app
        port = app._port_vars[cible].get().strip()
        if not port:
            app.afficher_avertissement("Missing instrument", f"Select an instrument for {label_multimetre(cible)}.")
            return
        if app.gp.connecter(port, cible):   # bus auto : COMx -> série, GPIB… -> VISA
            app._vue_port_ok(cible, port)
            if cible == "thermo1":
                # Auto-adaptation : détecte Hart 1620 ou RUSKA 2456-LEM et fixe le mode.
                mode = app.gp.detecter_source_thermo()
                libelles = {"hart": "Hart 1620", "ruska": "RUSKA 2456-LEM"}
                if mode in libelles:
                    app.var_thermo_source.set(libelles[mode])
                    app._log(f"Ambient source auto-detected: {libelles[mode]}", "ok")
                else:
                    app._log("Ambient source not auto-detected — select it manually.", "err")
            if not app.gp.backboard_actif:
                app.gp.demarrer_backboard(
                    callback_erreur=lambda m: app.after(0, lambda: app._log(f"⚠ {m}", "err")))
        else:
            errs = app.gp.get_erreurs()
            app._vue_port_echec(cible, errs[-1] if errs else "Connection failed.")

    def valider(self) -> None:
        app = self.app
        if app.export_xls is not None:
            if not app.demander_confirmation(
                "Session already open",
                "An Excel session is already open.\n"
                "Creating a new one will close the current file.\n\nContinue?",
            ):
                return
            try:
                app.export_xls.fermer()
            except Exception as exc:
                app._log(f"Could not close the previous Excel file: {exc}", "err")
            app.export_xls = None
            app.gestion_init.reinitialiser()
            app._vue_reset_session()   # purge Monitor + Results de la session précédente

        operateur = app.var_operateur.get().strip()
        if len(operateur) < 2:
            app.afficher_avertissement(
                "Missing operator",
                "Enter the operator's full name or identifier (at least 2 characters).",
            )
            return
        indice = app.var_indice.get().strip()
        if not indice:
            app.afficher_avertissement("Missing identifier", "Enter a record identifier.")
            return

        app.journal.set_operateur(operateur)
        app._vue_operateur(operateur)

        simulation = app.gp.mode_simulation
        export_index = f"SIMULATION_{indice}" if simulation else indice
        dossier_export = (os.path.join(get_desktop_path(), "IPQ_LFR_Simulation")
                          if simulation else get_export_dir())
        app.export_xls = ExportXLS(export_index, dossier=dossier_export,
                                   simulation=simulation, operateur=operateur,
                                   nb_points=app.gestion_init.nb_points)
        if app.export_xls.ouvrir():
            app.journal.enregistrer(
                EV_CONNEXION, f"indice={indice}  excel={app.export_xls.chemin_fichier}")
            app.journal.enregistrer(
                EV_EXPORT_EXCEL, f"Fichier créé : {app.export_xls.chemin_fichier}")
            app._vue_connexion_ok(indice, simulation, dossier_export, app.export_xls.chemin_fichier)
        else:
            app.journal.enregistrer(EV_ERREUR, "Échec création fichier Excel")
            app._log("Unable to create the Excel file.", "err")
