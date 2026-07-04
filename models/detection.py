# -*- coding: utf-8 -*-
"""
detect_com.py — Détection automatique des instruments sur ports COM (RS-232)
Programme IPQ/LFR — Python 3.8+, dépendance unique : pyserial

Scanne tous les ports série, teste les combinaisons de paramètres
(baudrate / parité / stop bits / rtscts), envoie des commandes de détection
puis identifie :
    • Agilent 34401A      (multimètre 6½ digits, protocole SCPI)
    • Hart Scientific 1620 (thermohygromètre, protocole ASCII propriétaire)

Dès qu'une réponse valide est reçue sur un port, le scan de ce port s'arrête.
Le résultat est affiché (rapport ✔/✘) et exporté dans detect_result.json,
directement exploitable par phase1_comm.py au démarrage de l'application.

Usage :
    python detect_com.py                 # scan complet de tous les ports
    python detect_com.py --list          # liste seulement les ports, sans scan
    python detect_com.py --port COM3     # scan d'un seul port
    python detect_com.py --timeout 1.0   # timeout de lecture par sonde (s)
    python detect_com.py -o result.json  # chemin de sortie JSON
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_OK = True
except ImportError:
    PYSERIAL_OK = False   # le module reste importable (ex. depuis l'UI) sans planter


# ── Paramètres série à balayer ────────────────────────────────────────────────
# 9600 en premier (le plus courant) pour verrouiller vite le cas nominal.
BAUDRATES = [9600, 19200, 38400, 57600]

# Les listes dépendant de pyserial ne sont construites que s'il est présent,
# pour que le module reste importable même sans la dépendance.
if PYSERIAL_OK:
    PARITES = [
        ("None", serial.PARITY_NONE),   # PARITY_NONE == 'N'
        ("Even", serial.PARITY_EVEN),   # PARITY_EVEN == 'E'
        ("Odd",  serial.PARITY_ODD),    # PARITY_ODD  == 'O'
    ]
    STOPBITS = [
        (1, serial.STOPBITS_ONE),
        (2, serial.STOPBITS_TWO),
    ]
else:
    PARITES = []
    STOPBITS = []

RTSCTS = [True, False]

TIMEOUT_DEFAUT = 2.0   # secondes (param série imposé par le cahier des charges)


# ── Validateurs de réponse ────────────────────────────────────────────────────

def _est_float(texte: str) -> bool:
    """True si le texte (éventuellement nettoyé) représente un nombre."""
    if not texte:
        return False
    candidat = texte.strip().split()[0].rstrip(",;")
    try:
        float(candidat)
        return True
    except ValueError:
        return False


def _est_agilent(texte: str) -> bool:
    haut = texte.upper()
    return "AGILENT" in haut or "34401" in haut or "HEWLETT" in haut


# ── Profils d'instruments ─────────────────────────────────────────────────────
# Chaque profil = un instrument + une liste de sondes (commande -> validateur).
# L'ordre compte : on teste d'abord l'identifiant fort (*IDN? Agilent) pour
# éviter de confondre un multimètre et un thermohygromètre qui renvoient
# tous deux un float.
PROFILS = [
    {
        "instrument": "Agilent 34401A",
        "protocole":  "SCPI",
        "role":       "multimetre",
        "sondes": [
            {"label": "*IDN?", "cmd": b"*IDN?\n", "valide": _est_agilent},
            {"label": "READ?", "cmd": b"READ?\n", "valide": _est_float},
        ],
    },
    {
        "instrument": "Hart Scientific 1620",
        "protocole":  "ASCII",
        "role":       "thermo",
        "sondes": [
            {"label": "T",     "cmd": b"T\r\n",   "valide": _est_float},
            {"label": "?T",    "cmd": b"?T\r\n",  "valide": _est_float},
            {"label": "H",     "cmd": b"H\r\n",   "valide": _est_float},
            {"label": "(vide)", "cmd": b"\r\n",   "valide": _est_float},
        ],
    },
]


# ── Découverte des ports ──────────────────────────────────────────────────────

def lister_ports() -> List[str]:
    """
    Liste les ports série disponibles (Windows COMx et Linux /dev/tty*).
    pyserial.comports() est multi-plateforme.
    """
    try:
        ports = [p.device for p in serial.tools.list_ports.comports()]
    except Exception as exc:
        print(f"  (impossible de lister les ports : {exc})")
        ports = []
    return sorted(ports)


# ── Test d'une combinaison sur un port ────────────────────────────────────────

def _interroger(ser: "serial.Serial", sonde: dict) -> Optional[str]:
    """Envoie une commande et retourne la réponse texte (ou None)."""
    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.write(sonde["cmd"])
        time.sleep(0.05)
        brut = ser.readline()
        if not brut:                       # rien en mode ligne -> lecture brute
            brut = ser.read(256)
        if not brut:
            return None
        return brut.decode("ascii", errors="replace").strip()
    except Exception:
        return None


def tester_combinaison(port: str, baud: int, parite, stopbits,
                       rtscts: bool, timeout: float,
                       deadline: Optional[float] = None) -> Optional[Dict]:
    """
    Ouvre le port avec ces paramètres et teste tous les profils.
    Retourne le dict d'identification si un instrument répond, sinon None.
    Ne lève jamais : tout est encapsulé dans try/except, le port est
    systématiquement refermé (finally).
    """
    ser = None
    try:
        ser = serial.Serial()
        ser.port         = port
        ser.baudrate     = baud
        ser.parity       = parite
        ser.stopbits     = stopbits
        ser.bytesize     = serial.EIGHTBITS
        ser.rtscts       = rtscts
        ser.timeout      = timeout
        ser.write_timeout = timeout
        ser.open()
        time.sleep(0.15)   # laisse l'instrument s'initialiser après ouverture

        # Sonde de vivacité : *IDN? puis T. Si les deux sont muettes, le port
        # ne parle pas à ces paramètres -> on abandonne vite cette combinaison.
        vivant = False
        for profil in PROFILS:
            for sonde in profil["sondes"]:
                if deadline is not None and time.time() >= deadline:
                    return None   # budget temps dépassé : on coupe entre deux sondes
                reponse = _interroger(ser, sonde)
                if reponse:
                    vivant = True
                    if sonde["valide"](reponse):
                        return {
                            "instrument": profil["instrument"],
                            "protocole":  profil["protocole"],
                            "role":       profil["role"],
                            "commande":   sonde["label"],
                            "reponse":    reponse,
                        }
            # Après le 1er profil, si toujours aucun octet reçu : combinaison morte
            if not vivant:
                break
        return None
    except Exception:
        return None
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


# ── Scan complet d'un port ────────────────────────────────────────────────────

def scanner_port(port: str, timeout: float = TIMEOUT_DEFAUT,
                 deadline: Optional[float] = None) -> Optional[Dict]:
    """Balaye toutes les combinaisons sur un port. Renvoie le 1er succès.
    Si `deadline` (instant absolu time.time()) est fourni et dépassé, arrête net."""
    total = len(BAUDRATES) * len(PARITES) * len(STOPBITS) * len(RTSCTS)
    n = 0
    for baud in BAUDRATES:
        for (p_nom, p_val) in PARITES:
            for (s_nom, s_val) in STOPBITS:
                for rtscts in RTSCTS:
                    if deadline is not None and time.time() >= deadline:
                        _effacer_ligne()
                        return None
                    n += 1
                    _afficher_progression(port, n, total, baud, p_nom, s_nom, rtscts)
                    res = tester_combinaison(port, baud, p_val, s_val, rtscts, timeout, deadline)
                    if res is not None:
                        res.update({
                            "port":     port,
                            "baudrate": baud,
                            "parite":   p_nom,
                            "parite_char": str(p_val),   # 'N' / 'E' / 'O'
                            "stopbits": s_nom,
                            "rtscts":   rtscts,
                        })
                        _effacer_ligne()
                        return res
    _effacer_ligne()
    return None


def _afficher_progression(port, n, total, baud, parite, stopbits, rtscts) -> None:
    """Barre de progression temps réel sur une seule ligne (\\r)."""
    ligne = (f"  scan {port}  [{n:>2}/{total}]  "
             f"{baud} {parite[0]} {stopbits} rtscts={'On' if rtscts else 'Off'}")
    sys.stdout.write("\r" + ligne.ljust(60))
    sys.stdout.flush()


def _effacer_ligne() -> None:
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()


# ── Rapport et export ─────────────────────────────────────────────────────────

LIGNE = "━" * 50


def afficher_rapport(resultats: List[Dict], non_reconnus: List[Dict]) -> None:
    print("\n" + LIGNE)
    print("RAPPORT DE DÉTECTION COM — IPQ/LFR")
    print(LIGNE)

    if not resultats and not non_reconnus:
        print("Aucun port COM détecté sur le système.")
        print(LIGNE)
        return

    for r in resultats:
        print(f"[✔] {r['port']} — {r['instrument']} ({r['protocole']})")
        print(f"    Baudrate : {r['baudrate']} | Parité : {r['parite']} | "
              f"Stop : {r['stopbits']} | rtscts : {r['rtscts']}")
        print(f"    Réponse {r['commande']} : \"{r['reponse']}\"")

    for nr in non_reconnus:
        print(f"[✘] {nr['port']} — {nr['raison']}")

    # ── Bloc config prêt à coller dans phase1_comm.py ────────────────────────
    config = construire_config(resultats)
    if config:
        print(LIGNE)
        print("CONFIG À UTILISER DANS phase1_comm.py :")
        for cle, c in config.items():
            print(f"  {cle:11s} = \"{c['port']}\"  | params : "
                  f"{c['baudrate']},{c['parite_char']},{c['stopbits']},"
                  f"rtscts={c['rtscts']}")
    print(LIGNE)


def construire_config(resultats: List[Dict]) -> Dict[str, Dict]:
    """
    Construit le mapping logique attendu par phase1_comm.py :
    multimètres -> COM_MULTI1, COM_MULTI2 ; thermo -> COM_THERMO1.
    """
    config: Dict[str, Dict] = {}
    i_multi = 0
    i_thermo = 0
    for r in resultats:
        if r["role"] == "multimetre":
            i_multi += 1
            config[f"COM_MULTI{i_multi}"] = r
        elif r["role"] == "thermo":
            i_thermo += 1
            config[f"COM_THERMO{i_thermo}"] = r
    return config


def mapping_phase1(resultats: List[Dict]) -> Dict[str, Dict]:
    """
    Mapping direct vers les cibles de phase1_comm.py (com1, com2, thermo1),
    avec la parité au format pyserial ('N'/'E'/'O') pour connecter_serie().
    """
    mapping: Dict[str, Dict] = {}
    multis = [r for r in resultats if r["role"] == "multimetre"]
    thermos = [r for r in resultats if r["role"] == "thermo"]

    for idx, r in enumerate(multis, start=1):
        if idx <= 2:   # phase1 ne gère que com1 et com2
            mapping[f"com{idx}"] = _params_phase1(r)
    if thermos:
        mapping["thermo1"] = _params_phase1(thermos[0])
    return mapping


def _params_phase1(r: Dict) -> Dict:
    return {
        "port":       r["port"],
        "baudrate":   r["baudrate"],
        "parite":     r["parite_char"],   # 'N' / 'E' / 'O'
        "stopbits":   r["stopbits"],
        "rtscts":     r["rtscts"],
        "protocole":  r["protocole"],
        "instrument": r["instrument"],
    }


def exporter_json(resultats: List[Dict], non_reconnus: List[Dict],
                  chemin: str) -> None:
    """Écrit le résultat dans un JSON exploitable par phase1_comm.py."""
    donnees = {
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "detections":   resultats,
        "non_reconnus": non_reconnus,
        "config":       construire_config(resultats),
        "mapping":      mapping_phase1(resultats),
    }
    try:
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        print(f"Résultat exporté : {os.path.abspath(chemin)}")
    except Exception as exc:
        print(f"ERREUR écriture JSON : {exc}")


# ── API programmatique (utilisée par l'UI) ───────────────────────────────────

def detecter(timeout: float = TIMEOUT_DEFAUT,
             ports: Optional[List[str]] = None,
             deadline: Optional[float] = None) -> Dict:
    """
    Scan programmatique réutilisable (ex. depuis l'interface graphique).
    Retourne un dict identique au JSON exporté :
        {date, detections, non_reconnus, config, mapping}
    Ne lève jamais ; si pyserial est absent, renvoie un résultat vide.
    `deadline` (instant absolu time.time()) borne la durée totale du scan.
    """
    if not PYSERIAL_OK:
        return {"date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "detections": [], "non_reconnus": [],
                "config": {}, "mapping": {}, "erreur": "pyserial absent"}

    if ports is None:
        ports = lister_ports()

    resultats: List[Dict] = []
    non_reconnus: List[Dict] = []
    for port in ports:
        if deadline is not None and time.time() >= deadline:
            non_reconnus.append({"port": port, "raison": "Scan interrompu (budget temps dépassé)"})
            continue
        try:
            res = scanner_port(port, timeout=timeout, deadline=deadline)
        except Exception as exc:
            non_reconnus.append({"port": port, "raison": f"Erreur de scan : {exc}"})
            continue
        if res is not None:
            resultats.append(res)
        else:
            non_reconnus.append({"port": port,
                                 "raison": "Aucun instrument reconnu"})

    return {
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "detections":   resultats,
        "non_reconnus": non_reconnus,
        "config":       construire_config(resultats),
        "mapping":      mapping_phase1(resultats),
    }


# ── Programme principal ───────────────────────────────────────────────────────

def main() -> int:
    if not PYSERIAL_OK:
        print("ERREUR : pyserial est requis  ->  pip install pyserial")
        return 1

    parser = argparse.ArgumentParser(
        description="Détection automatique des instruments sur ports COM (IPQ/LFR)")
    parser.add_argument("--list", action="store_true",
                        help="liste les ports détectés puis quitte (aucun scan)")
    parser.add_argument("--port", help="ne scanner qu'un seul port (ex. COM3)")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_DEFAUT,
                        help="timeout de lecture par sonde, en secondes")
    parser.add_argument("-o", "--output", default="detect_result.json",
                        help="chemin du fichier JSON de sortie")
    args = parser.parse_args()

    print(LIGNE)
    print("DÉTECTION AUTOMATIQUE DES INSTRUMENTS COM — IPQ/LFR")
    print(f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(LIGNE)

    ports = [args.port] if args.port else lister_ports()
    if not ports:
        print("Aucun port COM détecté.")
        exporter_json([], [], args.output)
        return 0

    print(f"Ports à analyser : {', '.join(ports)}")
    if args.list:
        return 0

    resultats: List[Dict] = []
    non_reconnus: List[Dict] = []

    for port in ports:
        try:
            res = scanner_port(port, timeout=args.timeout)
        except Exception as exc:
            non_reconnus.append({"port": port,
                                 "raison": f"Erreur de scan : {exc}"})
            continue
        if res is not None:
            print(f"  ✔ {port} : {res['instrument']} détecté.")
            resultats.append(res)
        else:
            non_reconnus.append({
                "port": port,
                "raison": "Aucun instrument reconnu (pas de réponse / "
                          "port occupé ou câble débranché)",
            })

    afficher_rapport(resultats, non_reconnus)
    exporter_json(resultats, non_reconnus, args.output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nScan interrompu par l'utilisateur.")
        sys.exit(1)
