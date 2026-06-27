# -*- coding: utf-8 -*-
"""
audit.py — Journal d'audit horodaté et chaîné (ISO/IEC 17025)

Chaque entrée contient le hash SHA-256 enchaîné sur l'entrée précédente :
toute modification du fichier (ajout, suppression, altération d'une ligne)
rompt la chaîne et est détectée par verifier_integrite().
"""
import hashlib
import os
import threading
from datetime import datetime

AUDIT_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "IPQ_LFR", "audit"
)

# ── Événements canoniques ──────────────────────────────────────────────────────
EV_DEMARRAGE            = "DEMARRAGE"
EV_OPERATEUR            = "OPERATEUR_IDENTIFIE"
EV_CONNEXION            = "CONNEXION_VALIDEE"
EV_INIT_DEBUT           = "INIT_DEBUT"
EV_INIT_FIN             = "INIT_FIN"
EV_INIT_INTERROMPUE     = "INIT_INTERROMPUE"
EV_INIT_ECHEC           = "INIT_ECHEC"
EV_INIT_VALIDEE         = "INIT_VALIDEE"
EV_CAL_DEBUT            = "CALIBRATION_DEBUT"
EV_CAL_SERIE            = "CALIBRATION_SERIE"
EV_CAL_FIN              = "CALIBRATION_FIN"
EV_CAL_INTERROMPUE      = "CALIBRATION_INTERROMPUE"
EV_EXPORT_EXCEL         = "EXPORT_EXCEL"
EV_SIMULATION_ACTIVE    = "SIMULATION_ACTIVE"
EV_SIMULATION_DESACTIVE = "SIMULATION_DESACTIVE"
EV_ADMIN_AUTH           = "ADMIN_AUTHENTIFIE"
EV_ADMIN_LOCK           = "ADMIN_VERROUILLE"
EV_ADMIN_CLE            = "ADMIN_CLE_CONFIGUREE"
EV_ERREUR               = "ERREUR"
EV_ARRET                = "ARRET_APPLICATION"


class JournalAudit:
    """
    Journal d'audit chaîné, thread-safe, un fichier par jour.

    Format de chaque ligne :
        NNNNNN|ISO-timestamp|opérateur|EVENEMENT|détails|hash_sha256

    Le hash_sha256 est calculé sur (hash_précédent + contenu_ligne_sans_hash),
    formant une chaîne dont la rupture trahit toute altération.
    """

    _HASH_INITIAL = "0" * 64

    def __init__(self, operateur: str = "INCONNU") -> None:
        self._lock      = threading.Lock()
        self._operateur = operateur
        self._sequence  = 0
        self._hash_prec = self._HASH_INITIAL

        os.makedirs(AUDIT_DIR, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        self._chemin = os.path.join(AUDIT_DIR, f"audit_{date}.log")

        # Reprendre un fichier existant du jour sans casser la chaîne
        if os.path.isfile(self._chemin):
            with open(self._chemin, "r", encoding="utf-8") as fh:
                lignes = [l.rstrip("\n") for l in fh if l.strip()]
            self._sequence = len(lignes)
            if lignes:
                self._hash_prec = lignes[-1].rsplit("|", 1)[-1]

        self.enregistrer(EV_DEMARRAGE, "Application démarrée")

    # ── API publique ──────────────────────────────────────────────────────────

    def set_operateur(self, nom: str) -> None:
        ancien = self._operateur
        self._operateur = nom
        self.enregistrer(EV_OPERATEUR, f"{ancien} → {nom}")

    def enregistrer(self, evenement: str, details: str = "") -> None:
        with self._lock:
            self._sequence += 1
            ts      = datetime.now().isoformat(timespec="milliseconds")
            contenu = f"{self._sequence:06d}|{ts}|{self._operateur}|{evenement}|{details}"
            hash_l  = hashlib.sha256(
                (self._hash_prec + contenu).encode("utf-8")
            ).hexdigest()
            ligne = f"{contenu}|{hash_l}\n"
            with open(self._chemin, "a", encoding="utf-8") as fh:
                fh.write(ligne)
            self._hash_prec = hash_l

    @property
    def chemin(self) -> str:
        return self._chemin

    @property
    def operateur(self) -> str:
        return self._operateur


# ── Vérification d'intégrité ──────────────────────────────────────────────────

def verifier_integrite(chemin: str) -> tuple:
    """
    Vérifie la chaîne de hash du journal.

    Retourne (ok: bool, nb_lignes: int, premiere_ligne_invalide: int | None).
    Une ligne invalide signifie une modification, une insertion ou une suppression.
    """
    if not os.path.isfile(chemin):
        return False, 0, None

    with open(chemin, "r", encoding="utf-8") as fh:
        lignes = [l.rstrip("\n") for l in fh if l.strip()]

    hash_prec = JournalAudit._HASH_INITIAL
    for numero, ligne in enumerate(lignes, start=1):
        parties = ligne.rsplit("|", 1)
        if len(parties) != 2:
            return False, len(lignes), numero
        contenu, hash_attendu = parties
        hash_calcule = hashlib.sha256(
            (hash_prec + contenu).encode("utf-8")
        ).hexdigest()
        if hash_calcule != hash_attendu:
            return False, len(lignes), numero
        hash_prec = hash_attendu

    return True, len(lignes), None
