# -*- coding: utf-8 -*-
"""views/monitor.py — Live monitor (vue temps réel).

Disposition : liste scrollable des runs (gauche) + grand graphe détaillé de la
série sélectionnée (centre) + bande readout horizontale (dessous). Bouton
« Cloud view » sélectionnable = superposition de toutes les séries avec cases à
cocher et auto-échelle Y. Charte claire. API publique inchangée (appelée par les
contrôleurs)."""
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

# ── Palette claire ──────────────────────────────────────────────────────────────
_C = {
    "bg":      "#D8D7D3",
    "card":    "#FFFFFF",
    "panel":   "#EFEEEA",
    "header":  "#F4F3F0",
    "hover":   "#F2F1ED",
    "sel":     "#EFE7FB",
    "border":  "#DDDBD4",
    "muted":   "#8A8D86",
    "second":  "#5F6168",
    "primary": "#24272C",
    "blue":    "#2563EB",
    "violet":  "#7C4DDB",
    "green":   "#2E7D4F",
    "red":     "#C0392B",
    "amber":   "#B7791F",
    "init_fg": "#7C4DDB",
    "grid":    "#ECECEC",
    "plot_bg": "#FCFCFB",
}
_F  = ("Segoe UI", 9)
_FB = ("Segoe UI", 9, "bold")
_FS = ("Segoe UI", 8)
_FM = ("Consolas", 9)


