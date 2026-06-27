# -*- coding: utf-8 -*-
"""models/ports.py — GestionPorts : découverte, connexion et surveillance des ports (sans Tkinter)."""
import random
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False

try:
    import pyvisa
    PYVISA_DISPONIBLE = True
except ImportError:
    PYVISA_DISPONIBLE = False

from core.logger import creer_logger
from core.config import (
    BAUD_RATE_DEFAULT,
    PARITY_DEFAULT,
    STOP_BITS_DEFAULT,
    DATA_BITS_DEFAULT,
    TIMEOUT_PORT_DEFAULT,
    POLL_INTERVAL_S,
)

logger = creer_logger("phase1")


class GestionPorts:
    """
    Gère la découverte, la connexion et la surveillance continue des ports.
    Peut être utilisé indépendamment de l'interface graphique.
    """

    def __init__(self) -> None:
        self.com1:         Optional[serial.Serial] = None
        self.com2:         Optional[serial.Serial] = None
        self.thermo1:      Optional[serial.Serial] = None
        self.gpib_rm:      Optional[object] = None
        self.gpib_instr:   Optional[object] = None
        self.noms_appareils: Dict[str, str] = {}   # 'com1' -> 'COM3', etc.

        self._backboard_actif: bool = False
        self._thread_backboard: Optional[threading.Thread] = None
        self._erreurs: List[str] = []
        self._verrou = threading.Lock()
        self.mode_simulation = False
        self._simulation_random = random.Random()
        self._simulation_index = 0

    def set_simulation_mode(self, enabled: bool) -> None:
        """Enable or disable synthetic readings. Never enabled by default."""
        self.mode_simulation = bool(enabled)
        self._simulation_index = 0
        logger.warning("SIMULATION MODE %s", "ENABLED" if enabled else "DISABLED")

    # ── Découverte ────────────────────────────────────────────────────────────

    def lister_ports_serie(self) -> List[str]:
        """Liste tous les ports série disponibles (ex. ['COM1', 'COM3'])."""
        if not SERIAL_DISPONIBLE:
            logger.warning("pyserial non installé.")
            return []
        ports = serial.tools.list_ports.comports()
        disponibles = sorted([p.device for p in ports])
        logger.info("Ports série détectés : %s", disponibles)
        return disponibles

    def lister_ressources_visa(self) -> List[str]:
        """Liste les ressources VISA disponibles (GPIB, USB-TMC…)."""
        if not PYVISA_DISPONIBLE:
            logger.warning("pyvisa non installé — GPIB indisponible.")
            return []
        try:
            rm = pyvisa.ResourceManager()
            ressources = list(rm.list_resources())
            logger.info("Ressources VISA détectées : %s", ressources)
            rm.close()
            return ressources
        except Exception as exc:
            logger.error("Erreur détection VISA : %s", exc)
            return []

    # ── Connexions ────────────────────────────────────────────────────────────

    def connecter_serie(
        self,
        port: str,
        cible: str,
        baud: int = BAUD_RATE_DEFAULT,
        parite: str = PARITY_DEFAULT,
        bits_stop: int = STOP_BITS_DEFAULT,
        bits_data: int = DATA_BITS_DEFAULT,
        timeout: float = TIMEOUT_PORT_DEFAULT,
    ) -> bool:
        """
        Ouvre une connexion série.
        cible : 'com1', 'com2' ou 'thermo1'
        Retourne True si succès.
        """
        if not SERIAL_DISPONIBLE:
            self._ajouter_erreur("pyserial is not installed.")
            return False
        try:
            conn = serial.Serial(
                port=port,
                baudrate=baud,
                parity=parite,
                stopbits=bits_stop,
                bytesize=bits_data,
                timeout=timeout,
            )
            setattr(self, cible, conn)
            self.noms_appareils[cible] = port
            logger.info("%s connected on %s", cible.upper(), port)
            return True
        except serial.SerialException as exc:
            msg = f"Unable to open {port} ({cible}): {exc}"
            logger.error(msg)
            self._ajouter_erreur(msg)
            return False

    def connecter_gpib(self, adresse_visa: str) -> bool:
        """
        Connecte un instrument GPIB via PyVISA.
        Exemple : 'GPIB0::22::INSTR'
        """
        if not PYVISA_DISPONIBLE:
            self._ajouter_erreur("pyvisa is not installed.")
            return False
        try:
            self.gpib_rm = pyvisa.ResourceManager()
            self.gpib_instr = self.gpib_rm.open_resource(adresse_visa)
            self.gpib_instr.timeout = int(TIMEOUT_PORT_DEFAULT * 1000)
            idn = self.gpib_instr.query("*IDN?").strip()
            self.noms_appareils["gpib"] = idn
            logger.info("GPIB connected — instrument: %s", idn)
            return True
        except Exception as exc:
            msg = f"GPIB connection failed ({adresse_visa}): {exc}"
            logger.error(msg)
            self._ajouter_erreur(msg)
            return False

    def deconnecter_serie(self, cible: str) -> None:
        """Ferme proprement un port série."""
        port = getattr(self, cible, None)
        if port and port.is_open:
            port.close()
            setattr(self, cible, None)
            self.noms_appareils.pop(cible, None)
            logger.info("%s déconnecté.", cible.upper())

    def fermer_tout(self) -> None:
        """Ferme tous les ports ouverts."""
        self.arreter_backboard()
        for cible in ("com1", "com2", "thermo1"):
            self.deconnecter_serie(cible)
        if self.gpib_instr:
            try:
                self.gpib_instr.close()
                logger.info("GPIB fermé.")
            except Exception:
                pass
        if self.gpib_rm:
            try:
                self.gpib_rm.close()
            except Exception:
                pass

    # ── Backboard (vérification continue) ────────────────────────────────────

    def demarrer_backboard(self, callback_erreur: Optional[Callable[[str], None]] = None) -> None:
        """
        Lance la surveillance continue des ports dans un thread dédié.
        callback_erreur(msg) est appelé depuis le thread si un port tombe.
        """
        self._backboard_actif = True
        self._thread_backboard = threading.Thread(
            target=self._boucle_backboard,
            args=(callback_erreur,),
            daemon=True,
            name="thread-backboard",
        )
        self._thread_backboard.start()
        logger.info("Backboard démarré.")

    def arreter_backboard(self) -> None:
        self._backboard_actif = False
        logger.info("Backboard arrêté.")

    @property
    def backboard_actif(self) -> bool:
        """État public de la surveillance continue des ports."""
        return self._backboard_actif

    def _boucle_backboard(self, callback_erreur: Optional[Callable[[str], None]]) -> None:
        while self._backboard_actif:
            erreurs = self._verifier_ports()
            for msg in erreurs:
                logger.warning("BACKBOARD : %s", msg)
                if callback_erreur:
                    callback_erreur(msg)
            time.sleep(POLL_INTERVAL_S)

    def _verifier_ports(self) -> List[str]:
        erreurs = []
        with self._verrou:
            for nom in ("com1", "com2", "thermo1"):
                port = getattr(self, nom)
                if port is not None:
                    try:
                        if not port.is_open:
                            erreurs.append(f"{nom.upper()} port lost — reconnection required.")
                    except Exception as exc:
                        erreurs.append(f"{nom.upper()} port error: {exc}")
        return erreurs

    def _ajouter_erreur(self, msg: str) -> None:
        with self._verrou:
            self._erreurs.append(msg)

    def get_erreurs(self) -> List[str]:
        with self._verrou:
            return list(self._erreurs)

    def get_noms_appareils(self) -> Dict[str, str]:
        return dict(self.noms_appareils)

    def lire_thermo(self) -> Tuple[float, float]:
        """
        Lit T (°C) et HR (%) depuis Thermo1.
        Retourne (T_float, HR_float). Simule si non connecté.
        Protocole attendu : réponse ASCII "T=23.5,HR=48.2\r\n"
        """
        if self.mode_simulation:
            temperature = 20.0 + self._simulation_random.gauss(0.0, 0.08)
            humidity = 50.0 + self._simulation_random.gauss(0.0, 0.25)
            return round(temperature, 2), round(humidity, 2)
        if self.thermo1 is None or not self.thermo1.is_open:
            raise RuntimeError("Thermohygrometer is not connected.")
        try:
            self.thermo1.write(b"READ?\r\n")
            ligne = self.thermo1.readline().decode("ascii", errors="replace").strip()
            # Format "T=23.5,HR=48.2"
            parties = dict(p.split("=") for p in ligne.split(","))
            t  = float(parties.get("T",  "20.0"))
            hr = float(parties.get("HR", "50.0"))
            return (t, hr)
        except Exception as exc:
            logger.error("Thermohygrometer read failed: %s", exc)
            raise RuntimeError("Thermohygrometer read failed.") from exc

    def lire_com(self, cible: str) -> Optional[float]:
        """
        Lit une mesure depuis COM1 ou COM2 (multimètre).
        Retourne float ou None si échec.
        Protocole attendu : réponse ASCII numérique "1.2345E-3\r\n"
        """
        port = getattr(self, cible, None)
        if self.mode_simulation:
            self._simulation_index += 1
            base = 1.000 if cible == "com1" else 1.200
            drift = (self._simulation_index % 30) * 0.00002
            noise = self._simulation_random.gauss(0.0, 0.0015)
            return round(base + drift + noise, 6)
        if port is None or not port.is_open:
            logger.error("Cannot read %s: instrument is not connected.", cible.upper())
            return None
        try:
            port.write(b"READ?\r\n")
            reponse = port.readline().decode("ascii", errors="replace").strip()
            return float(reponse)
        except Exception as exc:
            logger.warning("lire_com %s erreur : %s", cible, exc)
            return None
