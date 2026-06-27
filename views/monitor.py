
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _MPL = True
except Exception:
    _MPL = False

from core.logger import creer_logger
from core.config import V_SEUIL_ALERTE
from models import stats

logger = creer_logger("phase6")

# ── Palette ───────────────────────────────────────────────────────────────────
_C = {
    "bg":      "#0f0f0f",
    "card":    "#161616",
    "hover":   "#1e1e1e",
    "active":  "#1d3a5c",
    "border":  "#222222",
    "muted":   "#475569",
    "second":  "#94a3b8",
    "primary": "#e2e8f0",
    "blue":    "#3b9ade",
    "green":   "#4ade80",
    "red":     "#f87171",
    "amber":   "#fbbf24",
    "init_bg": "#1a0d00",
    "init_fg": "#fb923c",
}
_F  = ("Segoe UI", 9)
_FB = ("Segoe UI", 9, "bold")
_FS = ("Segoe UI", 8)
_FM = ("Consolas", 8)

COLS = 3  # colonnes de la grille


def _bleu_serie(x: int, total: int) -> str:
    t = (x - 1) / max(total - 1, 1)
    return "#{:02x}{:02x}{:02x}".format(
        int(0x3b + t * (0x1d - 0x3b)),
        int(0x9a + t * (0x3a - 0x9a)),
        int(0xde + t * (0x5c - 0xde)),
    )


# ── Données d'une série ───────────────────────────────────────────────────────
class _SerieData:
    def __init__(self, sid, label: str, couleur: str) -> None:
        self.sid     = sid
        self.label   = label
        self.couleur = couleur
        self.vals:   List[Optional[float]] = []
        self.m:      Optional[float] = None
        self.v:      Optional[float] = None
        self.complete = False

    def ajouter(self, val: Optional[float]) -> None:
        self.vals.append(val)

    def reinit(self) -> None:
        self.vals = []
        self.m = None
        self.v = None
        self.complete = False

    def m_provisoire(self) -> Optional[float]:
        return stats.moyenne(self.vals)

    def alerte(self) -> bool:
        return self.complete and stats.alerte_variance(self.v, V_SEUIL_ALERTE)


