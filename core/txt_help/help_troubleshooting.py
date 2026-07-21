# -*- coding: utf-8 -*-
"""Contenu de la sous-vue d'aide « Troubleshooting and FAQ » (éditable librement)."""

HELP_TEXT = """TROUBLESHOOTING AND FAQ

Devices disconnect during a measurement
    Reconnect on the Connection page; a single VISA ResourceManager is
    kept open for the whole session.

The thermometer shows "T: error"
    The Hart is read in 'hart' mode by default and auto-detected. Check
    the cable and that the right ambient source is selected.

The Excel file is locked / cannot be saved
    Close it in Excel before starting or exporting; the app never
    overwrites a running measurement.

Points per series above the sheet capacity
    Set the points before approving the initialization, or create a
    new session.
"""

if __name__ == "__main__":
    print(HELP_TEXT)
