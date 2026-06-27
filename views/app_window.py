
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from core.logger import creer_logger
from core.paths import horodatage_lisible, get_desktop_path
from core.config import ATTENTE_INTER_SERIE_S
from models.ports import GestionPorts
from models.acquisition import Acquisition
from models.export_xls import ExportXLS
from models.calibration import BoucleCalibration
from models.initialisation import GestionInitialisation
from views.monitor import MonitorTab
from models.thermo import ThermoService
from controllers.thermo_controller import ThermoController
from controllers.init_controller import InitController
from controllers.mesure_controller import MesureController
from controllers.admin_controller import AdminController
from controllers.connexion_controller import ConnexionController
from models.security import admin_key_configured, verify_admin_key, configure_admin_key
from models.audit import (
    JournalAudit,
    EV_CONNEXION, EV_INIT_DEBUT, EV_INIT_FIN, EV_INIT_INTERROMPUE,
    EV_INIT_ECHEC, EV_INIT_VALIDEE, EV_CAL_DEBUT, EV_CAL_SERIE,
    EV_CAL_FIN, EV_CAL_INTERROMPUE, EV_EXPORT_EXCEL,
    EV_SIMULATION_ACTIVE, EV_SIMULATION_DESACTIVE,
    EV_ADMIN_AUTH, EV_ADMIN_LOCK, EV_ADMIN_CLE,
    EV_ERREUR, EV_ARRET,
)

logger = creer_logger("ui")

# ── Charte graphique (palette claire + helpers) ─────────────────────────────────
# La palette et les fabriques de widgets vivent désormais dans views/theme.py.
from views.theme import (
    C, FONT, FONT_SMALL, FONT_BOLD, FONT_TITLE, FONT_LABEL, FONT_VALUE, FONT_MONO,
    ACCENT_VIOLET, ACCENT_VIOLET_HOVER, ACCENT_GREEN, ACCENT_RED, NOIR,
    lbl, sep, card, btn, btn_noir, btn_accent, section_title, champ_saisie,
)

# Alias rétro-compatibles : les pages pas encore redessinées les utilisent encore.
_section_title = section_title
_entry_dark = champ_saisie