# ── Mini-carte ────────────────────────────────────────────────────────────────
class _MiniCarte(tk.Frame):
    _H = 108

    def __init__(self, parent, data: _SerieData, on_click=None, **kw):
        is_init = isinstance(data.sid, str)
        bg = _C["init_bg"] if is_init else _C["card"]
        super().__init__(parent, bg=bg,
                         highlightbackground=_C["border"], highlightthickness=1,
                         cursor="hand2", **kw)
        self._data = data
        self._on_click = on_click

        fg_title = _C["init_fg"] if is_init else _C["second"]
        tk.Label(self, text=data.label, font=_FS, bg=bg,
                 fg=fg_title, anchor="w").pack(fill="x", padx=6, pady=(4, 0))

        if _MPL:
            self._init_mpl(bg)
        else:
            self._init_tk(bg)

        self._lbl_mv = tk.Label(self, text="", font=_FM, bg=bg,
                                fg=_C["second"], anchor="w")
        self._lbl_mv.pack(fill="x", padx=6, pady=(0, 4))

        for w in [self] + list(self.winfo_children()):
            w.bind("<Button-1>", self._click)
            if hasattr(w, "configure"):
                try:
                    w.configure(cursor="hand2")
                except tk.TclError:
                    pass

    def _init_mpl(self, bg: str) -> None:
        fig = Figure(figsize=(2.2, 1.1), dpi=80, facecolor="#0a0a0a")
        self._ax = fig.add_subplot(111)
        self._ax.set_facecolor("#0a0a0a")
        self._ax.tick_params(colors=_C["muted"], labelsize=6)
        for sp in self._ax.spines.values():
            sp.set_color(_C["border"])
        fig.subplots_adjust(left=0.18, right=0.97, top=0.93, bottom=0.24)
        self._cv_mpl = FigureCanvasTkAgg(fig, master=self)
        w = self._cv_mpl.get_tk_widget()
        w.configure(height=self._H)
        w.pack(fill="x", padx=4)
        w.bind("<Button-1>", self._click)

    def _init_tk(self, bg: str) -> None:
        self._cv_tk = tk.Canvas(self, bg="#0a0a0a", height=self._H,
                                highlightthickness=0)
        self._cv_tk.pack(fill="x", padx=4)
        self._cv_tk.bind("<Button-1>", self._click)
        self._cv_tk.bind("<Configure>", lambda _: self._dessiner_tk())

    def update_point(self) -> None:
        if _MPL:
            self._dessiner_mpl()
        else:
            self._dessiner_tk()

    def set_complete(self) -> None:
        m_s = f"{self._data.m:.6f}" if self._data.m is not None else "—"
        v_s = f"{self._data.v:.6f}" if self._data.v is not None else "—"
        fg  = _C["red"] if self._data.alerte() else _C["second"]
        self._lbl_mv.configure(text=f"M {m_s}   V {v_s}", fg=fg)
        self.update_point()

    def _dessiner_mpl(self) -> None:
        ax = self._ax
        ax.cla()
        ax.set_facecolor("#0a0a0a")
        ax.tick_params(colors=_C["muted"], labelsize=6)
        for sp in ax.spines.values():
            sp.set_color(_C["border"])
        vals = self._data.vals
        if vals:
            xs = list(range(1, len(vals) + 1))
            ys = [v if v is not None else float("nan") for v in vals]
            ax.scatter(xs, ys, color=self._data.couleur, s=10, zorder=3)
            if self._data.alerte() and self._data.m is not None:
                ax.axhline(self._data.m, color=_C["red"],
                           linestyle="--", linewidth=0.8, zorder=4)
        self._cv_mpl.draw_idle()

    def _dessiner_tk(self) -> None:
        c = self._cv_tk
        c.delete("all")
        W = c.winfo_width() or 160
        H = self._H
        x0, x1, y0, y1 = 12, W - 4, 4, H - 4
        valides = [(i + 1, v) for i, v in enumerate(self._data.vals) if v is not None]
        if not valides:
            return
        ys_v = [v for _, v in valides]
        lo, hi = min(ys_v), max(ys_v)
        amp = hi - lo or max(abs(hi) * 0.05, 1e-9)
        lo -= amp * 0.1; hi += amp * 0.1
        dy = hi - lo

        def px(i): return x0 + (i - 1) / 29 * (x1 - x0)
        def py(v): return y1 - (v - lo) / dy * (y1 - y0)

        for xi, v in valides:
            x, y = px(xi), py(v)
            c.create_oval(x - 2, y - 2, x + 2, y + 2,
                          fill=self._data.couleur, outline="")
        if self._data.alerte():
            mp = self._data.m_provisoire()
            if mp is not None:
                yp = py(mp)
                c.create_line(x0, yp, x1, yp, fill=_C["red"], dash=(4, 2))

    def _click(self, _event=None) -> None:
        if self._on_click:
            self._on_click(self._data.sid)


