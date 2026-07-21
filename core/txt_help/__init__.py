# -*- coding: utf-8 -*-
"""Textes d'aide de l'application, exposés comme CHAÎNES prêtes à afficher.

Chaque module de ce package définit une constante ``HELP_TEXT``. On la ré-exporte
ici sous un nom parlant pour que les vues fassent simplement :

    from core.txt_help import help_text, help_text_true

Sans ce fichier, ``core.txt_help`` serait un paquet-espace-de-noms implicite et
``from core.txt_help import help_text`` importerait le MODULE ``help_text`` (et non
la chaîne), ce qui afficherait « <module …> » dans la page d'aide.
"""
from core.txt_help.help_text import HELP_TEXT as help_text
from core.txt_help.help_text_true import HELP_TEXT as help_text_true
from core.txt_help.help_quickstart import HELP_TEXT as help_quickstart
from core.txt_help.help_instruments import HELP_TEXT as help_instruments
from core.txt_help.help_troubleshooting import HELP_TEXT as help_troubleshooting

__all__ = [
    "help_text", "help_text_true",
    "help_quickstart", "help_instruments", "help_troubleshooting",
]
