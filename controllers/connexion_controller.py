# -*- coding: utf-8 -*-
"""controllers/connexion_controller.py — connexion instruments + création de session Excel (sans widgets)."""
import os
import threading

from models.export_xls import ExportXLS
from models.audit import EV_CONNEXION, EV_EXPORT_EXCEL, EV_ERREUR
from core.paths import get_desktop_path


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
            app.afficher_avertissement("Missing instrument", f"Select an instrument for {cible.upper()}.")
            return
        if app.gp.connecter(port, cible):   # bus auto : COMx -> série, GPIB… -> VISA
            app._vue_port_ok(cible, port)
            if not app.gp.backboard_actif:
                app.gp.demarrer_backboard(
                    callback_erreur=lambda m: app.after(0, lambda: app._log(f"⚠ {m}", "err")))
        else:
            errs = app.gp.get_erreurs()
            app._vue_port_echec(cible, errs[-1] if errs else "Connection failed.")

    def auto_detecter(self) -> None:
        app = self.app
        try:
            import models.detection as detect_com
        except Exception as exc:
            app._log(f"Auto-detect unavailable: {exc}", "err")
            return
        if not getattr(detect_com, "PYSERIAL_OK", False):
            app._vue_detect_indispo()
            return
        app._vue_detect_scan()

        def _run():
            data = detect_com.detecter()
            app.after(0, lambda: self._appliquer(data))

        threading.Thread(target=_run, daemon=True, name="thread-detect").start()

    def _appliquer(self, data: dict) -> None:
        self.rafraichir_ports()
        self.app._vue_detection(data)

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
                          if simulation else ".")
        app.export_xls = ExportXLS(export_index, dossier=dossier_export,
                                   simulation=simulation, operateur=operateur)
        if app.export_xls.ouvrir():
            app.journal.enregistrer(
                EV_CONNEXION, f"indice={indice}  excel={app.export_xls.chemin_fichier}")
            app.journal.enregistrer(
                EV_EXPORT_EXCEL, f"Fichier créé : {app.export_xls.chemin_fichier}")
            app._vue_connexion_ok(indice, simulation, dossier_export, app.export_xls.chemin_fichier)
        else:
            app.journal.enregistrer(EV_ERREUR, "Échec création fichier Excel")
            app._log("Unable to create the Excel file.", "err")
