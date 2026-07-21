# -*- coding: utf-8 -*-
"""views/theme.py — charte graphique claire + helpers UI partagés.

Source unique de vérité du design (palette, polices, fabriques de widgets).
Les clés sémantiques de la palette `C` sont conservées telles quelles : les
pages existantes les réutilisent et adoptent automatiquement le thème clair.
"""

import tkinter as tk

# ── Palette claire ──────────────────────────────────────────────────────────────
# Fond gris clair + accents violet (interactif) / vert (validé).
# NB : Tkinter ne sait pas faire de fond en grille / dégradé / ombre — on dégrade
# en aplats. Les noms de clés restent identiques à l'ancienne palette sombre.

C = {
    "bg_app": "#D8D7D3",  # zone de contenu (gris clair)
    "bg_sidebar": "#EFEEEA",
    "bg_sidebar_title": "#757266",
    "bg_topbar": "#F4F3F0",
    "bg_card": "#FFFFFF",
    "bg_input": "#FFFFFF",
    "bg_active": "#E6DCFB",  # sélection / état actif (violet pâle)
    "bg_hover": "#E8E7E2",
    "scroll_track": "#CFCEC8",
    "scroll_thumb": "#8A8D86",
    "scroll_thumb_hover": "#5F6168",
    "bg_success": "#E4F2E9",
    "bg_danger": "#FBE4E2",
    "bg_warning": "#FBF1DD",
    "bg_badge": "#EDEAF6",
    "border": "#DCDBD5",
    "border_light": "#C9C7C0",
    "txt_primary": "#24272C",
    "txt_secondary": "#5F6168",
    "txt_muted": "#8A8D86",
    "txt_active": "#5A2FC2",  # violet (texte interactif)
    "txt_green": "#2E7D4F",
    "txt_red": "#C0392B",
    "txt_blue": "#2563EB",
    "txt_amber": "#B7791F",
}

# Accents pleins (boutons colorés) — désaturés pour un rendu plus calme, moins « lourd ».
# On garde une luminosité proche des anciennes valeurs pour conserver le contraste du
# texte blanc ; c'est surtout la SATURATION (et le noir pur) qui alourdissait l'écran.
ACCENT_VIOLET = "#7458C2"
ACCENT_VIOLET_HOVER = "#6349B0"
ACCENT_GREEN = "#4E9670"
ACCENT_RED = "#CB6156"
NOIR = "#3B3A37"        # gris chaud foncé (au lieu du noir pur, qui jurait avec le gris)
NOIR_HOVER = "#2C2B29"
var_ajustement_taille = 3  # Ajustement de taille pour les polices (pour compenser le DPI)
FONT = ("Segoe UI", 10 + var_ajustement_taille)
FONT_SMALL = ("Segoe UI", 9 + var_ajustement_taille)
FONT_BOLD = ("Segoe UI", 10 + var_ajustement_taille, "bold")
FONT_TITLE = ("Segoe UI", 13 + var_ajustement_taille, "bold")
FONT_LABEL = ("Segoe UI", 9 + var_ajustement_taille)
FONT_VALUE = ("Segoe UI", 18 + var_ajustement_taille, "bold")
FONT_MONO = ("Consolas", 9 + var_ajustement_taille)


#  widgets


def lbl(parent, text="", font=FONT, fg=None, bg=None, anchor="w", **kw):
    return tk.Label(
        parent,
        text=text,
        font=font,
        fg=fg or C["txt_secondary"],
        bg=bg or C["bg_app"],
        anchor=anchor,
        **kw,
    )


def sep(parent, bg=None):
    return tk.Frame(parent, height=1, bg=bg or C["border"])


def card(parent, **kw):
    return tk.Frame(parent, bg=C["bg_card"], highlightbackground=C["border"], highlightthickness=1, **kw)


def btn(parent, text, command, color=None, fgcolor=None, font=FONT, padx=12, pady=5):
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=font,
        bg=color or C["bg_active"],
        fg=fgcolor or C["txt_active"],
        activebackground=C["bg_hover"],
        activeforeground=C["txt_primary"],
        relief="flat",
        bd=0,
        padx=padx,
        pady=pady,
        cursor="hand2",
    )


def btn_noir(parent, text, command, font=FONT, padx=14, pady=7):
    """Bouton noir plein, texte blanc — reste noir au survol/clic (bien visible)."""
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=font,
        bg=NOIR,
        fg="#ffffff",
        activebackground=NOIR_HOVER,
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=padx,
        pady=pady,
        cursor="hand2",
    )


def btn_ghost(parent, text, command, fg=None, border=None, font=FONT, padx=14, pady=6):
    """Bouton LÉGER (action secondaire) : fond blanc, texte coloré, fine bordure colorée.

    Allège l'écran par rapport à un aplat plein — on réserve le plein à l'action
    principale (ex. START), et STOP / Final / etc. passent en contour discret.
    """
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=font,
        bg=C["bg_card"],
        fg=fg or C["txt_secondary"],
        activebackground=C["bg_hover"],
        activeforeground=fg or C["txt_primary"],
        disabledforeground=C["txt_muted"],
        relief="flat",
        bd=0,
        highlightbackground=border or C["border_light"],
        highlightcolor=border or C["border_light"],
        highlightthickness=1,
        padx=padx,
        pady=pady,
        cursor="hand2",
    )


def btn_accent(parent, text, command, color, fgcolor="#ffffff", active=None, font=FONT_BOLD, padx=16, pady=8):
    """Bouton à accent plein (violet / vert / rouge)."""
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=font,
        bg=color,
        fg=fgcolor,
        activebackground=active or color,
        activeforeground=fgcolor,
        relief="flat",
        bd=0,
        padx=padx,
        pady=pady,
        cursor="hand2",
    )


def section_title(parent, text):
    f = tk.Frame(parent, bg=C["bg_app"])
    f.pack(fill="x", padx=20, pady=(16, 12))
    tk.Label(f, text=text, font=FONT_TITLE, fg=C["txt_primary"], bg=C["bg_app"]).pack(side="left")
    tk.Frame(f, height=1, bg=C["border"]).pack(side="left", fill="x", expand=True, padx=(12, 0), pady=6)


def champ_saisie(parent, textvariable=None, width=20, **kw):
    """Champ de saisie clair (bordure grise, fond blanc)."""
    return tk.Entry(
        parent,
        textvariable=textvariable,
        width=width,
        bg=C["bg_input"],
        fg=C["txt_primary"],
        insertbackground=C["txt_primary"],
        relief="flat",
        bd=0,
        highlightbackground=C["border_light"],
        highlightcolor=ACCENT_VIOLET,
        highlightthickness=1,
        font=FONT,
        **kw,
    )