def _bleu_serie(x: int, total: int) -> str:
    """Dégradé de bleus pour distinguer les séries (lisible sur fond clair)."""
    t = (x - 1) / max(total - 1, 1)
    return "#{:02x}{:02x}{:02x}".format(
        int(0x25 + t * (0x1d - 0x25)),
        int(0x63 + t * (0x3a - 0x63)),
        int(0xeb + t * (0x8c - 0xeb)),
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


# ── Graphe détaillé d'une série ────────────────────────────────────────────────
class _DetailChart(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault("bg", _C["card"])
        super().__init__(parent, highlightbackground=_C["border"],
                         highlightthickness=1, **kw)
        self._titre = tk.Label(self, text="No run selected", font=_FB,
                               bg=_C["card"], fg=_C["primary"], anchor="w")
        self._titre.pack(fill="x", padx=12, pady=(10, 0))
        if _MPL:
            fig = Figure(figsize=(5, 3), dpi=90, facecolor=_C["card"])
            self._ax = fig.add_subplot(111)
            fig.subplots_adjust(left=0.11, right=0.97, top=0.95, bottom=0.13)
            self._cv = FigureCanvasTkAgg(fig, master=self)
            self._cv.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        else:
            self._cv_tk = tk.Canvas(self, bg=_C["plot_bg"], highlightthickness=1,
                                    highlightbackground=_C["border"])
            self._cv_tk.pack(fill="both", expand=True, padx=8, pady=8)
            self._data: Optional[_SerieData] = None
            self._cv_tk.bind("<Configure>", lambda _e: self._dessiner_tk())

    def afficher(self, data: Optional[_SerieData]) -> None:
        if data is None:
            self._titre.configure(text="No run selected")
            return
        self._titre.configure(text=data.label)
        if _MPL:
            self._dessiner_mpl(data)
        else:
            self._data = data
            self._dessiner_tk()

    def _style_ax(self) -> None:
        ax = self._ax
        ax.set_facecolor(_C["plot_bg"])
        ax.tick_params(colors=_C["muted"], labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(_C["border"])
        ax.grid(True, color=_C["grid"], linewidth=0.8)

    def _dessiner_mpl(self, data: _SerieData) -> None:
        ax = self._ax
        ax.cla()
        self._style_ax()
        valides = [(i + 1, v) for i, v in enumerate(data.vals) if v is not None]
        if valides:
            xs = [i for i, _ in valides]
            ys = [v for _, v in valides]
            ax.scatter(xs, ys, color=data.couleur, s=24, zorder=3)
            res = stats.moyenne_sigma(ys)
            if res is not None:
                m, sigma = res
                ax.axhline(m, color=_C["violet"], linestyle="--", linewidth=1.2,
                           label=f"M = {m:.5f}", zorder=2)
                if sigma > 0:
                    ax.axhspan(m - sigma, m + sigma, color=_C["violet"], alpha=0.10)
            # Dernier point mis en évidence
            ax.scatter([xs[-1]], [ys[-1]], s=70, facecolor=data.couleur,
                       edgecolor="white", linewidths=1.5, zorder=4)
            ax.legend(fontsize=8, facecolor=_C["card"],
                      labelcolor=_C["second"], edgecolor=_C["border"])
        ax.set_xlim(0.5, 30.5)
        ax.set_xlabel("Sample index N[i]", color=_C["second"], fontsize=9)
        ax.set_ylabel("Value", color=_C["second"], fontsize=9)
        self._cv.draw_idle()

    def _dessiner_tk(self) -> None:
        c = self._cv_tk
        c.delete("all")
        data = getattr(self, "_data", None)
        if data is None:
            return
        W = c.winfo_width() or 500
        H = c.winfo_height() or 300
        x0, x1, y0, y1 = 56, W - 14, 14, H - 30
        valides = [(i + 1, v) for i, v in enumerate(data.vals) if v is not None]
        if not valides:
            c.create_text(W // 2, H // 2, text="No data",
                          fill=_C["muted"], font=_F)
            return
        ys_v = [v for _, v in valides]
        lo, hi = min(ys_v), max(ys_v)
        amp = hi - lo or max(abs(hi) * 0.05, 1e-9)
        lo -= amp * 0.12
        hi += amp * 0.12
        dy = hi - lo

        def px(i): return x0 + (i - 1) / 29 * (x1 - x0)
        def py(v): return y1 - (v - lo) / dy * (y1 - y0)

        for frac in range(5):
            yy = y1 - frac / 4 * (y1 - y0)
            c.create_line(x0, yy, x1, yy, fill=_C["grid"])
            c.create_text(x0 - 6, yy, anchor="e", fill=_C["muted"], font=_FS,
                          text=f"{lo + frac / 4 * dy:.5f}")
        res = stats.moyenne_sigma(ys_v)
        if res is not None:
            m, sigma = res
            if sigma > 0:
                c.create_rectangle(x0, py(m + sigma), x1, py(m - sigma),
                                   fill="#efe7fb", outline="")
            c.create_line(x0, py(m), x1, py(m), fill=_C["violet"], dash=(5, 4))
        for xi, v in valides:
            x, y = px(xi), py(v)
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=data.couleur, outline="")
        lx, lv = valides[-1]
        x, y = px(lx), py(lv)
        c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=data.couleur, outline="white", width=2)
        c.create_text((x0 + x1) / 2, H - 6, anchor="s", fill=_C["second"],
                      font=_FS, text="Sample index N[i]")


# ── Bande readout horizontale ──────────────────────────────────────────────────
class _ReadoutStrip(tk.Frame):
    CHAMPS = [("Active COM", "com"), ("Series", "serie"), ("Point i", "pt"),
              ("Temp.", "t"), ("Humidity", "hr"), ("Prov. M", "m"), ("Prov. V", "v")]

    def __init__(self, parent, **kw):
        kw.setdefault("bg", _C["card"])
        super().__init__(parent, highlightbackground=_C["border"],
                         highlightthickness=1, **kw)
        self._vars: Dict[str, tk.StringVar] = {}
        for i, (titre, cle) in enumerate(self.CHAMPS):
            cell = tk.Frame(self, bg=_C["card"])
            cell.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=6)
            self.grid_columnconfigure(i, weight=1, uniform="ro")
            tk.Label(cell, text=titre.upper(), font=("Segoe UI", 8), bg=_C["card"],
                     fg=_C["muted"]).pack(anchor="w", padx=12)
            var = tk.StringVar(value="—")
            self._vars[cle] = var
            tk.Label(cell, textvariable=var, font=_FM, bg=_C["card"],
                     fg=_C["primary"]).pack(anchor="w", padx=12)
            if i < len(self.CHAMPS) - 1:
                tk.Frame(self, bg=_C["border"], width=1).grid(
                    row=0, column=i, sticky="nse", pady=8)

    def update_stats(self, com: str, serie: str, i: int, t: float, hr: float,
                     m_prov: Optional[float], v_prov: Optional[float]) -> None:
        self._vars["com"].set(f"COM {com[-1]}" if com else "—")
        self._vars["serie"].set(serie)
        self._vars["pt"].set(f"{i} / 30")
        self._vars["t"].set(f"{t:.1f} °C")
        self._vars["hr"].set(f"{hr:.1f} %")
        self._vars["m"].set(f"{m_prov:.5f}" if m_prov is not None else "—")
        self._vars["v"].set(f"{v_prov:.6f}" if v_prov is not None else "—")


