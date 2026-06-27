# -*- coding: utf-8 -*-
"""controllers/admin_controller.py — administration : authentification, simulation, clé, audit (sans widgets)."""
from models.security import admin_key_configured, verify_admin_key, configure_admin_key
from models.audit import (
    verifier_integrite,
    EV_ADMIN_AUTH, EV_ADMIN_LOCK, EV_ADMIN_CLE, EV_ERREUR,
    EV_SIMULATION_ACTIVE, EV_SIMULATION_DESACTIVE,
)


class AdminController:
    """Pilote la sécurité / la simulation / l'audit ; délègue dialogues et widgets à la Vue."""

    def __init__(self, app) -> None:
        self.app = app

    def authentifier(self) -> bool:
        app = self.app
        if app._acq_en_cours:
            app.afficher_erreur("Operation blocked",
                                "Cannot open administration during a measurement.")
            return False
        if not admin_key_configured():
            key = app.demander_secret(
                "Administration access",
                "No admin key configured.\nDevelopment password:",
            )
            if key != "admin":
                return False
            app._admin_mode_dev = True
        else:
            app._admin_mode_dev = False
            key = app.demander_secret("Administration access", "Administrator key:")
            if key is None:
                return False
            if not verify_admin_key(key):
                app.journal.enregistrer(EV_ERREUR, "Tentative d'accès admin refusée")
                app.afficher_erreur("Access denied", "Invalid administrator key.")
                return False
        app._admin_actif = True
        app.journal.enregistrer(
            EV_ADMIN_AUTH,
            f"mode={'dev' if app._admin_mode_dev else 'prod'}  op={app.journal.operateur}",
        )
        app._vue_admin_deverrouille()
        return True

    def verrouiller(self) -> None:
        app = self.app
        app._admin_actif = False
        app._admin_mode_dev = False
        app.journal.enregistrer(EV_ADMIN_LOCK, f"op={app.journal.operateur}")
        app._vue_admin_verrouille()
        app._naviguer("connexion")

    def basculer_simulation(self) -> None:
        app = self.app
        if app._acq_en_cours:
            app.afficher_erreur("Operation blocked",
                                "Cannot change simulation mode during a measurement.")
            return
        if app.export_xls is not None:
            app.afficher_erreur(
                "Operation blocked",
                "Simulation mode must be set before creating the Excel session.\n"
                "Restart the application to change mode.",
            )
            return
        enabled = not app.gp.mode_simulation
        app.gp.fermer_tout()
        app.gp.set_simulation_mode(enabled)
        app.gestion_init.reinitialiser()
        app.journal.enregistrer(
            EV_SIMULATION_ACTIVE if enabled else EV_SIMULATION_DESACTIVE,
            ("activé" if enabled else "désactivé") + " depuis panneau admin",
        )
        app._vue_simulation(enabled)

    def configurer_cle(self) -> None:
        app = self.app
        k1 = app.demander_secret("New admin key", "New key (min 12 characters):")
        if not k1:
            return
        k2 = app.demander_secret("Confirmation", "Confirm the key:")
        if k1 != k2:
            app.afficher_erreur("Error", "The keys do not match.")
            return
        try:
            configure_admin_key(k1)
            app.journal.enregistrer(EV_ADMIN_CLE, "Nouvelle clé admin configurée")
            app._vue_cle_configuree()
        except ValueError as exc:
            app.afficher_erreur("Invalid key", str(exc))

    def verifier_journal(self) -> None:
        app = self.app
        ok, nb, premiere_erreur = verifier_integrite(app.journal.chemin)
        app._vue_audit_resultat(ok, nb, premiere_erreur)
