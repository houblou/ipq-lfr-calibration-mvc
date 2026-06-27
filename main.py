# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée
Projet : IPQ/LFR — Calibração de Fotômetros e Luxímetros
"""
import sys

from views.app_window import ApplicationIPQ


def _activer_dpi_awareness() -> None:
    """Windows : déclare le process « DPI-aware » AVANT de créer la fenêtre.

    Sans ça, Windows dessine l'appli à 96 DPI puis étire l'image (bitmap) à
    l'échelle de l'écran (125/150 %), ce qui rend texte et bords flous/pixelisés.
    En mode aware, Tk dessine à la résolution réelle → rendu net.
    """
    if sys.platform != "win32":
        return
    import ctypes
    # Per-monitor v2 (Windows 10 1703+) → fallback système → fallback ancien.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()        # Vista+
    except Exception:
        pass


def _dpi_systeme() -> int:
    if sys.platform != "win32":
        return 96
    import ctypes
    try:
        return ctypes.windll.user32.GetDpiForSystem() or 96
    except Exception:
        return 96


def _ajuster_echelle(app, dpi: int) -> None:
    """Aligne l'échelle des polices Tk sur le DPI réel (points → pixels = DPI/72)."""
    if dpi and dpi != 96:
        try:
            app.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass


# ── Mise à l'échelle de la géométrie en pixels (paddings, largeurs, hauteurs) ───
# Les polices (en points) suivent le DPI automatiquement, mais la mise en page est
# en pixels fixes et ne suit pas. On la multiplie par DPI/96 pour qu'elle reste
# proportionnée aux polices → net ET même taille apparente qu'en 96 DPI étiré.

def _ints(v):
    if isinstance(v, (int, float)):
        return [int(round(v))]
    if isinstance(v, (tuple, list)):
        return [int(round(float(x))) for x in v]
    return [int(round(float(p))) for p in str(v).replace("{", " ").replace("}", " ").split()]


def _pad(v, s):
    nums = [int(round(n * s)) for n in _ints(v)]
    if not nums:
        return 0
    return tuple(nums) if len(nums) > 1 else nums[0]


def _scale_layout(widget, s) -> None:
    import tkinter as tk
    for getter, setter in (("pack_info", "pack_configure"), ("grid_info", "grid_configure")):
        try:
            info = getattr(widget, getter)()
        except (tk.TclError, AttributeError):
            info = None
        if info:
            kw = {k: _pad(info[k], s) for k in ("padx", "pady", "ipadx", "ipady")
                  if k in info and str(info[k]) not in ("", "0")}
            if kw:
                try:
                    getattr(widget, setter)(**kw)
                except tk.TclError:
                    pass
    cls = widget.winfo_class()
    opts = []
    if cls in ("Frame", "Labelframe"):
        opts += ["width", "height"]
    if cls in ("Label", "Message"):
        opts += ["wraplength"]
    for opt in opts:
        try:
            val = int(float(widget.cget(opt)))
        except (tk.TclError, ValueError):
            continue
        if val > 1:
            try:
                widget.configure(**{opt: int(round(val * s))})
            except tk.TclError:
                pass
    for child in widget.winfo_children():
        _scale_layout(child, s)


def _mettre_a_echelle(app, dpi: int) -> None:
    s = (dpi or 96) / 96.0
    if abs(s - 1.0) < 0.01:
        return
    try:
        mn = app.wm_minsize()
        if mn and mn[0] > 1:
            app.wm_minsize(int(mn[0] * s), int(mn[1] * s))
    except Exception:
        pass
    try:
        from tkinter import ttk
        st = ttk.Style()
        st.configure("Light.Treeview", rowheight=int(round(28 * s)))
        st.configure("Green.Horizontal.TProgressbar", thickness=int(round(10 * s)))
    except Exception:
        pass
    _scale_layout(app, s)
    app.update_idletasks()


def main() -> None:
    _activer_dpi_awareness()
    dpi = _dpi_systeme()
    app = ApplicationIPQ()
    _ajuster_echelle(app, dpi)
    _mettre_a_echelle(app, dpi)
    app.mainloop()


if __name__ == "__main__":
    main()