# ── Vue Grille ────────────────────────────────────────────────────────────────
class _VueGrille(tk.Frame):
    def __init__(self, parent, on_carte_click, **kw):
        super().__init__(parent, bg=_C["bg"], **kw)
        self._on_click = on_carte_click
        self._cartes: Dict[object, _MiniCarte] = {}

        cv = tk.Canvas(self, bg=_C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=cv.yview)
        self._inner = tk.Frame(cv, bg=_C["bg"])
        win = cv.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        cv.bind_all("<MouseWheel>",
                    lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

    def ajouter_carte(self, data: _SerieData) -> _MiniCarte:
        carte = _MiniCarte(self._inner, data, on_click=self._on_click)
        self._cartes[data.sid] = carte
        self._placer()
        return carte

    def get_carte(self, sid) -> Optional[_MiniCarte]:
        return self._cartes.get(sid)

    def reset(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        self._cartes.clear()

    def _placer(self) -> None:
        for w in self._inner.winfo_children():
            w.grid_forget()
        for idx, carte in enumerate(self._cartes.values()):
            carte.grid(row=idx // COLS, column=idx % COLS,
                       padx=6, pady=6, sticky="nsew")
        for c in range(COLS):
            self._inner.grid_columnconfigure(c, weight=1)


# ── Vue Agrandie (plein espace central) ───────────────────────────────────────
class _VueAgrandie(tk.Frame):
    """Graphique plein écran d'une série, ouvert par clic sur mini-carte."""

    def __init__(self, parent, data: _SerieData, on_retour, **kw):
        super().__init__(parent, bg=_C["bg"], **kw)
        self._data = data

        # En-tête
        hdr = tk.Frame(self, bg=_C["card"],
                       highlightbackground=_C["border"], highlightthickness=1)
        hdr.pack(fill="x", padx=4, pady=(4, 0))

        tk.Button(hdr, text="← Back to grid", font=_F,
                  bg=_C["active"], fg=_C["blue"],
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=on_retour).pack(side="left", padx=8, pady=6)

        tk.Label(hdr, text=data.label, font=_FB,
                 bg=_C["card"], fg=_C["primary"]).pack(side="left", padx=8)

        self._lbl_mv = tk.Label(hdr, text="", font=_FM,
                                bg=_C["card"], fg=_C["second"])
        self._lbl_mv.pack(side="right", padx=16)

        # Zone graphique
        zone = tk.Frame(self, bg="#0a0a0a")
        zone.pack(fill="both", expand=True, padx=4, pady=4)

        if _MPL:
            fig = Figure(facecolor="#0a0a0a")
            self._ax = fig.add_subplot(111)
            self._ax.set_facecolor("#0a0a0a")
            self._ax.tick_params(colors=_C["muted"])
            for sp in self._ax.spines.values():
                sp.set_color(_C["border"])
            fig.subplots_adjust(left=0.09, right=0.97, top=0.95, bottom=0.10)
            self._cv = FigureCanvasTkAgg(fig, master=zone)
            self._cv.get_tk_widget().pack(fill="both", expand=True)
        else:
            self._cv_tk = tk.Canvas(zone, bg="#0a0a0a", highlightthickness=0)
            self._cv_tk.pack(fill="both", expand=True)
            self._cv_tk.bind("<Configure>", lambda _: self._dessiner_tk())

        self.rafraichir()

    def rafraichir(self) -> None:
        if _MPL:
            self._dessiner_mpl()
        else:
            self._dessiner_tk()
        # Mise à jour de l'étiquette M/V
        d = self._data
        m_s = f"{d.m:.6f}" if d.m is not None else (
              f"{d.m_provisoire():.6f} (in progress)" if d.m_provisoire() is not None else "—")
        v_s = f"  V = {d.v:.6f}" if d.v is not None else ""
        fg = _C["red"] if d.alerte() else _C["second"]
        self._lbl_mv.configure(text=f"M = {m_s}{v_s}", fg=fg)

    def _dessiner_mpl(self) -> None:
        ax = self._ax
        ax.cla()
        ax.set_facecolor("#0a0a0a")
        ax.tick_params(colors=_C["muted"])
        for sp in ax.spines.values():
            sp.set_color(_C["border"])
        vals = self._data.vals
        if vals:
            xs = list(range(1, len(vals) + 1))
            ys = [v if v is not None else float("nan") for v in vals]
            ax.scatter(xs, ys, color=self._data.couleur, s=30, zorder=3,
                       label=self._data.label)
            m_ref = self._data.m if self._data.m is not None else self._data.m_provisoire()
            if m_ref is not None:
                lbl = f"M = {m_ref:.6f}"
                col = _C["red"] if self._data.alerte() else _C["second"]
                ax.axhline(m_ref, color=col, linestyle="--",
                           linewidth=1.2, label=lbl, zorder=2)
        ax.set_xlabel("Point N[i]", color=_C["muted"], fontsize=9)
        ax.set_ylabel("Value", color=_C["muted"], fontsize=9)
        ax.legend(fontsize=9, facecolor=_C["card"],
                  labelcolor=_C["second"], edgecolor=_C["border"])
        self._cv.draw_idle()

    def _dessiner_tk(self) -> None:
        c = self._cv_tk
        c.delete("all")
        W = c.winfo_width() or 400
        H = c.winfo_height() or 300
        x0, x1, y0, y1 = 40, W - 10, 10, H - 30
        valides = [(i + 1, v) for i, v in enumerate(self._data.vals) if v is not None]
        if not valides:
            c.create_text(W // 2, H // 2, text="No data",
                          fill=_C["muted"], font=_F)
            return
        ys_v = [v for _, v in valides]
        lo, hi = min(ys_v), max(ys_v)
        amp = hi - lo or max(abs(hi) * 0.05, 1e-9)
        lo -= amp * 0.15; hi += amp * 0.15
        dy = hi - lo

        def px(i): return x0 + (i - 1) / 29 * (x1 - x0)
        def py(v): return y1 - (v - lo) / dy * (y1 - y0)

        for xi, v in valides:
            x, y = px(xi), py(v)
            c.create_oval(x - 4, y - 4, x + 4, y + 4,
                          fill=self._data.couleur, outline="")
        mp = self._data.m if self._data.m is not None else self._data.m_provisoire()
        if mp is not None:
            yp = py(mp)
            col = _C["red"] if self._data.alerte() else _C["second"]
            c.create_line(x0, yp, x1, yp, fill=col, dash=(6, 3), width=1.5)


# ── Vue Nuage ─────────────────────────────────────────────────────────────────
class _VueNuage(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=_C["bg"], **kw)
        self._series:   Dict[object, _SerieData] = {}
        self._visibles: Dict[object, tk.BooleanVar] = {}

        if _MPL:
            fig = Figure(figsize=(5, 3.5), facecolor="#0a0a0a")
            self._ax = fig.add_subplot(111)
            self._ax.set_facecolor("#0a0a0a")
            self._ax.tick_params(colors=_C["muted"])
            for sp in self._ax.spines.values():
                sp.set_color(_C["border"])
            self._cv = FigureCanvasTkAgg(fig, master=self)
            self._cv.get_tk_widget().pack(fill="both", expand=True)
        else:
            tk.Label(self, text="matplotlib required for the cloud view.",
                     bg=_C["bg"], fg=_C["muted"], font=_F).pack(pady=30)

        self._frame_cb = tk.Frame(self, bg="#141414")
        self._frame_cb.pack(side="bottom", fill="x", padx=8, pady=4)

    def ajouter_serie(self, data: _SerieData) -> None:
        self._series[data.sid] = data
        var = tk.BooleanVar(value=True)
        self._visibles[data.sid] = var
        tk.Checkbutton(
            self._frame_cb, text=data.label, variable=var,
            command=self.redessiner,
            bg="#141414", fg=data.couleur,
            selectcolor="#141414", activebackground="#141414", font=_FS,
        ).pack(side="left", padx=4)

    def redessiner(self) -> None:
        if not _MPL:
            return
        ax = self._ax
        ax.cla()
        ax.set_facecolor("#0a0a0a")
        ax.tick_params(colors=_C["muted"])
        for sp in ax.spines.values():
            sp.set_color(_C["border"])

        all_vals: List[float] = []
        for sid, data in self._series.items():
            if not self._visibles.get(sid, tk.BooleanVar(value=True)).get():
                continue
            valides = [v for v in data.vals if v is not None]
            if not valides:
                continue
            xs = list(range(1, len(data.vals) + 1))
            ys = [v if v is not None else float("nan") for v in data.vals]
            ax.scatter(xs, ys, color=data.couleur, s=12, label=data.label, zorder=3)
            all_vals.extend(valides)

        res = stats.moyenne_sigma(all_vals)
        if res is not None:
            m_g, sigma = res
            ax.axhline(m_g, color=_C["second"], linestyle="--",
                       linewidth=1, label=f"M={m_g:.4f}")
            ax.axhspan(m_g - 2 * sigma, m_g + 2 * sigma,
                       alpha=0.08, color=_C["second"])

        ax.set_xlabel("N[i]", color=_C["muted"], fontsize=8)
        ax.set_ylabel("Value", color=_C["muted"], fontsize=8)
        if len(self._series) <= 10:
            ax.legend(fontsize=6, facecolor=_C["card"],
                      labelcolor=_C["second"], edgecolor=_C["border"])
        self._cv.draw_idle()

    def reset(self) -> None:
        self._series.clear()
        self._visibles.clear()
        for w in self._frame_cb.winfo_children():
            w.destroy()
        if _MPL:
            self._ax.cla()
            self._cv.draw_idle()


# ── Bandeau latéral stats ─────────────────────────────────────────────────────
class _Sidebar(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=_C["card"],
                         highlightbackground=_C["border"], highlightthickness=1, **kw)
        self._var_com = tk.StringVar(value="—")
        self._var_pt  = tk.StringVar(value="— / 30")
        self._var_t   = tk.StringVar(value="— °C")
        self._var_hr  = tk.StringVar(value="— %")
        self._var_m   = tk.StringVar(value="—")
        self._build()

    def _build(self) -> None:
        for w in self.winfo_children():
            w.destroy()

        def row(lbl: str, var: tk.StringVar) -> None:
            f = tk.Frame(self, bg=_C["card"])
            f.pack(fill="x", padx=10, pady=3)
            tk.Label(f, text=lbl, font=_FS, bg=_C["card"],
                     fg=_C["muted"], anchor="w").pack(fill="x")
            tk.Label(f, textvariable=var, font=_FB, bg=_C["card"],
                     fg=_C["primary"], anchor="w").pack(fill="x")

        tk.Label(self, text="LIVE MONITOR", font=_FB,
                 bg=_C["card"], fg=_C["blue"]).pack(padx=10, pady=(12, 8), anchor="w")
        tk.Frame(self, height=1, bg=_C["border"]).pack(fill="x", padx=8)
        row("Active COM",    self._var_com)
        row("Point i",       self._var_pt)
        row("Temperature",   self._var_t)
        row("Humidity",      self._var_hr)
        row("Provisional M", self._var_m)

        tk.Label(self, text="Click a card\nto enlarge it",
                 font=_FS, bg=_C["card"], fg=_C["muted"],
                 justify="center").pack(pady=20)

    def update_stats(self, com: str, i: int, t: float, hr: float,
                     m_prov: Optional[float]) -> None:
        self._var_com.set(com.upper())
        self._var_pt.set(f"{i} / 30")
        self._var_t.set(f"{t:.1f} °C")
        self._var_hr.set(f"{hr:.1f} %")
        self._var_m.set(f"{m_prov:.6f}" if m_prov is not None else "—")


# ── Onglet principal ──────────────────────────────────────────────────────────
class MonitorTab(tk.Frame):

    def __init__(self, parent, **kw):
        kw.setdefault("bg", _C["bg"])
        super().__init__(parent, **kw)
        self._series:    Dict[object, _SerieData] = {}
        self._nb_series  = 0
        self._com_actif  = tk.StringVar(value="com1")
        self._agrandie:  Optional[_VueAgrandie] = None
        self._construire()

    # ── Construction ─────────────────────────────────────────────────────────
    def _construire(self) -> None:
        self._build_header()

        body = tk.Frame(self, bg=_C["bg"])
        body.pack(fill="both", expand=True)

        self._sidebar = _Sidebar(body, width=190)
        self._sidebar.pack(side="right", fill="y")
        self._sidebar.pack_propagate(False)

        self._zone = tk.Frame(body, bg=_C["bg"])
        self._zone.pack(side="left", fill="both", expand=True)

        self._grille = _VueGrille(self._zone, on_carte_click=self._ouvrir_agrandie)
        self._nuage  = _VueNuage(self._zone)
        self._grille.pack(fill="both", expand=True)

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg="#141414",
                       highlightbackground=_C["border"], highlightthickness=1)
        hdr.pack(fill="x")

        tk.Label(hdr, text="Instrument monitor", font=_FB,
                 bg="#141414", fg=_C["primary"]).pack(side="left", padx=(14, 10), pady=8)

        # Indicateur du COM mesuré (choisi sur la page Measurement, lecture seule ici)
        self._lbl_com = tk.Label(hdr, text="Measuring: COM 1", font=_F,
                                 bg="#141414", fg=_C["blue"])
        self._lbl_com.pack(side="left", padx=4, pady=8)

        self._btn_toggle = tk.Button(
            hdr, text="☁  Cloud view", font=_FS,
            bg=_C["active"], fg=_C["blue"],
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2", command=self._toggle_vue,
        )
        self._btn_toggle.pack(side="right", padx=14, pady=6)

    # ── Navigation ───────────────────────────────────────────────────────────
    def _toggle_vue(self) -> None:
        self._fermer_agrandie(repack=False)
        if self._grille.winfo_ismapped():
            self._grille.pack_forget()
            self._nuage.pack(fill="both", expand=True)
            self._btn_toggle.configure(text="Grid view")
            self._nuage.redessiner()
        else:
            self._nuage.pack_forget()
            self._grille.pack(fill="both", expand=True)
            self._btn_toggle.configure(text="Cloud view")

    def _ouvrir_agrandie(self, sid) -> None:
        data = self._series.get(sid)
        if not data:
            return
        # Masquer grille / nuage
        self._grille.pack_forget()
        self._nuage.pack_forget()
        # Détruire ancienne vue agrandie
        if self._agrandie is not None:
            self._agrandie.destroy()
            self._agrandie = None
        # Créer nouvelle vue agrandie
        self._agrandie = _VueAgrandie(
            self._zone, data, on_retour=self._fermer_agrandie)
        self._agrandie.pack(fill="both", expand=True)

    def _fermer_agrandie(self, repack: bool = True) -> None:
        if self._agrandie is not None:
            self._agrandie.destroy()
            self._agrandie = None
        if repack:
            self._grille.pack(fill="both", expand=True)
            self._btn_toggle.configure(text="Cloud view")

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _get_or_create(self, sid, label: str, couleur: str) -> _SerieData:
        if sid not in self._series:
            data = _SerieData(sid, label, couleur)
            self._series[sid] = data
            self._grille.ajouter_carte(data)
            self._nuage.ajouter_serie(data)
        return self._series[sid]

    def _refresh_agrandie_if(self, sid) -> None:
        """Met à jour la vue agrandie si elle affiche cette série."""
        if (self._agrandie is not None
                and self._agrandie._data.sid == sid):
            self._agrandie.rafraichir()

    # ── API publique ──────────────────────────────────────────────────────────
    def set_nb_series(self, nb: int) -> None:
        self._nb_series = nb

    def on_init_point(self, cible: str, i: int,
                      val: Optional[float], t: float, hr: float) -> None:
        sid  = f"init_{cible}"
        data = self._get_or_create(sid, f"Init {cible.upper()}", _C["init_fg"])
        if i == 1:
            data.reinit()
        data.ajouter(val)
        carte = self._grille.get_carte(sid)
        if carte:
            carte.update_point()
        self._refresh_agrandie_if(sid)
        self._sidebar.update_stats(cible, i, t, hr, data.m_provisoire())

    def on_init_complete(self, cible: str,
                         m: Optional[float], v: Optional[float]) -> None:
        sid  = f"init_{cible}"
        data = self._series.get(sid)
        if data:
            data.m = m
            data.v = v
            data.complete = True
            carte = self._grille.get_carte(sid)
            if carte:
                carte.set_complete()
            self._refresh_agrandie_if(sid)
            self._nuage.redessiner()

    def on_serie_point(self, x: int, i: int,
                       val: Optional[float], t: float, hr: float) -> None:
        couleur = _bleu_serie(x, max(self._nb_series, 1))
        data    = self._get_or_create(x, f"Série {x}", couleur)
        if i == 1:
            data.reinit()
        data.ajouter(val)
        carte = self._grille.get_carte(x)
        if carte:
            carte.update_point()
        self._refresh_agrandie_if(x)
        self._sidebar.update_stats(self._com_actif.get(), i, t, hr,
                                   data.m_provisoire())

    def on_serie_complete(self, x: int, m: float, v: float) -> None:
        data = self._series.get(x)
        if data:
            data.m = m
            data.v = v
            data.complete = True
            carte = self._grille.get_carte(x)
            if carte:
                carte.set_complete()
            self._refresh_agrandie_if(x)
            self._nuage.redessiner()

    def set_com_actif(self, com: str) -> None:
        """Indique quel COM est mesuré (choisi sur la page Measurement)."""
        self._com_actif.set(com)
        if hasattr(self, "_lbl_com"):
            self._lbl_com.configure(text=f"Measuring: COM {com[-1]}")

    def reset(self) -> None:
        self._fermer_agrandie(repack=False)
        self._series.clear()
        self._grille.reset()
        self._nuage.reset()
        self._grille.pack(fill="both", expand=True)
        self._btn_toggle.configure(text="Cloud view")