# ══════════════════════════════════════════════════════════════════════════════
class ApplicationIPQ(tk.Tk):
# ══════════════════════════════════════════════════════════════════════════════

    def __init__(self) -> None:
        super().__init__()
        self.title("IPQ/LFR — Photometer and Luxmeter Calibration")
        self.configure(bg=C["bg_app"])
        self.minsize(920, 600)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._quitter)
        self.bind_all("<Control-Shift-F12>", self._demander_mode_simulation)

        # ── Objets métier ──────────────────────────────────────────────────
        self.gp             = GestionPorts()
        self.gestion_init   = GestionInitialisation(self.gp)
        self.export_xls:    Optional[ExportXLS] = None
        self._acq_en_cours  = False
        self.journal        = JournalAudit()
        self.var_operateur  = tk.StringVar()
        self._admin_actif      = False
        self._admin_mode_dev   = False
        self._init_sequentielle = False
        self._acq_courante:    Optional[Acquisition]       = None
        self._boucle_courante: Optional[BoucleCalibration] = None
        self._vue_active    = None
        self._nav_btns      = {}
        self._detect_scanning = False
        self._spin_i        = 0

        # COM mesuré pendant les X séries uniquement (l'init n'est pas concernée).
        # Par défaut COM1. L'autre COM n'est pas lu pendant le mesurage.
        self.var_com_mesure = tk.StringVar(value="com1")

        # ── Contrôleurs ────────────────────────────────────────────────────
        self._ctrl_init = InitController(self)
        self._ctrl_mesure = MesureController(self)
        self._ctrl_admin = AdminController(self)
        self._ctrl_connexion = ConnexionController(self)

        # ── Layout racine ──────────────────────────────────────────────────
        self._appliquer_styles_ttk()
        self._construire_layout()
        self._construire_sidebar()
        self._construire_topbar()
        self._construire_vues()

        # Synchronise tout ce qui dépend du COM choisi (Monitor, page Init, mesurage)
        self.var_com_mesure.trace_add("write", lambda *_: self._on_com_change())
        self._monitor.set_com_actif(self.var_com_mesure.get())

        self._naviguer("connexion")
        self._tick_horloge()
        self._thermo = ThermoController(
            self, self.var_t, self.var_hr,
            ThermoService(self.gp, est_occupe=lambda: self._acq_en_cours),
        )
        self._thermo.demarrer()

    # ══════════════════════════════════════════════════════════════════════════
    # Styles ttk (palette claire partagée)
    # ══════════════════════════════════════════════════════════════════════════

    def _appliquer_styles_ttk(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        # Barre de progression verte (Init + mesurage)
        style.configure("Green.Horizontal.TProgressbar",
                        troughcolor="#E3E2DD", bordercolor="#E3E2DD",
                        background=ACCENT_GREEN, lightcolor=ACCENT_GREEN,
                        darkcolor=ACCENT_GREEN, thickness=10)
        # Combobox claire (ports)
        style.configure("TCombobox",
                        fieldbackground=C["bg_input"], background=C["bg_card"],
                        foreground=C["txt_primary"], arrowcolor=C["txt_secondary"],
                        bordercolor=C["border_light"], lightcolor=C["border_light"],
                        darkcolor=C["border_light"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", C["bg_input"])],
                  foreground=[("readonly", C["txt_primary"])],
                  selectbackground=[("readonly", C["bg_input"])],
                  selectforeground=[("readonly", C["txt_primary"])])
        # Tableau de résultats clair
        style.configure("Light.Treeview",
                        background=C["bg_card"], foreground=C["txt_primary"],
                        fieldbackground=C["bg_card"], rowheight=28, font=FONT_SMALL,
                        bordercolor=C["border"])
        style.configure("Light.Treeview.Heading",
                        background="#EEEDE8", foreground=C["txt_secondary"],
                        relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Light.Treeview",
                  background=[("selected", C["bg_active"])],
                  foreground=[("selected", C["txt_active"])])
        # Barres de défilement claires
        style.configure("Vertical.TScrollbar",
                        background=C["bg_hover"], troughcolor=C["bg_app"],
                        arrowcolor=C["txt_secondary"], bordercolor=C["border"])

    # ══════════════════════════════════════════════════════════════════════════
    # Layout principal
    # ══════════════════════════════════════════════════════════════════════════

    def _construire_layout(self) -> None:
        self.frame_sidebar = tk.Frame(self, bg=C["bg_sidebar"], width=210)
        self.frame_sidebar.pack(side="left", fill="y")
        self.frame_sidebar.pack_propagate(False)

        self.frame_right = tk.Frame(self, bg=C["bg_app"])
        self.frame_right.pack(side="left", fill="both", expand=True)

        self.frame_topbar = tk.Frame(self.frame_right, bg=C["bg_topbar"], height=44)
        self.frame_topbar.pack(side="top", fill="x")
        self.frame_topbar.pack_propagate(False)

        self.frame_content = tk.Frame(self.frame_right, bg=C["bg_app"])
        self.frame_content.pack(side="top", fill="both", expand=True)

        self.frame_statusbar = tk.Frame(self.frame_right, bg=C["bg_topbar"], height=28,
                                        highlightbackground=C["border"], highlightthickness=1)
        self.frame_statusbar.pack(side="bottom", fill="x")
        self.frame_statusbar.pack_propagate(False)
        self.lbl_statut = tk.Label(
            self.frame_statusbar, text="Ready.",
            font=FONT_SMALL, bg=C["bg_topbar"], fg=C["txt_muted"], anchor="w", padx=10,
        )
        self.lbl_statut.pack(fill="both", expand=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Sidebar
    # ══════════════════════════════════════════════════════════════════════════

    def _construire_sidebar(self) -> None:
        sb = self.frame_sidebar

        # Logo
        logo = tk.Frame(sb, bg=C["bg_sidebar"])
        logo.pack(fill="x", padx=16, pady=(18, 12))
        tk.Label(logo, text="IPQ / LFR", font=("Segoe UI", 9, "bold"),
                 fg=C["txt_muted"], bg=C["bg_sidebar"]).pack(anchor="w")
        tk.Label(logo, text="Photometer Calibration", font=("Segoe UI", 10),
                 fg=C["txt_secondary"], bg=C["bg_sidebar"],
                 wraplength=180, justify="left").pack(anchor="w", pady=(2, 0))

        sep(sb, C["border"]).pack(fill="x", padx=0)

        nav_frame = tk.Frame(sb, bg=C["bg_sidebar"])
        nav_frame.pack(fill="both", expand=True, padx=8, pady=10)

        sections = [
            ("INSTRUMENTS", [
                ("connexion",   "⬡  Connection"),
            ]),
            ("INITIALIZATION", [
                ("init",        "⬡  Initialization"),
            ]),
            ("MEASUREMENT", [
                ("acquisition", "⬡  Live monitor"),
                ("calibration", "⬡  X-series run"),
            ]),
            ("DATA", [
                ("resultats",   "⬡  Results"),
                ("journal",     "⬡  Event log"),
            ]),
        ]

        for section_label, items in sections:
            tk.Label(nav_frame, text=section_label,
                     font=("Segoe UI", 8, "bold"),
                     fg=C["txt_muted"], bg=C["bg_sidebar"]).pack(
                anchor="w", padx=8, pady=(12, 4))

            for vue_id, label in items:
                b = tk.Button(
                    nav_frame, text=label,
                    font=FONT, fg=C["txt_secondary"], bg=C["bg_sidebar"],
                    activebackground=C["bg_hover"], activeforeground=C["txt_primary"],
                    relief="flat", bd=0, anchor="w", padx=10, pady=7,
                    cursor="hand2",
                    command=lambda v=vue_id: self._naviguer(v),
                )
                b.pack(fill="x", pady=1)
                self._nav_btns[vue_id] = b

        # Section SYSTEM — accès admin (toujours visible, verrouillé par défaut)
        tk.Label(nav_frame, text="SYSTEM",
                 font=("Segoe UI", 8, "bold"),
                 fg=C["txt_muted"], bg=C["bg_sidebar"]).pack(
            anchor="w", padx=8, pady=(12, 4))
        self._btn_admin = tk.Button(
            nav_frame, text="🔒  Administration",
            font=FONT, fg=C["txt_muted"], bg=C["bg_sidebar"],
            activebackground=C["bg_hover"], activeforeground=C["txt_primary"],
            relief="flat", bd=0, anchor="w", padx=10, pady=7,
            cursor="hand2",
            command=lambda: self._naviguer("admin"),
        )
        self._btn_admin.pack(fill="x", pady=1)
        self._nav_btns["admin"] = self._btn_admin

        # Pied sidebar — export
        sep(sb, C["border"]).pack(fill="x")
        footer = tk.Frame(sb, bg=C["bg_sidebar"])
        footer.pack(fill="x", padx=8, pady=10)
        btn(footer, "↓  Save Excel", self._exporter_xls,
            color=C["bg_success"], fgcolor=C["txt_green"],
            padx=10, pady=7).pack(fill="x")

    def _naviguer(self, vue_id: str) -> None:
        if vue_id == "admin" and not self._admin_actif:
            if not self._authentifier_admin():
                return

        # Reset tous les boutons
        for vid, b in self._nav_btns.items():
            b.configure(bg=C["bg_sidebar"], fg=C["txt_secondary"])

        # Activer le bouton sélectionné
        if vue_id in self._nav_btns:
            self._nav_btns[vue_id].configure(bg=C["bg_active"], fg=C["txt_active"])

        # Cacher toutes les vues, montrer la cible
        for child in self.frame_content.winfo_children():
            child.pack_forget()

        vue = self._vues.get(vue_id)
        if vue:
            vue.pack(fill="both", expand=True)

        self._vue_active = vue_id

    # ══════════════════════════════════════════════════════════════════════════
    # Topbar
    # ══════════════════════════════════════════════════════════════════════════

    def _construire_topbar(self) -> None:
        tb = self.frame_topbar

        # Badge statut acquisition
        self.badge_frame = tk.Frame(tb, bg=C["bg_badge"],
                                    highlightbackground="#166534",
                                    highlightthickness=1)
        self.badge_frame.pack(side="left", padx=14, pady=10)
        self.lbl_badge = tk.Label(self.badge_frame, text="  ●  Standby",
                                   font=FONT_SMALL, fg=C["txt_muted"],
                                   bg=C["bg_badge"], padx=8, pady=0)
        self.lbl_badge.pack()

        # Verrou admin — cliquable pour ouvrir/fermer la session admin
        self.lbl_admin_verrou = tk.Label(
            tb, text="🔒", font=("Segoe UI", 13),
            fg=C["txt_muted"], bg=C["bg_topbar"],
            cursor="hand2", padx=8,
        )
        self.lbl_admin_verrou.pack(side="left", pady=6)
        self.lbl_admin_verrou.bind("<Button-1>", lambda _: self._naviguer("admin"))

        # Séparateur
        tk.Frame(tb, width=1, bg=C["border"]).pack(side="left", fill="y", pady=8)

        self.lbl_simulation = tk.Label(
            tb,
            text="SIMULATION — DATA NOT VALID",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff",
            bg="#b91c1c",
            padx=12,
            pady=3,
        )

        # Capteurs droite
        self.var_t       = tk.StringVar(value="T: — °C")
        self.var_hr      = tk.StringVar(value="RH: — %")
        self.var_dist_tb = tk.StringVar(value="— mm")
        self.var_date    = tk.StringVar(value="")
        self.var_heure   = tk.StringVar(value="")

        # Badge opérateur
        self.lbl_operateur = tk.Label(
            tb, textvariable=self.var_operateur,
            font=FONT_SMALL, fg=C["txt_secondary"], bg=C["bg_topbar"],
            padx=10,
        )
        self.lbl_operateur.pack(side="right")
        tk.Frame(tb, width=1, bg=C["border"]).pack(side="right", fill="y", pady=8)

        sensors_frame = tk.Frame(tb, bg=C["bg_topbar"])
        sensors_frame.pack(side="right", padx=14)

        for var, icon in [
            (self.var_heure,   "⏱"),
            (self.var_date,    "📅"),
            (self.var_dist_tb, "⇔"),
            (self.var_hr,      "💧"),
            (self.var_t,       "🌡"),
        ]:
            f = tk.Frame(sensors_frame, bg=C["bg_topbar"])
            f.pack(side="right", padx=12)
            tk.Label(f, text=icon, font=("Segoe UI", 10),
                     bg=C["bg_topbar"], fg=C["txt_muted"]).pack(side="left", padx=(0, 4))
            tk.Label(f, textvariable=var, font=FONT_SMALL,
                     bg=C["bg_topbar"], fg=C["txt_secondary"]).pack(side="left")

    # ══════════════════════════════════════════════════════════════════════════
    # Vues
    # ══════════════════════════════════════════════════════════════════════════

    def _construire_vues(self) -> None:
        self._monitor = MonitorTab(self.frame_content, bg=C["bg_app"])
        self._vues = {
            "connexion":   self._vue_connexion(),
            "init":        self._vue_init(),
            "acquisition": self._monitor,
            "calibration": self._vue_calibration(),
            "resultats":   self._vue_resultats(),
            "journal":     self._vue_journal(),
            "admin":       self._vue_admin(),
        }

    # ── Vue : Connexion ───────────────────────────────────────────────────────

    def _vue_connexion(self) -> tk.Frame:
        f = tk.Frame(self.frame_content, bg=C["bg_app"])
        scroll = _ScrollFrame(f)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner

        _section_title(inner, "Instrument connection")

        # ── Session : opérateur + indice de notation ──────────────────────
        c_sess = card(inner)
        c_sess.pack(fill="x", padx=20, pady=(0, 12))
        lbl(c_sess, "SESSION", FONT_LABEL, C["txt_muted"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(12, 8))
        row_sess = tk.Frame(c_sess, bg=C["bg_card"])
        row_sess.pack(fill="x", padx=14, pady=(0, 12))

        col_op = tk.Frame(row_sess, bg=C["bg_card"])
        col_op.pack(side="left", fill="x", expand=True, padx=(0, 12))
        lbl(col_op, "Operator", FONT_LABEL, C["txt_muted"], C["bg_card"]).pack(anchor="w")
        champ_saisie(col_op, self.var_operateur).pack(fill="x", pady=(3, 0))

        self.var_indice = tk.StringVar()
        col_id = tk.Frame(row_sess, bg=C["bg_card"])
        col_id.pack(side="left", fill="x", expand=True)
        lbl(col_id, "Notation index", FONT_LABEL, C["txt_muted"], C["bg_card"]).pack(anchor="w")
        champ_saisie(col_id, self.var_indice).pack(fill="x", pady=(3, 0))

        # GPIB conservé en arrière-plan (non affiché) — ne pas casser le contrôleur.
        self.var_gpib = tk.StringVar(value="GPIB0::1::INSTR")

        # ── Ports instruments ─────────────────────────────────────────────
        c_ports = card(inner)
        c_ports.pack(fill="x", padx=20, pady=(0, 12))
        lbl(c_ports, "INSTRUMENT PORTS", FONT_LABEL, C["txt_muted"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        lbl(c_ports,
            "Assign each role to its serial port — ports may change when the card is reconnected.",
            FONT_SMALL, C["txt_muted"], C["bg_card"]).pack(anchor="w", padx=14, pady=(0, 8))

        self._port_vars   = {}
        self._port_labels = {}
        for nom, label in [("com1", "COM1   ·   Multimeter 1"),
                           ("com2", "COM2   ·   Multimeter 2"),
                           ("thermo1", "Thermo1   ·   Thermohygrometer")]:
            row = tk.Frame(c_ports, bg=C["bg_card"])
            row.pack(fill="x", padx=14, pady=5)
            lbl(row, label, FONT, C["txt_primary"], C["bg_card"]).pack(side="left")

            dot = tk.Label(row, text="●", font=("Segoe UI", 13),
                           bg=C["bg_card"], fg=C["txt_muted"])
            dot.pack(side="right", padx=(8, 0))
            self._port_labels[nom] = dot

            var = tk.StringVar()
            self._port_vars[nom] = var
            cb = ttk.Combobox(row, textvariable=var, width=12, state="readonly",
                              font=FONT_SMALL)
            cb.pack(side="right", padx=(0, 8))

            # Connexion du port laissée disponible (la gestion fine des COM est faite à part).
            btn(row, "Connect",
                command=lambda n=nom: self._connecter_port(n),
                padx=10, pady=3).pack(side="right", padx=(0, 8))

        row_btns = tk.Frame(c_ports, bg=C["bg_card"])
        row_btns.pack(fill="x", padx=14, pady=(8, 4))
        btn_noir(row_btns, "↻   Refresh ports",
                 command=self._rafraichir_ports, padx=12, pady=7).pack(side="left")
        self._btn_detect = btn_noir(row_btns, "⌖   Auto-detect",
                                    command=self._auto_detecter, padx=12, pady=7)
        self._btn_detect.pack(side="left", padx=(8, 0))
        self.lbl_detect = lbl(c_ports, "", FONT_SMALL, C["txt_muted"], C["bg_card"])
        self.lbl_detect.pack(anchor="w", padx=14, pady=(6, 12))

        # ── Valider la connexion (rouge → vert) ───────────────────────────
        self.btn_validate = btn_accent(
            inner, "Validate connection", command=self._valider_connexion,
            color=ACCENT_RED, padx=26, pady=12)
        self.btn_validate.pack(anchor="w", padx=20, pady=(4, 20))

        self._rafraichir_ports()
        return f

    # ── Vue : Acquisition ─────────────────────────────────────────────────────


    # ── Vue : Initialisation ──────────────────────────────────────────────────

    def _vue_init(self) -> tk.Frame:
        f = tk.Frame(self.frame_content, bg=C["bg_app"])
        scroll = _ScrollFrame(f)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner

        # ── Paramètre Distance ────────────────────────────────────────────
        _section_title(inner, "Photometric bench")

        c_dist = card(inner)
        c_dist.pack(fill="x", padx=20, pady=(0, 12))
        grid_d = tk.Frame(c_dist, bg=C["bg_card"])
        grid_d.pack(padx=14, pady=12, anchor="w")
        lbl(grid_d, "Lamp-to-sensor distance (mm):", FONT, C["txt_secondary"], C["bg_card"]).grid(
            row=0, column=0, sticky="e", padx=(0, 10), pady=5)
        self.var_distance = tk.StringVar(value="0.0")
        _entry_dark(grid_d, self.var_distance, width=14).grid(row=0, column=1, sticky="w", pady=5)
        lbl(c_dist, "This value is exported with every series.",
            FONT_SMALL, C["txt_muted"], C["bg_card"]).pack(anchor="w", padx=14, pady=(0, 12))

        # ── Section Initialisation ────────────────────────────────────────
        _section_title(inner, "Initialization — 2 × 30 points")

        self._build_init_card(inner, "com1")
        self._build_init_card(inner, "com2")

        # Bouton Valider (désactivé tant que COM1 ET COM2 ne sont pas faits)
        c_val = card(inner)
        c_val.pack(fill="x", padx=20, pady=(0, 20))
        val_inner = tk.Frame(c_val, bg=C["bg_card"])
        val_inner.pack(padx=14, pady=14, fill="x")

        self.lbl_val_hint = lbl(
            val_inner,
            "Run both COM 1 and COM 2 initialization before approval.",
            FONT_SMALL, C["txt_muted"], C["bg_card"],
        )
        self.lbl_val_hint.pack(anchor="w", pady=(0, 8))

        self.btn_valider_init = btn(
            val_inner, "✔  Approve initialization",
            command=self._valider_init,
            color=C["bg_hover"], fgcolor=C["txt_muted"],
            padx=14, pady=8,
        )
        self.btn_valider_init.configure(state="disabled")
        self.btn_valider_init.pack(anchor="w")

        return f

    def _build_init_card(self, parent, cible: str) -> None:
        n = cible[-1]
        c = card(parent)
        c.pack(fill="x", padx=20, pady=(0, 8))
        h = tk.Frame(c, bg=C["bg_card"])
        h.pack(fill="x", padx=14, pady=(12, 6))
        lbl(h, f"Init COM{n}", FONT_BOLD, C["txt_primary"], C["bg_card"]).pack(side="left")
        statut = lbl(h, "Standby", FONT_SMALL, C["txt_muted"], C["bg_card"])
        statut.pack(side="right")
        setattr(self, f"lbl_init{n}_statut", statut)
        prog = ttk.Progressbar(c, length=100, maximum=30, mode="determinate",
                               style="Green.Horizontal.TProgressbar")
        prog.pack(fill="x", padx=14, pady=(0, 8))
        setattr(self, f"prog_init{n}", prog)
        mv = tk.Frame(c, bg=C["bg_card"])
        mv.pack(fill="x", padx=14, pady=(0, 12))
        for attr, txt in [
            (f"var_m_init{n}", f"M init{n}"), (f"var_v_init{n}", f"V init{n}"),
            (f"var_t_init{n}", "Mean T"),      (f"var_hr_init{n}", "Mean RH"),
        ]:
            sub = tk.Frame(mv, bg=C["bg_card"])
            sub.pack(side="left", padx=(0, 20))
            lbl(sub, txt.upper(), FONT_LABEL, C["txt_muted"], C["bg_card"]).pack(anchor="w")
            var = tk.StringVar(value="—")
            setattr(self, attr, var)
            tk.Label(sub, textvariable=var, font=("Segoe UI", 13, "bold"),
                     fg=C["txt_blue"], bg=C["bg_card"]).pack(anchor="w")
        pady_btn = (0, 4) if cible == "com1" else (0, 12)
        btn_noir(c, f"▶   Run COM{n} initialization",
                 command=lambda ci=cible: self._lancer_init(ci),
                 padx=12, pady=6).pack(anchor="w", padx=14, pady=pady_btn)
        if cible == "com1":
            b_seq = btn(c, "⏩   Initialize COM1 then COM2 automatically",
                        command=self._lancer_init_sequentielle,
                        color=C["bg_card"], fgcolor=C["txt_secondary"],
                        padx=12, pady=5)
            b_seq.configure(highlightbackground=C["border_light"], highlightthickness=1)
            b_seq.pack(anchor="w", padx=14, pady=(0, 12))

    def _maj_boutons_com(self) -> None:
        """Boutons COM1/COM2 : exclusifs, tous deux verts (plein = mesuré, contour = dispo)."""
        sel = self.var_com_mesure.get() or "com1"
        for com, b in (("com1", self._btn_com1), ("com2", self._btn_com2)):
            if com == sel:
                b.configure(bg=ACCENT_GREEN, fg="#ffffff",
                            activebackground=ACCENT_GREEN, activeforeground="#ffffff",
                            highlightbackground=ACCENT_GREEN, highlightthickness=0)
            else:
                b.configure(bg=C["bg_card"], fg=C["txt_green"],
                            activebackground=C["bg_success"], activeforeground=C["txt_green"],
                            highlightbackground=ACCENT_GREEN, highlightthickness=1)

    def _on_com_change(self) -> None:
        """COM mesuré (X séries) changé : sync Monitor + boutons verts."""
        sel = self.var_com_mesure.get() or "com1"
        self._monitor.set_com_actif(sel)
        if hasattr(self, "_btn_com1"):
            self._maj_boutons_com()

    # ── Vue : Calibration ─────────────────────────────────────────────────────

    def _vue_calibration(self) -> tk.Frame:
        f = tk.Frame(self.frame_content, bg=C["bg_app"])
        _section_title(f, "Measurement — X series")

        # ── Multimètre mesuré (sélectionnable ici) ────────────────────────
        c_sel = card(f)
        c_sel.pack(fill="x", padx=20, pady=(0, 12))
        row_sel = tk.Frame(c_sel, bg=C["bg_card"])
        row_sel.pack(anchor="w", padx=14, pady=(12, 8))
        lbl(row_sel, "Measuring multimeter:", FONT_BOLD, C["txt_primary"], C["bg_card"]).pack(
            side="left", padx=(0, 12))
        self._btn_com1 = btn(
            row_sel, "COM 1",
            command=lambda: self.var_com_mesure.set("com1"),
            color=C["bg_input"], fgcolor=C["txt_secondary"],
            padx=14, pady=6)
        self._btn_com1.pack(side="left", padx=(0, 6))
        self._btn_com2 = btn(
            row_sel, "COM 2",
            command=lambda: self.var_com_mesure.set("com2"),
            color=C["bg_input"], fgcolor=C["txt_secondary"],
            padx=14, pady=6)
        self._btn_com2.pack(side="left")
        lbl(c_sel,
            "Select the multimeter to read",
            FONT_SMALL, C["txt_muted"], C["bg_card"]).pack(anchor="w", padx=14, pady=(0, 12))
        self._maj_boutons_com()

        c = card(f)
        c.pack(fill="x", padx=20, pady=(0, 12))

        grid = tk.Frame(c, bg=C["bg_card"])
        grid.pack(padx=14, pady=14)

        lbl(grid, "Number of series X:", FONT, C["txt_secondary"], C["bg_card"]).grid(
            row=0, column=0, sticky="e", padx=(0, 10), pady=6)
        self.var_nb_series = tk.IntVar(value=5)
        sp = tk.Spinbox(grid, from_=1, to=99, textvariable=self.var_nb_series,
                        width=6, font=FONT,
                        bg=C["bg_input"], fg=C["txt_primary"],
                        buttonbackground=C["bg_hover"],
                        relief="flat", bd=1,
                        highlightbackground=C["border_light"],
                        highlightthickness=1)
        sp.grid(row=0, column=1, sticky="w", pady=6)

        lbl(grid, "Wait between series (s):", FONT, C["txt_secondary"], C["bg_card"]).grid(
            row=1, column=0, sticky="e", padx=(0, 10), pady=6)
        self.var_attente_s = tk.IntVar(value=60)
        tk.Spinbox(grid, from_=0, to=600, increment=5, textvariable=self.var_attente_s,
                   width=6, font=FONT,
                   bg=C["bg_input"], fg=C["txt_primary"],
                   buttonbackground=C["bg_hover"],
                   relief="flat", bd=1,
                   highlightbackground=C["border_light"],
                   highlightthickness=1).grid(row=1, column=1, sticky="w", pady=6)
        lbl(grid, "Beeps (1/s, rising pitch) play during the wait.",
            FONT_SMALL, C["txt_muted"], C["bg_card"]).grid(
            row=1, column=2, sticky="w", padx=(10, 0), pady=6)

        # Progression boucle
        self.lbl_serie_status = lbl(c, "Series — / —", FONT_BOLD, C["txt_blue"], C["bg_card"])
        self.lbl_serie_status.pack(anchor="w", padx=14)

        self.progress_cal = ttk.Progressbar(c, length=100, maximum=5, mode="determinate",
                                            style="Green.Horizontal.TProgressbar")
        self.progress_cal.pack(fill="x", padx=14, pady=(6, 14))

        btn_cal_row = tk.Frame(f, bg=C["bg_app"])
        btn_cal_row.pack(anchor="w", padx=20, pady=(0, 20))
        self.btn_cal_start = btn(btn_cal_row, "▶  Start measurement",
                                 command=self._lancer_calibration,
                                 color=ACCENT_GREEN, fgcolor="#ffffff",
                                 padx=16, pady=9)
        self.btn_cal_start.configure(activebackground=ACCENT_GREEN, activeforeground="#ffffff")
        self.btn_cal_start.pack(side="left", padx=(0, 8))
        self.btn_cal_stop = btn(btn_cal_row, "■  Stop",
                                command=self._arreter_calibration,
                                color=ACCENT_RED, fgcolor="#ffffff",
                                padx=14, pady=9)
        self.btn_cal_stop.configure(activebackground=ACCENT_RED, activeforeground="#ffffff",
                                    state="disabled")
        self.btn_cal_stop.pack(side="left")

        return f

    # ── Vue : Résultats ───────────────────────────────────────────────────────

    def _vue_resultats(self) -> tk.Frame:
        f = tk.Frame(self.frame_content, bg=C["bg_app"])
        _section_title(f, "Results — all series")

        table_wrap = tk.Frame(f, bg=C["bg_app"])
        table_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        cols = ("Series", "Distance (mm)", "Mean M", "Variance V", "Mean T (°C)", "Mean RH (%)")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings",
                                  style="Light.Treeview", height=15)
        widths = [130, 110, 130, 130, 110, 110]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center", minwidth=70)
        self.tree.column("Series", anchor="w")
        self.tree.tag_configure("init", foreground=C["txt_active"])

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        btn(f, "↓   Export to Excel", command=self._exporter_xls,
            color=ACCENT_VIOLET, fgcolor="#ffffff",
            font=FONT_BOLD, padx=22, pady=10).pack(anchor="w", padx=20, pady=(4, 20))

        return f

    # ── Vue : Journal ─────────────────────────────────────────────────────────

    def _vue_journal(self) -> tk.Frame:
        f = tk.Frame(self.frame_content, bg=C["bg_app"])
        _section_title(f, "Event log")

        wrap = tk.Frame(f, bg=C["bg_card"],
                        highlightbackground=C["border"], highlightthickness=1)
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.txt_journal = tk.Text(
            wrap, bg=C["bg_card"], fg=C["txt_primary"],
            font=FONT_MONO, relief="flat", bd=0,
            state="disabled", wrap="word", padx=12, pady=8,
            selectbackground=C["bg_active"], selectforeground=C["txt_active"],
        )
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.txt_journal.yview)
        self.txt_journal.configure(yscrollcommand=vsb.set)
        self.txt_journal.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self.txt_journal.tag_configure("err",  foreground=C["txt_red"])
        self.txt_journal.tag_configure("ok",   foreground=C["txt_green"])
        self.txt_journal.tag_configure("info", foreground=C["txt_secondary"])
        self.txt_journal.tag_configure("ts",   foreground=C["txt_muted"])

        return f

    # ══════════════════════════════════════════════════════════════════════════
    # Actions — Connexion
    # ══════════════════════════════════════════════════════════════════════════

    def _rafraichir_ports(self) -> None:
        self._ctrl_connexion.rafraichir_ports()

    def _iter_comboboxes(self):
        """Parcourt tous les Combobox dans frame_content."""
        return self._find_widgets(self.frame_content, ttk.Combobox)

    def _find_widgets(self, parent, wtype):
        result = []
        for child in parent.winfo_children():
            if isinstance(child, wtype):
                result.append(child)
            result.extend(self._find_widgets(child, wtype))
        return result

    def _connecter_port(self, cible: str) -> None:
        self._ctrl_connexion.connecter(cible)

    def _connecter_gpib(self) -> None:
        self._ctrl_connexion.connecter_gpib()

    def _lister_visa(self) -> None:
        self._ctrl_connexion.lister_visa()

    def _auto_detecter(self) -> None:
        self._ctrl_connexion.auto_detecter()

    def _valider_connexion(self) -> None:
        self._ctrl_connexion.valider()

    # ── Vue Connexion (pilotée par ConnexionController) ───────────────────────

    def _vue_ports_disponibles(self, ports) -> None:
        liste = [""] + ports
        for widget in self._iter_comboboxes():
            widget["values"] = liste
        self._log(f"Detected ports: {ports or 'none'}")

    def _vue_port_ok(self, cible: str, port: str) -> None:
        self._port_labels[cible].configure(fg=C["txt_green"])
        self._log(f"{cible.upper()} connected on {port}", "ok")

    def _vue_port_echec(self, cible: str, msg: str) -> None:
        self._port_labels[cible].configure(fg=C["txt_red"])
        self._log(msg, "err")

    def _vue_gpib(self, ok: bool, idn) -> None:
        if hasattr(self, "lbl_gpib_dot"):
            self.lbl_gpib_dot.configure(fg=C["txt_green"] if ok else C["txt_red"])
        if ok:
            self._log(f"GPIB connected: {idn}", "ok")
        else:
            self._log("GPIB connection failed.", "err")

    def _vue_visa(self, ressources) -> None:
        if not hasattr(self, "lbl_visa_list"):
            return
        if ressources:
            self.lbl_visa_list.configure(text="  ".join(ressources), fg=C["txt_secondary"])
        else:
            self.lbl_visa_list.configure(text="No VISA resource detected.", fg=C["txt_red"])

    def _vue_detect_indispo(self) -> None:
        self.lbl_detect.configure(text="pyserial required for auto-detect.", fg=C["txt_red"])

    def _spin_detect(self) -> None:
        """Anime l'icône du bouton Auto-detect pendant le scan (cycle de glyphes)."""
        frames = ("◐", "◓", "◑", "◒")
        if not self._detect_scanning:
            if hasattr(self, "_btn_detect"):
                self._btn_detect.configure(text="⌖   Auto-detect")
            return
        self._spin_i = (self._spin_i + 1) % len(frames)
        self._btn_detect.configure(text=f"{frames[self._spin_i]}   Scanning…")
        self.after(120, self._spin_detect)

    def _vue_detect_scan(self) -> None:
        self.lbl_detect.configure(text="Scanning ports…", fg=C["txt_amber"])
        for nom in ("com1", "com2", "thermo1"):
            self._port_labels[nom].configure(fg=C["txt_muted"])
        self._detect_scanning = True
        self._spin_detect()

    def _vue_detection(self, data: dict) -> None:
        self._detect_scanning = False
        if hasattr(self, "_btn_detect"):
            self._btn_detect.configure(text="⌖   Auto-detect")
        mapping    = data.get("mapping", {})
        detections = data.get("detections", [])
        for cible in ("com1", "com2", "thermo1"):
            dot = self._port_labels[cible]
            if cible in mapping:
                self._port_vars[cible].set(mapping[cible]["port"])
                dot.configure(fg=C["txt_green"])
            else:
                dot.configure(fg=C["txt_red"])
        if detections:
            noms = ", ".join(f"{d['instrument']} @ {d['port']}" for d in detections)
            self.lbl_detect.configure(text=f"{len(detections)} detected — {noms}",
                                      fg=C["txt_green"])
            self._log(f"Auto-detect: {noms}", "ok")
        else:
            self.lbl_detect.configure(text="No instrument detected.", fg=C["txt_red"])
            self._log("Auto-detect: no instrument found.", "err")

    def _vue_operateur(self, operateur: str) -> None:
        self.var_operateur.set(f"👤  {operateur}")

    def _vue_connexion_ok(self, indice, simulation, dossier, chemin) -> None:
        self._log(f"Excel file created: {chemin}", "ok")
        if simulation:
            self._log(f"Simulation folder: {os.path.abspath(dossier)}", "info")
        self._statut(f"Configured — identifier: {indice}")
        if hasattr(self, "btn_validate"):
            self.btn_validate.configure(text="Connection validated",
                                        bg=ACCENT_GREEN, activebackground=ACCENT_GREEN)
        self._naviguer("acquisition")

    def demander_confirmation(self, titre: str, message: str) -> bool:
        return messagebox.askyesno(titre, message)

    # ══════════════════════════════════════════════════════════════════════════
    # Actions — Initialisation
    # ══════════════════════════════════════════════════════════════════════════

    def _lancer_init(self, cible: str) -> None:
        self._ctrl_init.lancer(cible)

    def _valider_init(self) -> None:
        self._ctrl_init.valider()

    def _maj_init_pt(self, cible: str, i: int, valeur, t: float, hr: float) -> None:
        n = cible[-1]
        getattr(self, f"prog_init{n}")["value"] = i
        self._monitor.on_init_point(cible, i, valeur, t, hr)
        self.var_t.set(f"T: {t:.1f} °C")
        self.var_hr.set(f"RH: {hr:.1f} %")

    # ── Vue Init (mise à jour des widgets, pilotée par InitController) ─────────

    def _vue_init_demarrage(self, cible: str) -> None:
        n = cible[-1]
        getattr(self, f"prog_init{n}")["value"] = 0
        getattr(self, f"lbl_init{n}_statut").configure(text="Running…", fg=C["txt_amber"])
        self._badge(f"● COM{n} initialization running", C["txt_amber"], "#3a2a00")

    def _vue_init_standby(self) -> None:
        self._badge("● Standby", C["txt_muted"], C["bg_badge"])

    def _vue_init_interrompu(self, cible: str) -> None:
        n = cible[-1]
        getattr(self, f"lbl_init{n}_statut").configure(text="Interrupted", fg=C["txt_red"])
        self._log(f"{cible.upper()} initialization interrupted — not recorded.", "err")

    def _vue_init_resultats(self, cible: str, m, v, t_moy, hr_moy) -> None:
        n = cible[-1]
        getattr(self, f"var_m_init{n}").set(f"{m:.6f}")
        getattr(self, f"var_v_init{n}").set(f"{v:.6f}")
        getattr(self, f"var_t_init{n}").set(f"{t_moy:.2f} °C")
        getattr(self, f"var_hr_init{n}").set(f"{hr_moy:.2f} %")
        getattr(self, f"lbl_init{n}_statut").configure(text="Completed", fg=C["txt_green"])
        getattr(self, f"prog_init{n}")["value"] = 30
        self._monitor.on_init_complete(cible, m, v)
        if hasattr(self, "tree"):
            iid = f"init_{cible}"
            valeurs = (f"Init {cible.upper()}", f"{self.gestion_init.distance_mm:.1f}",
                       f"{m:.6f}", f"{v:.6f}", f"{t_moy:.2f}", f"{hr_moy:.2f}")
            if self.tree.exists(iid):
                self.tree.item(iid, values=valeurs)
            else:
                pos = len([i for i in self.tree.get_children("") if str(i).startswith("init_")])
                self.tree.insert("", pos, iid=iid, values=valeurs, tags=("init",))
        self._log(f"COM{n} initialization — M={m:.6f}  V={v:.6f}", "ok")

    def _vue_init_pret(self) -> None:
        self.btn_valider_init.configure(
            state="normal", bg=ACCENT_GREEN, fg="#ffffff",
            activebackground=ACCENT_GREEN, activeforeground="#ffffff")
        self.lbl_val_hint.configure(
            text="Both acquisitions are ready. Click to approve.",
            fg=C["txt_secondary"],
        )

    def _vue_init_approuve(self) -> None:
        self.btn_valider_init.configure(
            text="Initialization approved", bg="#2e7d4f",
            fg="#ffffff", state="disabled",
        )
        self.lbl_val_hint.configure(
            text="Initialization approved — measurement may now be started.",
            fg=C["txt_green"],
        )

    def afficher_avertissement(self, titre: str, message: str) -> None:
        messagebox.showwarning(titre, message)

    def afficher_erreur(self, titre: str, message: str) -> None:
        messagebox.showerror(titre, message)

    # ══════════════════════════════════════════════════════════════════════════
    # Actions — Calibration
    # ══════════════════════════════════════════════════════════════════════════

    def _lancer_calibration(self) -> None:
        self._ctrl_mesure.lancer()

    def _arreter_calibration(self) -> None:
        self._ctrl_mesure.arreter()

    def _lire_nb_series(self) -> Optional[int]:
        try:
            x = int(self.var_nb_series.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid value", "The number of series X is invalid.")
            return None
        if x < 1:
            messagebox.showerror("Invalid value", "X must be at least 1.")
            return None
        return x

    def _lire_attente_s(self) -> int:
        try:
            return max(int(self.var_attente_s.get()), 0)
        except (tk.TclError, ValueError):
            return ATTENTE_INTER_SERIE_S

    # ── Vue Mesure (pilotée par MesureController) ─────────────────────────────

    def _vue_mesure_demarrage(self, x: int, cible: str) -> None:
        self.progress_cal.configure(maximum=x)
        self.progress_cal["value"] = 0
        self._monitor.set_com_actif(cible)
        self._monitor.set_nb_series(x)
        self.btn_cal_start.configure(state="disabled")
        self.btn_cal_stop.configure(state="normal")
        self._badge(f"● Measurement — 0 / {x}", C["txt_amber"], "#3a2a00")

    def _vue_mesure_attente(self, prochaine: int, restant: int, x: int) -> None:
        self._badge(f"● Waiting {restant}s — next series {prochaine}/{x}",
                    C["txt_blue"], "#0a2a3a")

    def _vue_mesure_serie(self, x, nb, m, v, t_moy, hr_moy, dist) -> None:
        self.lbl_serie_status.configure(text=f"Series {x} / {nb}")
        self.progress_cal["value"] = x
        self._badge(f"● Measurement — {x} / {nb}", C["txt_amber"], "#3a2a00")
        self.tree.insert("", "end", values=(
            f"Series {x}", f"{dist:.1f}", f"{m:.6f}", f"{v:.6f}", f"{t_moy:.2f}", f"{hr_moy:.2f}"))
        self._monitor.on_serie_complete(x, m, v)
        self._log(f"Series {x}/{nb} — M={m:.6f}  distance={dist:.1f} mm", "ok")

    def _vue_mesure_arret_demande(self) -> None:
        self.btn_cal_stop.configure(state="disabled")
        self._badge("● Stop requested…", C["txt_amber"], "#3a2a00")
        self._log("Measurement stop requested…", "info")

    def _vue_mesure_boutons_repos(self) -> None:
        self.btn_cal_start.configure(state="normal")
        self.btn_cal_stop.configure(state="disabled")

    def _vue_mesure_erreur(self, erreur: str, nb: int) -> None:
        self._badge("● Error", C["txt_red"], C["bg_danger"])
        self._statut(f"Measurement stopped — {nb} series saved.")
        self._log(f"Measurement failed: {erreur}", "err")
        messagebox.showerror("Measurement error", erreur)

    def _vue_mesure_interrompu(self, nb: int) -> None:
        self._badge("● Interrupted", C["txt_red"], C["bg_danger"])
        self._statut(f"Measurement interrupted — {nb} series recorded.")
        self._log(f"Measurement interrupted — {nb} series recorded.", "err")

    def _vue_mesure_termine(self, nb: int) -> None:
        self._badge("● Completed", C["txt_green"], "#1a3a1a")
        self._statut(f"Measurement completed — {nb} series.")
        self._log(f"Measurement completed — {nb} series.", "ok")

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _demander_mode_simulation(self, _event=None) -> None:
        """Ctrl+Shift+F12 — raccourci vers le panneau admin."""
        self._naviguer("admin")

    # ══════════════════════════════════════════════════════════════════════════
    # Administration
    # ══════════════════════════════════════════════════════════════════════════

    def _authentifier_admin(self) -> bool:
        return self._ctrl_admin.authentifier()

    def _verrouiller_admin(self) -> None:
        self._ctrl_admin.verrouiller()

    def _basculer_simulation(self) -> None:
        self._ctrl_admin.basculer_simulation()

    def _configurer_cle_admin(self) -> None:
        self._ctrl_admin.configurer_cle()

    def _verifier_journal_audit(self) -> None:
        self._ctrl_admin.verifier_journal()

    def _lancer_init_sequentielle(self) -> None:
        self._init_sequentielle = True
        self._lancer_init("com1")

    # ── Dialogues + Vue Admin (pilotés par AdminController) ───────────────────

    def demander_secret(self, titre: str, message: str):
        return simpledialog.askstring(titre, message, show="*", parent=self)

    def _vue_admin_deverrouille(self) -> None:
        self.lbl_admin_verrou.configure(text="🔓", fg=C["txt_amber"])
        self._nav_btns["admin"].configure(text="🔓  Administration", fg=C["txt_amber"])

    def _vue_admin_verrouille(self) -> None:
        self.lbl_admin_verrou.configure(text="🔒", fg=C["txt_muted"])
        self._nav_btns["admin"].configure(text="🔒  Administration", fg=C["txt_muted"])

    def _vue_simulation(self, enabled: bool) -> None:
        for dot in self._port_labels.values():
            dot.configure(fg=C["txt_muted"])
        if enabled:
            self.lbl_simulation.pack(side="left", padx=12, pady=8)
            self._badge("● Simulation ready", C["txt_amber"], "#3a2a00")
            self._statut("SIMULATION MODE ENABLED — generated data are not valid.")
            self._log("SIMULATION MODE ENABLED.", "err")
        else:
            self.lbl_simulation.pack_forget()
            self._badge("● Standby", C["txt_muted"], C["bg_badge"])
            self._statut("Simulation mode disabled.")
            self._log("Simulation mode disabled.", "info")
        self._actualiser_btn_sim()

    def _actualiser_btn_sim(self) -> None:
        if not hasattr(self, "_btn_sim_toggle"):
            return
        if self.gp.mode_simulation:
            self._btn_sim_toggle.configure(
                text="Disable simulation mode",
                bg=ACCENT_RED, fg="#ffffff",
                activebackground=ACCENT_RED, activeforeground="#ffffff",
                highlightthickness=0,
            )
        else:
            self._btn_sim_toggle.configure(
                text="Enable simulation mode",
                bg=C["bg_card"], fg=C["txt_secondary"],
                activebackground=C["bg_hover"], activeforeground=C["txt_primary"],
                highlightbackground=C["border_light"], highlightthickness=1,
            )

    def _vue_cle_configuree(self) -> None:
        self._lbl_cle_statut.configure(
            text="Key configured (PBKDF2-SHA256).", fg=C["txt_green"])
        self._admin_warn_frame.pack_forget()
        messagebox.showinfo("Success", "Administrator key configured successfully.")

    def _vue_audit_resultat(self, ok: bool, nb: int, premiere_erreur) -> None:
        if ok:
            self._lbl_audit_result.configure(
                text=f"✓  Integrity OK — {nb} entries verified.",
                fg=C["txt_green"],
            )
        else:
            self._lbl_audit_result.configure(
                text=f"✗  CHAIN BROKEN at line {premiere_erreur} / {nb}.",
                fg=C["txt_red"],
            )

    def _ouvrir_dossier_audit(self) -> None:
        import subprocess
        from models.audit import AUDIT_DIR
        os.makedirs(AUDIT_DIR, exist_ok=True)
        subprocess.Popen(f'explorer "{AUDIT_DIR}"')

    def _ouvrir_dossier_simulation(self) -> None:
        """Ouvre le dossier des exports de simulation (Bureau)."""
        import subprocess
        dossier = os.path.join(get_desktop_path(), "IPQ_LFR_Simulation")
        os.makedirs(dossier, exist_ok=True)
        subprocess.Popen(f'explorer "{dossier}"')

    # ── Vue : Administration ──────────────────────────────────────────────────

    def _vue_admin(self) -> tk.Frame:
        f = tk.Frame(self.frame_content, bg=C["bg_app"])
        scroll = _ScrollFrame(f)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner

        _section_title(inner, "Administration")

        # Bandeau avertissement mode dev (clair, ambre)
        self._admin_warn_frame = tk.Frame(inner, bg="#FBF1DD",
                                           highlightbackground="#E6C97A",
                                           highlightthickness=1)
        if not admin_key_configured():
            self._admin_warn_frame.pack(fill="x", padx=20, pady=(0, 12))
        lbl(self._admin_warn_frame,
            "⚠  Development mode — default password 'admin' is active.\n"
            "    Configure a real key before any production use.",
            FONT_SMALL, "#8A6D1F", "#FBF1DD").pack(padx=14, pady=10, anchor="w")

        # ── Current session ────────────────────────────────────────────────
        c_op = card(inner)
        c_op.pack(fill="x", padx=20, pady=(0, 10))
        lbl(c_op, "Current session", FONT_BOLD, C["txt_primary"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        lbl(c_op,
            f"Operator : {self.journal.operateur}\n"
            f"Log      : {self.journal.chemin}",
            FONT_MONO, C["txt_secondary"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(0, 12))

        # ── Simulation mode ────────────────────────────────────────────────
        c_sim = card(inner)
        c_sim.pack(fill="x", padx=20, pady=(0, 10))
        lbl(c_sim, "Simulation mode", FONT_BOLD, C["txt_primary"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        lbl(c_sim,
            "COM ports not required — values are generated artificially.\n"
            "Must be enabled BEFORE the Excel session is created.\n"
            "Produced data are not metrologically valid.",
            FONT_SMALL, C["txt_muted"], C["bg_card"]).pack(anchor="w", padx=14, pady=(0, 8))
        row_sim = tk.Frame(c_sim, bg=C["bg_card"])
        row_sim.pack(anchor="w", padx=14, pady=(0, 12))
        self._btn_sim_toggle = btn(
            row_sim, "",
            command=self._basculer_simulation,
            padx=14, pady=6,
        )
        self._btn_sim_toggle.pack(side="left")
        b_open_sim = btn(row_sim, "Open simulation exports",
                         command=self._ouvrir_dossier_simulation,
                         color=C["bg_card"], fgcolor=C["txt_secondary"],
                         padx=12, pady=6)
        b_open_sim.configure(highlightbackground=C["border_light"], highlightthickness=1)
        b_open_sim.pack(side="left", padx=(8, 0))
        self._actualiser_btn_sim()

        # ── Audit log ──────────────────────────────────────────────────────
        c_aud = card(inner)
        c_aud.pack(fill="x", padx=20, pady=(0, 10))
        lbl(c_aud, "Audit log", FONT_BOLD, C["txt_primary"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        self._lbl_audit_result = lbl(
            c_aud, "Not verified", FONT_SMALL, C["txt_muted"], C["bg_card"])
        self._lbl_audit_result.pack(anchor="w", padx=14, pady=(0, 6))
        row_aud = tk.Frame(c_aud, bg=C["bg_card"])
        row_aud.pack(anchor="w", padx=14, pady=(0, 12))
        btn(row_aud, "Verify today's log",
            command=self._verifier_journal_audit,
            color=ACCENT_VIOLET, fgcolor="#ffffff",
            padx=12, pady=6).pack(side="left", padx=(0, 8))
        b_open_aud = btn(row_aud, "Open folder",
                         command=self._ouvrir_dossier_audit,
                         color=C["bg_card"], fgcolor=C["txt_secondary"],
                         padx=12, pady=6)
        b_open_aud.configure(highlightbackground=C["border_light"], highlightthickness=1)
        b_open_aud.pack(side="left")

        # ── Administrator key ──────────────────────────────────────────────
        c_key = card(inner)
        c_key.pack(fill="x", padx=20, pady=(0, 10))
        lbl(c_key, "Administrator key", FONT_BOLD, C["txt_primary"], C["bg_card"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        statut_cle = ("Key configured (PBKDF2-SHA256)." if admin_key_configured()
                      else "No key — dev password 'admin' active.")
        self._lbl_cle_statut = lbl(
            c_key, statut_cle, FONT_SMALL,
            C["txt_green"] if admin_key_configured() else C["txt_amber"],
            C["bg_card"],
        )
        self._lbl_cle_statut.pack(anchor="w", padx=14, pady=(0, 8))
        b_key = btn(c_key, "New key",
                    command=self._configurer_cle_admin,
                    color=C["bg_card"], fgcolor=C["txt_secondary"],
                    padx=12, pady=6)
        b_key.configure(highlightbackground=C["border_light"], highlightthickness=1)
        b_key.pack(anchor="w", padx=14, pady=(0, 12))

        # ── Lock ───────────────────────────────────────────────────────────
        btn(inner, "🔒  Lock admin session",
            command=self._verrouiller_admin,
            color=ACCENT_RED, fgcolor="#ffffff",
            padx=16, pady=9).pack(anchor="w", padx=20, pady=(10, 24))

        return f

    def _get_distance(self) -> float:
        try:
            return float(self.var_distance.get())
        except (ValueError, AttributeError):
            return 0.0

    def _verifier_ports_requis(self, *cibles: str) -> bool:
        """Bloque une mesure si un instrument requis n'est pas réellement connecté."""
        if self.gp.mode_simulation:
            return True
        manquants = []
        for cible in cibles:
            port = getattr(self.gp, cible, None)
            try:
                ouvert = bool(port is not None and port.is_open)
            except Exception:
                ouvert = False
            if not ouvert:
                manquants.append(cible.upper())

        if not manquants:
            return True

        noms = ", ".join(manquants)
        messagebox.showerror(
            "Instruments not connected",
            f"Connection required before measurement: {noms}.\n\n"
            "No simulated value will be used in production mode.",
        )
        self._log(f"Measurement blocked — instruments not connected: {noms}.", "err")
        return False

    def _badge(self, text, fg, bg) -> None:
        self.lbl_badge.configure(text=f"  {text}", fg=fg, bg=bg)
        self.badge_frame.configure(bg=bg, highlightbackground=fg)

    def _statut(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.lbl_statut.configure(text=f"  {ts}  {msg}")
        logger.info(msg)

    def _log(self, msg: str, niveau: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.txt_journal.configure(state="normal")
            self.txt_journal.insert("end", f"[{ts}]  ", "ts")
            self.txt_journal.insert("end", msg + "\n", niveau)
            self.txt_journal.see("end")
            self.txt_journal.configure(state="disabled")
        except Exception:
            pass
        logger.info(msg)

    def _exporter_xls(self) -> None:
        if self.export_xls:
            try:
                self.export_xls.fermer()
            except RuntimeError as exc:
                self._log(str(exc), "err")
                messagebox.showerror("Export error", str(exc))
                return
            self._log("Excel file saved.", "ok")
            messagebox.showinfo("Export", f"File saved:\n{self.export_xls.chemin_fichier}")
        else:
            messagebox.showinfo("Export", "No Excel file is open.")

    def _tick_horloge(self) -> None:
        now = datetime.now()
        self.var_date.set(now.strftime("%d/%m/%Y"))
        self.var_heure.set(now.strftime("%H:%M:%S"))
        self.after(1000, self._tick_horloge)

    def _quitter(self) -> None:
        if self._acq_en_cours:
            quitter = messagebox.askyesno(
                "Measurement in progress",
                "A measurement is running. Stop it and close the application?",
            )
            if not quitter:
                return
            if self._boucle_courante is not None:
                self._boucle_courante.demander_arret()
            elif self._acq_courante is not None:
                self._acq_courante.demander_arret()
            self.after(100, self._attendre_avant_quitter)
            return
        self._finaliser_quitter()

    def _attendre_avant_quitter(self) -> None:
        if self._acq_en_cours:
            self.after(100, self._attendre_avant_quitter)
            return
        self._finaliser_quitter()

    def _finaliser_quitter(self) -> None:
        self.journal.enregistrer(EV_ARRET, "Application fermée normalement")
        if self.export_xls:
            try:
                self.export_xls.fermer()
            except RuntimeError as exc:
                quitter = messagebox.askyesno(
                    "Save failed",
                    f"{exc}\n\nClose the application anyway?",
                )
                if not quitter:
                    return
        self._thermo.arreter()
        self.gp.fermer_tout()
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# Widgets utilitaires
# ══════════════════════════════════════════════════════════════════════════════

class _ScrollFrame(tk.Frame):
    """Frame avec scrollbar verticale."""
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg_app"], **kw)
        canvas = tk.Canvas(self, bg=C["bg_app"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=C["bg_app"])
        self.inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * e.delta / 120), "units"))


class _ScatterPlot(tk.Canvas):
    """Nuage de points auto-adaptatif pour les mesures COM1 et COM2."""

    MARGE_GAUCHE = 72
    MARGE_DROITE = 20
    MARGE_HAUT = 16
    MARGE_BAS = 58

    def __init__(self, parent, **kw):
        kw.setdefault("bg", C["bg_input"])
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", C["border_light"])
        super().__init__(parent, **kw)
        self._com1 = []
        self._com2 = []
        self.bind("<Configure>", lambda _event: self._dessiner())
        self.after_idle(self._dessiner)

    def ajouter_point(self, index: int, com1, com2) -> None:
        """Ajoute les valeurs valides du point index et redessine le graphique."""
        if com1 is not None:
            self._com1.append((index, float(com1)))
        if com2 is not None:
            self._com2.append((index, float(com2)))
        self._dessiner()

    def reinitialiser(self) -> None:
        self._com1 = []
        self._com2 = []
        self._dessiner()

    def _bornes_y(self):
        valeurs = [y for _, y in self._com1] + [y for _, y in self._com2]
        if not valeurs:
            return 0.0, 1.0
        minimum = min(valeurs)
        maximum = max(valeurs)
        amplitude = maximum - minimum
        marge = amplitude * 0.10 if amplitude > 0 else max(abs(maximum) * 0.05, 0.5)
        return minimum - marge, maximum + marge

    def _dessiner(self) -> None:
        self.delete("all")
        largeur = self.winfo_width()
        hauteur = self.winfo_height()
        if largeur < 160 or hauteur < 100:
            return

        x0 = self.MARGE_GAUCHE
        x1 = largeur - self.MARGE_DROITE
        y0 = self.MARGE_HAUT
        y1 = hauteur - self.MARGE_BAS
        min_y, max_y = self._bornes_y()

        for pas in range(5):
            ratio = pas / 4
            y = y1 - ratio * (y1 - y0)
            valeur = min_y + ratio * (max_y - min_y)
            self.create_line(x0, y, x1, y, fill=C["border"], width=1)
            self.create_text(x0 - 8, y, text=f"{valeur:.6g}", anchor="e",
                             fill=C["txt_muted"], font=FONT_SMALL)

        for index in (1, 5, 10, 15, 20, 25, 30):
            x = x0 + (index - 1) / 29 * (x1 - x0)
            self.create_line(x, y0, x, y1, fill=C["border"], width=1)
            self.create_text(x, y1 + 8, text=str(index), anchor="n",
                             fill=C["txt_muted"], font=FONT_SMALL)

        self.create_text((x0 + x1) / 2, hauteur - 6, text="Sample index N[i]",
                         anchor="s", fill=C["txt_secondary"], font=FONT_SMALL)

        def tracer(points, couleur):
            for index, valeur in points:
                x = x0 + (index - 1) / 29 * (x1 - x0)
                ratio = (valeur - min_y) / (max_y - min_y)
                y = y1 - ratio * (y1 - y0)
                rayon = 3
                self.create_oval(x - rayon, y - rayon, x + rayon, y + rayon,
                                 fill=couleur, outline="")

        tracer(self._com1, C["txt_blue"])
        tracer(self._com2, C["txt_amber"])


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ApplicationIPQ()
    app.mainloop()
