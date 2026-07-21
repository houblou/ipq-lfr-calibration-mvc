# -*- coding: utf-8 -*-
"""Contenu de la sous-vue d'aide « Quick start » (éditable librement)."""

HELP_TEXT = """QUICK START — 4 steps

1.  Connection
    Select the instruments (UR / UL multimeters, ambient thermometer),
    connect them, enter the operator and the record identifier, then
    click Validate connection.

2.  Initialization
    Run Init UR and Init UL (30 points each), then Approve.
    The Excel file is created at this moment.

3.  Calibration
    Choose the measuring multimeter, the number of series and the
    points per series, then START.

4.  Results
    Review the series table, run the Final measurement, and export.
"""

if __name__ == "__main__":
    print(HELP_TEXT)
