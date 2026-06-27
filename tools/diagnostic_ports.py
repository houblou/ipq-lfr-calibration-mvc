# -*- coding: utf-8 -*-
"""phase1_comm.py — Vue Phase 1 (FenetrePhase1). GestionPorts vit dans models/ports.py (ré-exporté ici)."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from core.logger import creer_logger
from core.paths import horodatage_lisible
from models.ports import GestionPorts

logger = creer_logger("phase1")


COULEUR_BG      = "#F0F4F8"
COULEUR_HEADER  = "#1F4E79"
COULEUR_BTN     = "#2E75B6"
COULEUR_BTN_TXT = "white"
COULEUR_OK      = "#27AE60"
COULEUR_ERR     = "#E74C3C"
COULEUR_WARN    = "#F39C12"
POLICE          = ("Arial", 10)
POLICE_TITRE    = ("Arial", 13, "bold")
POLICE_HEADER   = ("Arial", 11, "bold")


class FenetrePhase1(tk.Toplevel):
    """
    Interface graphique Phase 1 — Sélection et connexion des ports.
    S'ouvre comme fenêtre secondaire (Toplevel) ou principale.
    """

    def __init__(
        self,
        parent: tk.Widget,
        callback_valide: Optional[Callable] = None,
        gestion_ports: Optional["GestionPorts"] = None,
    ) -> None:
        """
        parent           : widget parent Tkinter
        callback_valide  : fonction appelée quand l'utilisateur valide (noms_appareils en arg)
        gestion_ports    : instance GestionPorts partagée (si None, une nouvelle est créée)
        """
        super().__init__(parent)
        self.title("Phase 1 — Dialogue & Communication")
        self.configure(bg=COULEUR_BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._quitter)

        self.gp = gestion_ports if gestion_ports is not None else GestionPorts()
        self.callback_valide = callback_valide

        # Variables Tkinter
        self.var_com1   = tk.StringVar()
        self.var_com2   = tk.StringVar()
        self.var_thermo = tk.StringVar()
        self.var_gpib   = tk.StringVar(value="GPIB0::1::INSTR")
        self.var_indice = tk.StringVar()

        self._construire_ui()
        self._rafraichir_ports()
        self.grab_set()

    def _construire_ui(self) -> None:
        # ── En-tête ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=COULEUR_HEADER, pady=10)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        tk.Label(
            header,
            text="⚙  Phase 1 — Dialogue & Communication",
            font=("Arial", 13, "bold"),
            bg=COULEUR_HEADER,
            fg="white",
        ).pack(padx=20)

        corps = tk.Frame(self, bg=COULEUR_BG, padx=20, pady=15)
        corps.grid(row=1, column=0, sticky="nsew")

        # -- Indice de notation -----------------------------------------------
        self._section(corps, "Identification de la série", row=0)
        tk.Label(corps, text="Indice de notation :", font=POLICE, bg=COULEUR_BG).grid(
            row=1, column=0, sticky="w", pady=3)
        tk.Entry(corps, textvariable=self.var_indice, font=POLICE, width=30).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=5, pady=3)

        # -- Ports série -------------------------------------------------------
        self._section(corps, "Ports série (RS-232)", row=2)

        # COM1
        tk.Label(corps, text="COM 1 :", font=POLICE, bg=COULEUR_BG).grid(
            row=3, column=0, sticky="w", pady=3)
        self.cb_com1 = ttk.Combobox(corps, textvariable=self.var_com1, width=12, state="readonly")
        self.cb_com1.grid(row=3, column=1, sticky="w", padx=5)
        self.btn_com1 = tk.Button(
            corps, text="Connecter", font=POLICE,
            bg=COULEUR_BTN, fg=COULEUR_BTN_TXT, relief="flat", padx=8,
            command=lambda: self._connecter("com1"),
        )
        self.btn_com1.grid(row=3, column=2, padx=5)
        self.lbl_statut_com1 = tk.Label(corps, text="●", font=("Arial", 14), bg=COULEUR_BG, fg=COULEUR_ERR)
        self.lbl_statut_com1.grid(row=3, column=3, padx=5)

        # COM2
        tk.Label(corps, text="COM 2 :", font=POLICE, bg=COULEUR_BG).grid(
            row=4, column=0, sticky="w", pady=3)
        self.cb_com2 = ttk.Combobox(corps, textvariable=self.var_com2, width=12, state="readonly")
        self.cb_com2.grid(row=4, column=1, sticky="w", padx=5)
        self.btn_com2 = tk.Button(
            corps, text="Connecter", font=POLICE,
            bg=COULEUR_BTN, fg=COULEUR_BTN_TXT, relief="flat", padx=8,
            command=lambda: self._connecter("com2"),
        )
        self.btn_com2.grid(row=4, column=2, padx=5)
        self.lbl_statut_com2 = tk.Label(corps, text="●", font=("Arial", 14), bg=COULEUR_BG, fg=COULEUR_ERR)
        self.lbl_statut_com2.grid(row=4, column=3, padx=5)

        # Thermo1
        tk.Label(corps, text="Thermo 1 :", font=POLICE, bg=COULEUR_BG).grid(
            row=5, column=0, sticky="w", pady=3)
        self.cb_thermo = ttk.Combobox(corps, textvariable=self.var_thermo, width=12, state="readonly")
        self.cb_thermo.grid(row=5, column=1, sticky="w", padx=5)
        self.btn_thermo = tk.Button(
            corps, text="Connecter", font=POLICE,
            bg=COULEUR_BTN, fg=COULEUR_BTN_TXT, relief="flat", padx=8,
            command=lambda: self._connecter("thermo1"),
        )
        self.btn_thermo.grid(row=5, column=2, padx=5)
        self.lbl_statut_thermo = tk.Label(corps, text="●", font=("Arial", 14), bg=COULEUR_BG, fg=COULEUR_ERR)
        self.lbl_statut_thermo.grid(row=5, column=3, padx=5)

        # Bouton rafraîchir
        tk.Button(
            corps, text="🔄 Rafraîchir ports", font=POLICE,
            bg="#555", fg="white", relief="flat", padx=8,
            command=self._rafraichir_ports,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 4))

        # -- GPIB --------------------------------------------------------------
        self._section(corps, "Interface GPIB (PyVISA)", row=7)
        tk.Label(corps, text="Adresse VISA :", font=POLICE, bg=COULEUR_BG).grid(
            row=8, column=0, sticky="w", pady=3)
        tk.Entry(corps, textvariable=self.var_gpib, font=POLICE, width=22).grid(
            row=8, column=1, sticky="w", padx=5)
        tk.Button(
            corps, text="Connecter", font=POLICE,
            bg=COULEUR_BTN, fg=COULEUR_BTN_TXT, relief="flat", padx=8,
            command=self._connecter_gpib,
        ).grid(row=8, column=2, padx=5)
        self.lbl_statut_gpib = tk.Label(corps, text="●", font=("Arial", 14), bg=COULEUR_BG, fg=COULEUR_ERR)
        self.lbl_statut_gpib.grid(row=8, column=3, padx=5)

        tk.Button(
            corps, text="🔍 Lister ressources VISA", font=POLICE,
            bg="#555", fg="white", relief="flat", padx=8,
            command=self._lister_visa,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 4))

        # -- Backboard ---------------------------------------------------------
        self._section(corps, "Surveillance continue (Backboard)", row=10)
        self.lbl_backboard = tk.Label(
            corps, text="● Inactive", font=POLICE, bg=COULEUR_BG, fg=COULEUR_ERR)
        self.lbl_backboard.grid(row=11, column=0, columnspan=2, sticky="w", pady=3)

        # -- Journal d'erreurs ------------------------------------------------
        self._section(corps, "Journal", row=12)
        self.txt_log = tk.Text(
            corps, height=6, width=58, font=("Courier", 9),
            bg="#1E1E1E", fg="#D4D4D4", relief="flat",
            state="disabled",
        )
        self.txt_log.grid(row=13, column=0, columnspan=4, pady=5, sticky="ew")

        scrollbar = tk.Scrollbar(corps, command=self.txt_log.yview)
        scrollbar.grid(row=13, column=4, sticky="ns")
        self.txt_log.configure(yscrollcommand=scrollbar.set)

        # -- Boutons principaux -----------------------------------------------
        btn_frame = tk.Frame(corps, bg=COULEUR_BG)
        btn_frame.grid(row=14, column=0, columnspan=4, pady=(15, 5), sticky="ew")

        tk.Button(
            btn_frame, text="✔  Valider et continuer", font=("Arial", 10, "bold"),
            bg=COULEUR_OK, fg="white", relief="flat", padx=14, pady=6,
            command=self._valider,
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame, text="✖  Quitter", font=POLICE,
            bg=COULEUR_ERR, fg="white", relief="flat", padx=14, pady=6,
            command=self._quitter,
        ).pack(side="left", padx=5)

    def _section(self, parent: tk.Frame, texte: str, row: int) -> None:
        """Ajoute un séparateur de section."""
        frame = tk.Frame(parent, bg=COULEUR_BG)
        frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(12, 2))
        tk.Label(frame, text=texte, font=POLICE_HEADER, bg=COULEUR_BG, fg=COULEUR_HEADER).pack(side="left")
        tk.Frame(frame, height=1, bg=COULEUR_HEADER).pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _rafraichir_ports(self) -> None:
        """Analyse tous les ports série disponibles et peuple les listes déroulantes."""
        ports = self.gp.lister_ports_serie()
        liste = [""] + ports
        self.cb_com1["values"]  = liste
        self.cb_com2["values"]  = liste
        self.cb_thermo["values"] = liste
        self._log(f"Ports détectés : {ports if ports else 'aucun'}")

    def _connecter(self, cible: str) -> None:
        """Tente de connecter le port sélectionné pour la cible donnée."""
        var   = {"com1": self.var_com1, "com2": self.var_com2, "thermo1": self.var_thermo}[cible]
        label = {"com1": self.lbl_statut_com1, "com2": self.lbl_statut_com2, "thermo1": self.lbl_statut_thermo}[cible]
        port  = var.get().strip()

        if not port:
            messagebox.showwarning("Port manquant", f"Veuillez sélectionner un port pour {cible.upper()}.")
            return

        self._log(f"Connexion {cible.upper()} sur {port}…")
        ok = self.gp.connecter_serie(port, cible)

        if ok:
            label.configure(fg=COULEUR_OK)
            self._log(f"✔ {cible.upper()} connecté sur {port}")
            # Démarrer le backboard dès qu'au moins un port est connecté
            if not self.gp._backboard_actif:
                self.gp.demarrer_backboard(callback_erreur=self._erreur_backboard)
                self.lbl_backboard.configure(text="● Active", fg=COULEUR_OK)
        else:
            label.configure(fg=COULEUR_ERR)
            erreurs = self.gp.get_erreurs()
            msg = erreurs[-1] if erreurs else "Erreur inconnue."
            self._log(f"✖ {msg}", erreur=True)

    def _connecter_gpib(self) -> None:
        """Tente de connecter l'instrument GPIB."""
        adresse = self.var_gpib.get().strip()
        if not adresse:
            messagebox.showwarning("Adresse manquante", "Entrez une adresse VISA.")
            return
        self._log(f"Connexion GPIB {adresse}…")
        ok = self.gp.connecter_gpib(adresse)
        if ok:
            self.lbl_statut_gpib.configure(fg=COULEUR_OK)
            idn = self.gp.noms_appareils.get("gpib", "inconnu")
            self._log(f"✔ GPIB connecté : {idn}")
        else:
            self.lbl_statut_gpib.configure(fg=COULEUR_ERR)
            erreurs = self.gp.get_erreurs()
            self._log(f"✖ {erreurs[-1] if erreurs else 'Erreur GPIB.'}", erreur=True)

    def _lister_visa(self) -> None:
        """Affiche les ressources VISA dans le journal."""
        ressources = self.gp.lister_ressources_visa()
        if ressources:
            self._log("Ressources VISA : " + ", ".join(ressources))
        else:
            self._log("Aucune ressource VISA détectée.", erreur=True)

    def _erreur_backboard(self, msg: str) -> None:
        """Appelé depuis le thread backboard — planifié dans le thread principal."""
        self.after(0, lambda: self._log(f"⚠ BACKBOARD : {msg}", erreur=True))

    def _valider(self) -> None:
        """Vérifie les saisies et transmet les résultats à la phase suivante."""
        indice = self.var_indice.get().strip()
        if not indice:
            messagebox.showwarning("Indice manquant", "Veuillez entrer un indice de notation.")
            return

        noms = self.gp.get_noms_appareils()

        if not noms:
            if not messagebox.askyesno(
                "Aucun port connecté",
                "Aucun appareil connecté. Continuer quand même ?"
            ):
                return

        noms["indice_notation"] = indice

        self._log(f"✔ Validation — appareils : {noms}")

        if self.callback_valide:
            self.callback_valide(noms)

        self.destroy()

    def _quitter(self) -> None:
        self.gp.fermer_tout()
        self.destroy()

    def _log(self, message: str, erreur: bool = False) -> None:
        """Ajoute une ligne dans le journal de l'interface."""
        self.txt_log.configure(state="normal")
        couleur_tag = "erreur" if erreur else "normal"
        self.txt_log.tag_configure("erreur",  foreground="#FF6B6B")
        self.txt_log.tag_configure("normal",  foreground="#D4D4D4")
        ligne = f"[{horodatage_lisible()}]  {message}\n"
        self.txt_log.insert("end", ligne, couleur_tag)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        logger.info(message)


if __name__ == "__main__":
    def afficher_resultat(noms: dict) -> None:
        print("\n=== Appareils validés ===")
        for k, v in noms.items():
            print(f"  {k:20s} : {v}")

    root = tk.Tk()
    root.withdraw()   # cache la fenêtre racine
    app = FenetrePhase1(root, callback_valide=afficher_resultat)
    root.mainloop()
