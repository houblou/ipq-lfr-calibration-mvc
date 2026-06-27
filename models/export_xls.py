
"""

Structure Excel:
  Colonne A    : index i (1-30) + étiquettes de synthèse
  Colonnes B+  : une colonne par série (les 2 premières = acquisition initiale COM1/COM2)
  Lignes 2-31 : N[1] à N[30]
  Ligne 32     : MOYENNE
  Ligne 33     : VARIANCE
  Ligne 34     : T moy (°C)
  Ligne 35     : HR moy (%)
  Ligne 36     : Distance (mm)
  Ligne 37     : Date
  Ligne 38     : Heure début
"""
import os
from datetime import datetime
from typing import List, Optional, Dict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    OPENPYXL_OK = True
except ImportError:
    OPENPYXL_OK = False

from core.logger import creer_logger
from core.paths import nom_fichier_xls

logger = creer_logger("phase3")

# Lignes de synthèse (index 1-based dans Excel)
ROW_DATA_START = 2          # N[1] en ligne 2
ROW_MOYENNE    = 32
ROW_VARIANCE   = 33
ROW_T_MOY      = 34
ROW_HR_MOY     = 35
ROW_DISTANCE   = 36
ROW_DATE       = 37
ROW_HEURE      = 38
ROW_OPERATEUR  = 39

SYNTHESE_LABELS = {
    ROW_MOYENNE:   "MEAN",
    ROW_VARIANCE:  "VARIANCE",
    ROW_T_MOY:     "Mean T (°C)",
    ROW_HR_MOY:    "Mean RH (%)",
    ROW_DISTANCE:  "Distance (mm)",
    ROW_DATE:      "Date",
    ROW_HEURE:     "Start time",
    ROW_OPERATEUR: "Operator",
}


class ExportXLS:
    """Gère la création et l'écriture du fichier Excel multi-séries."""

    def __init__(self, indice_notation: str, dossier: str = ".",
                 simulation: bool = False, operateur: str = "") -> None:
        self.indice_notation = indice_notation
        self.dossier         = dossier
        self.chemin_fichier  = os.path.join(dossier, nom_fichier_xls(indice_notation))
        self.wb              = None
        self.ws              = None
        self.serie_courante  = 0
        self.simulation      = simulation
        self.operateur       = operateur

    def ouvrir(self) -> bool:
        """Crée le classeur Excel et prépare la feuille principale."""
        if not OPENPYXL_OK:
            logger.error("openpyxl non installé — export XLS impossible.")
            return False
        try:
            self.wb = openpyxl.Workbook()
            self.ws = self.wb.active
            self.ws.title = "SIMULATION" if self.simulation else "Measurements"
            self._ecrire_entete()
            if self.simulation:
                warning = self.ws.cell(
                    row=40, column=1,
                    value="SIMULATION DATA — NOT VALID FOR METROLOGY",
                )
                warning.font = Font(bold=True, color="FFFFFF")
                warning.fill = PatternFill("solid", fgColor="C00000")
            os.makedirs(self.dossier, exist_ok=True)
            self.wb.save(self.chemin_fichier)
            logger.info("Fichier Excel créé : %s", self.chemin_fichier)
            return True
        except Exception as exc:
            logger.error("Erreur création Excel : %s", exc)
            return False

    def ajouter_serie(
        self,
        n:        List[Optional[float]],
        m:        float,
        v:        float,
        t_moy:    float = 0.0,
        hr_moy:   float = 0.0,
        distance: float = 0.0,
        date:     str   = "",
        heure:    str   = "",
        label:    Optional[str] = None,
    ) -> None:
        """
        Ajoute une série dans la colonne suivante.
        Sauvegarde automatiquement après chaque série.
        """
        if self.ws is None:
            raise RuntimeError("Excel file is not open.")

        if len(n) != 30:
            raise ValueError(f"A series must contain exactly 30 points; received: {len(n)}.")
        if any(valeur is None for valeur in n):
            raise ValueError("The series contains at least one invalid measurement (None).")

        if not date:
            date = datetime.now().strftime("%d/%m/%Y")
        if not heure:
            heure = datetime.now().strftime("%H:%M:%S")

        self.serie_courante += 1
        col = self.serie_courante + 1   # B = col 2, C = col 3…

        # En-tête de colonne (label explicite ou numérotation automatique)
        entete = label if label else f"Series {self.serie_courante}"
        cell_h = self.ws.cell(row=1, column=col, value=entete)
        cell_h.font      = Font(bold=True, color="FFFFFF")
        cell_h.fill      = PatternFill("solid", fgColor="2E75B6")
        cell_h.alignment = Alignment(horizontal="center")

        # Données N[i] (lignes 2 à 31)
        for i, valeur in enumerate(n, start=1):
            self.ws.cell(row=i + 1, column=col, value=valeur)

        # Synthèse
        synthese = {
            ROW_MOYENNE:  m,
            ROW_VARIANCE: v,
            ROW_T_MOY:    t_moy,
            ROW_HR_MOY:   hr_moy,
            ROW_DISTANCE: distance,
            ROW_DATE:     date,
            ROW_HEURE:    heure,
        }
        for row, valeur in synthese.items():
            cell = self.ws.cell(row=row, column=col, value=valeur)
            cell.fill = PatternFill("solid", fgColor="FFF3CD")

        self._sauvegarder()
        logger.info(
            "%s ajoutée (col %d) — M=%.6f V=%.6f T_moy=%.2f HR_moy=%.2f dist=%.1f",
            entete, col, m, v, t_moy, hr_moy, distance,
        )

    def fermer(self) -> None:
        """Sauvegarde finale."""
        self._sauvegarder()
        logger.info("Fichier Excel finalisé : %s", self.chemin_fichier)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ecrire_entete(self) -> None:
        """Écrit la colonne A : index i + étiquettes de synthèse."""
        bold = Font(bold=True)

        # Ligne 1, col A
        self.ws.cell(row=1, column=1, value="i").font = bold

        # Index 1..30
        for i in range(1, 31):
            self.ws.cell(row=i + 1, column=1, value=i)

        # Étiquettes de synthèse
        fill_synth = PatternFill("solid", fgColor="D9E1F2")
        for row, label in SYNTHESE_LABELS.items():
            cell = self.ws.cell(row=row, column=1, value=label)
            cell.font = bold
            cell.fill = fill_synth

        # Opérateur — donnée de session, colonne B fixe (une seule valeur)
        if self.operateur:
            cell_op = self.ws.cell(row=ROW_OPERATEUR, column=2, value=self.operateur)
            cell_op.fill = PatternFill("solid", fgColor="FFF3CD")

        # Largeur colonne A
        self.ws.column_dimensions["A"].width = 16

    def _sauvegarder(self) -> None:
        if self.wb and self.chemin_fichier:
            try:
                self.wb.save(self.chemin_fichier)
            except Exception as exc:
                logger.exception("Excel save failed: %s", exc)
                raise RuntimeError(
                    f"Unable to save the Excel file: {self.chemin_fichier}"
                ) from exc
