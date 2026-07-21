# -*- coding: utf-8 -*-
"""Contenu de la sous-vue d'aide « Instruments and wiring » (éditable librement)."""

HELP_TEXT = """INSTRUMENTS AND WIRING

Multimeters
    UR (com1) and UL (com2). One of them drives the generator from its
    back panel — the live voltage is shown on the top bar.

Ambient thermometer
    Hart 1620 (default) or RUSKA 2456-LEM. The source is auto-detected
    when connected; it can also be selected manually.

Buses
    COMx         -> serial (multimeters, RUSKA)
    GPIB / ASRL  -> VISA (Hart)
"""

if __name__ == "__main__":
    print(HELP_TEXT)
