# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée
Projet : IPQ/LFR — Calibração de Fotômetros e Luxímetros
"""
from views.app_window import ApplicationIPQ


def main() -> None:
    app = ApplicationIPQ()
    app.mainloop()


if __name__ == "__main__":
    main()