# ── Vue Nuage (superposition + cases à cocher + auto-échelle) ───────────────────
class _VueNuage(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=_C["card"],
                         highlightbackground=_C["border"], highlightthickness=1, **kw)
        self._series:   Dict[object, _SerieData] = {}
        self._visibles: Dict[object, tk.BooleanVar] = {}

        if _MPL:
            fig = Figure(figsize=(5, 3.2), dpi=90, facecolor=_C["card"])
            self._ax = fig.add_subplot(111)
            fig.subplots_adjust(left=0.11, right=0.97, top=0.95, bottom=0.13)
            self._cv = FigureCanvasTkAgg(fig, master=self)
            self._cv.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        else:
            tk.Label(self, text="matplotlib required for the cloud view.",
                     bg=_C["card"], fg=_C["muted"], font=_F).pack(pady=30)

        self._frame_cb = tk.Frame(self, bg=_C["panel"])
        self._frame_cb.pack(side="bottom", fill="x", padx=8, pady=(0, 8))

    def ajouter_serie(self, data: _SerieData) -> None:
        self._series[data.sid] = data
        var = tk.BooleanVar(value=True)
        self._visibles[data.sid] = var
        tk.Checkbutton(
            self._frame_cb, text=data.label, variable=var,
            command=self.redessiner,
            bg=_C["panel"], fg=data.couleur, selectcolor=_C["card"],
            activebackground=_C["panel"], activeforeground=data.couleur, font=_FS,
        ).pack(side="left", padx=4, pady=2)

    def redessiner(self) -> None:
        if not _MPL:
            return
        ax = self._ax
        ax.cla()
        ax.set_facecolor(_C["plot_bg"])
        ax.tick_params(colors=_C["muted"], labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(_C["border"])
        ax.grid(True, color=_C["grid"], linewidth=0.8)

        all_vals: List[float] = []
        for sid, data in self._series.items():
            if not self._visibles.get(sid, tk.BooleanVar(value=True)).get():
                continue
            valides = [v for v in data.vals if v is not None]
            if not valides:
                continue
            xs = list(range(1, len(data.vals) + 1))
            ys = [v if v is not None else float("nan") for v in data.vals]
            ax.scatter(xs, ys, color=data.couleur, s=14, label=data.label, zorder=3)
            all_vals.extend(valides)

        res = stats.moyenne_sigma(all_vals)
        if res is not None:
            m_g, sigma = res
            ax.axhline(m_g, color=_C["violet"], linestyle="--",
                       linewidth=1, label=f"M = {m_g:.5f}")
            if sigma > 0:
                ax.axhspan(m_g - 2 * sigma, m_g + 2 * sigma,
                           alpha=0.08, color=_C["violet"])
        # Auto-échelle Y : matplotlib ajuste aux données visibles (Δ min/max + marge).
        ax.set_xlim(0.5, 30.5)
        ax.set_xlabel("Sample index N[i]", color=_C["second"], fontsize=9)
        ax.set_ylabel("Value", color=_C["second"], fontsize=9)
        if 0 < len(all_vals) and len(self._series) <= 12:
            ax.legend(fontsize=7, facecolor=_C["card"],
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


# ── Onglet principal ──────────────────────────────────────────────────────────
class MonitorTab(tk.Frame):

    def __init__(self, parent, **kw):
        kw.setdefault("bg", _C["bg"])
        super().__init__(parent, **kw)
        self._series:   Dict[object, _SerieData] = {}
        self._order:    List[object] = []
        self._selected: Optional[object] = None
        self._follow_live = True
        self._nb_series = 0
        self._com_actif = tk.StringVar(value="com1")
        self._construire()

    # ── Construction ─────────────────────────────────────────────────────────
    def _construire(self) -> None:
        self._build_header()

        body = tk.Frame(self, bg=_C["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=12)

        # Liste des runs (gauche)
        liste = tk.Frame(body, bg=_C["card"], width=170,
                         highlightbackground=_C["border"], highlightthickness=1)
        liste.pack(side="left", fill="y")
        liste.pack_propagate(False)
        tk.Label(liste, text="RUNS", font=_FB, bg=_C["card"], fg=_C["muted"],
                 anchor="w").pack(fill="x", padx=12, pady=(10, 6))
        lb_wrap = tk.Frame(liste, bg=_C["card"])
        lb_wrap.pack(fill="both", expand=True, padx=2, pady=(0, 4))
        self._listbox = tk.Listbox(
            lb_wrap, bg=_C["card"], fg=_C["primary"], font=_FM,
            relief="flat", bd=0, highlightthickness=0, activestyle="none",
            selectbackground=_C["sel"], selectforeground=_C["violet"],
            exportselection=False,
        )
        sb = ttk.Scrollbar(lb_wrap, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        # Zone droite : détail (graphe + readout) / nuage
        self._zone = tk.Frame(body, bg=_C["bg"])
        self._zone.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._detail = tk.Frame(self._zone, bg=_C["bg"])
        self._chart = _DetailChart(self._detail)
        self._chart.pack(fill="both", expand=True)
        self._readout = _ReadoutStrip(self._detail)
        self._readout.pack(fill="x", pady=(12, 0))
        self._detail.pack(fill="both", expand=True)

        self._nuage = _VueNuage(self._zone)

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_C["header"],
                       highlightbackground=_C["border"], highlightthickness=1)
        hdr.pack(fill="x")

        tk.Label(hdr, text="Instrument monitor", font=_FB,
                 bg=_C["header"], fg=_C["primary"]).pack(side="left", padx=(14, 10), pady=9)
        self._lbl_com = tk.Label(hdr, text="Measuring: COM 1", font=_FM,
                                 bg=_C["header"], fg=_C["second"])
        self._lbl_com.pack(side="left", padx=4, pady=9)

        self._btn_toggle = tk.Button(
            hdr, text="☁  Cloud view", font=_FS,
            bg=_C["card"], fg=_C["second"],
            activebackground=_C["hover"], activeforeground=_C["primary"],
            relief="flat", bd=0, padx=12, pady=5,
            highlightbackground=_C["border"], highlightthickness=1,
            cursor="hand2", command=self._toggle_vue,
        )
        self._btn_toggle.pack(side="right", padx=14, pady=6)

    # ── Navigation ───────────────────────────────────────────────────────────
    def _toggle_vue(self) -> None:
        if self._nuage.winfo_ismapped():
            self._nuage.pack_forget()
            self._detail.pack(fill="both", expand=True)
            self._btn_toggle.configure(text="☁  Cloud view", bg=_C["card"],
                                       fg=_C["second"], highlightthickness=1)
        else:
            self._detail.pack_forget()
            self._nuage.pack(fill="both", expand=True)
            self._btn_toggle.configure(text="▦  Grid view", bg=_C["violet"],
                                       fg="#ffffff", highlightthickness=0)
            self._nuage.redessiner()

    def _on_select(self, _event=None) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self._order):
            self._follow_live = False
            self._selected = self._order[idx]
            self._chart.afficher(self._series.get(self._selected))

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _row_text(self, data: _SerieData) -> str:
        return f" {data.label}"

    def _get_or_create(self, sid, label: str, couleur: str) -> _SerieData:
        if sid not in self._series:
            data = _SerieData(sid, label, couleur)
            self._series[sid] = data
            self._order.append(sid)
            self._listbox.insert("end", self._row_text(data))
            self._listbox.itemconfig(len(self._order) - 1, foreground=couleur)
            self._nuage.ajouter_serie(data)
        return self._series[sid]

    def _maj_ligne(self, sid) -> None:
        if sid not in self._order:
            return
        idx = self._order.index(sid)
        data = self._series[sid]
        suffixe = ""
        if data.complete and data.m is not None:
            suffixe = f"   M={data.m:.5f}"
        elif not data.complete and data.vals:
            suffixe = "   live"
        self._listbox.delete(idx)
        self._listbox.insert(idx, self._row_text(data) + suffixe)
        fg = _C["red"] if data.alerte() else data.couleur
        self._listbox.itemconfig(idx, foreground=fg)

    def _suivre(self, sid) -> None:
        """Affiche la série sid si on suit le live ou si elle est déjà sélectionnée."""
        if self._follow_live:
            self._selected = sid
            idx = self._order.index(sid)
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
            self._chart.afficher(self._series.get(sid))
        elif sid == self._selected:
            self._chart.afficher(self._series.get(sid))

    # ── API publique ──────────────────────────────────────────────────────────
    def set_nb_series(self, nb: int) -> None:
        self._nb_series = nb

    def on_init_point(self, cible: str, i: int,
                      val: Optional[float], t: float, hr: float) -> None:
        sid  = f"init_{cible}"
        data = self._get_or_create(sid, f"Init {cible.upper()}", _C["init_fg"])
        if i == 1:
            data.reinit()
            self._follow_live = True
        data.ajouter(val)
        self._maj_ligne(sid)
        self._suivre(sid)
        self._readout.update_stats(cible, f"Init {cible.upper()}", i, t, hr,
                                   data.m_provisoire(), None)

    def on_init_complete(self, cible: str,
                         m: Optional[float], v: Optional[float]) -> None:
        sid  = f"init_{cible}"
        data = self._series.get(sid)
        if data:
            data.m = m
            data.v = v
            data.complete = True
            self._maj_ligne(sid)
            if sid == self._selected:
                self._chart.afficher(data)
            self._nuage.redessiner()

    def on_serie_point(self, x: int, i: int,
                       val: Optional[float], t: float, hr: float) -> None:
        couleur = _bleu_serie(x, max(self._nb_series, 1))
        data    = self._get_or_create(x, f"Series {x}", couleur)
        if i == 1:
            data.reinit()
            self._follow_live = True
        data.ajouter(val)
        self._maj_ligne(x)
        self._suivre(x)
        serie_lbl = f"{x} / {self._nb_series}" if self._nb_series else str(x)
        self._readout.update_stats(self._com_actif.get(), serie_lbl, i, t, hr,
                                   data.m_provisoire(), None)

    def on_serie_complete(self, x: int, m: float, v: float) -> None:
        data = self._series.get(x)
        if data:
            data.m = m
            data.v = v
            data.complete = True
            self._maj_ligne(x)
            if x == self._selected:
                self._chart.afficher(data)
            self._nuage.redessiner()

    def set_com_actif(self, com: str) -> None:
        """Indique quel COM est mesuré (choisi sur la page Measurement)."""
        self._com_actif.set(com)
        if hasattr(self, "_lbl_com"):
            self._lbl_com.configure(text=f"Measuring: COM {com[-1]}")

    def reset(self) -> None:
        self._series.clear()
        self._order.clear()
        self._selected = None
        self._follow_live = True
        self._listbox.delete(0, "end")
        self._nuage.reset()
        self._chart.afficher(None)
        if self._nuage.winfo_ismapped():
            self._toggle_vue()
