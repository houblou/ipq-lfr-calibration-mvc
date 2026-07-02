# -*- coding: utf-8 -*-
"""models/ports.py — GestionPorts : découverte, connexion et surveillance des ports (sans Tkinter).

Bus HYBRIDE : ports série (pyserial, COMx) et ressources VISA (pyvisa, GPIB…) unifiés.
On sélectionne indifféremment un instrument série ou GPIB dans le même menu ; le bus
est détecté automatiquement d'après l'adresse, et chaque rôle parle sa propre commande.
"""
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
        self.com1:         Optional[object] = None
        self.com2:         Optional[object] = None
        self.thermo1:      Optional[object] = None
        self.gpib_rm:      Optional[object] = None
        self.noms_appareils: Dict[str, str] = {}   # 'com1' -> 'COM3' ou 'GPIB0::8::INSTR'
        self._bus: Dict[str, str] = {}             # 'com1' -> 'serial' | 'visa'
        self._identites: Dict[str, str] = {}       # 'com1' -> 'HP3458A' (best-effort)
        self._cmd_mesure: Dict[str, str] = {}      # 'com1' -> 'READ?' (commande de mesure par rôle)

        # Source du thermohygromètre : 'ascii' (trame "T=..,HR=.."), 'ruska'
        # (RUSKA 2456-LEM, protocole binaire) ou 'manuel' (valeurs saisies).
        self.thermo_mode: str = "ruska"
        self._thermo_manuel: Optional[Tuple[float, float]] = None

        self._backboard_actif: bool = False
        self._thread_backboard: Optional[threading.Thread] = None
        self._erreurs: List[str] = []
        self._verrou = threading.Lock()       # protège la PUBLICATION d'état (attributs/dicts)
        self._io_lock = threading.Lock()      # C2 : sérialise les I/O instrument (thermo ↔ acquisition)
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

    def lister_instruments(self) -> List[str]:
        """
        Liste HYBRIDE : ports série (COMx) + ressources VISA (GPIB0::8::INSTR…).
        C'est cette liste qui peuple les menus déroulants de la page connexion :
        on y sélectionne indifféremment un instrument série ou GPIB.
        """
        return self.lister_ports_serie() + self.lister_ressources_visa()

    @staticmethod
    def _est_visa(adresse: str) -> bool:
        """True si l'adresse est une ressource VISA (contient '::'), sinon port série."""
        return "::" in adresse

    @staticmethod
    def _est_identite(reponse: str) -> bool:
        """
        True si la réponse ressemble à une identité (contient du texte), False si
        c'est un simple nombre. Un instrument en mode mesure (ex. HP 3458A) répond
        à *IDN? par une valeur numérique : ce n'est PAS une identité.
        """
        if not reponse:
            return False
        try:
            float(reponse.split(",")[0])
            return False   # nombre seul -> une mesure, pas un identifiant
        except ValueError:
            return True    # contient des lettres -> identité plausible

    def _identifier_visa(self, inst) -> str:
        """
        Identité propre d'un instrument VISA : *IDN? (SCPI) puis ID? (HP pré-SCPI
        type 3458A). On ignore une réponse purement numérique (= mesure poussée) et
        on bascule sur ID?. Best-effort : ne lève jamais, laisse read_termination='\\n'.
        """
        try:
            for cmd in ("*IDN?", "ID?"):
                for term in ("\n", "\r\n"):
                    inst.read_termination = term
                    try:
                        rep = inst.query(cmd).strip()
                    except Exception:
                        continue
                    if self._est_identite(rep):
                        return rep
        finally:
            inst.read_termination = "\n"
        return ""

    def definir_commande_mesure(self, cible: str, commande: str) -> None:
        """
        Configure la commande de mesure d'un rôle (com1/com2/thermo1).
        'READ?' pour un multimètre SCPI, '' (vide) pour lire en continu un
        HP 3458A (inst.read() sans commande), 'FETCH?' pour un compteur…
        """
        self._cmd_mesure[cible] = (commande or "").strip()
        logger.info("Commande de mesure %s = %r", cible.upper(), self._cmd_mesure[cible])

    def get_commande_mesure(self, cible: str) -> str:
        """Commande de mesure configurée pour ce rôle (défaut 'READ?')."""
        return self._cmd_mesure.get(cible, "READ?")

    def get_identite(self, cible: str) -> str:
        """Identité lue à la connexion (ex. 'HP3458A'), ou '' si non identifiée."""
        return self._identites.get(cible, "")

    # ── Source thermohygromètre ────────────────────────────────────────────────

    def set_thermo_mode(self, mode: str) -> None:
        """Choisit la source T/HR : 'ascii' | 'ruska' | 'manuel'."""
        self.thermo_mode = mode if mode in ("ascii", "ruska", "manuel") else "ascii"
        logger.info("Thermo mode = %s", self.thermo_mode)

    def set_thermo_manuel(self, t: float, hr: float) -> None:
        """Fixe les valeurs T/HR saisies manuellement (mode 'manuel')."""
        self._thermo_manuel = (float(t), float(hr))
        logger.info("Thermo manuel = T %.2f °C  RH %.2f %%", t, hr)

    def thermo_actif(self) -> bool:
        """True si une source T/HR est exploitable (sim, manuel, ou instrument connecté)."""
        if self.mode_simulation or self.thermo_mode == "manuel":
            return True
        return self.role_connecte("thermo1")

    def role_connecte(self, cible: str) -> bool:
        """
        True si le rôle (com1/com2/thermo1) est exploitable, quel que soit le bus.
        Série : port ouvert. VISA : ressource présente (pas d'attribut is_open).
        À utiliser au lieu de tester `.is_open` directement (qui plante sur VISA).
        """
        port = getattr(self, cible, None)
        if port is None:
            return False
        if self._bus.get(cible) == "serial":
            try:
                return bool(port.is_open)
            except Exception:
                return False
        return True   # VISA : présent = exploitable

    # ── Connexions ────────────────────────────────────────────────────────────

    def connecter(self, adresse: str, cible: str) -> bool:
        """
        Connexion unifiée : détecte automatiquement le bus d'après l'adresse.
        'COM3' -> série ;  'GPIB0::8::INSTR' -> VISA.
        cible : 'com1', 'com2' ou 'thermo1'.
        """
        # C1 : si le rôle est déjà connecté (reconnexion via le menu), fermer d'abord.
        self.deconnecter(cible)
        if self._est_visa(adresse):
            return self._connecter_visa(adresse, cible)
        return self.connecter_serie(adresse, cible)

    def _connecter_visa(self, adresse: str, cible: str) -> bool:
        """Ouvre un instrument VISA et l'affecte à la cible (com1/com2/thermo1)."""
        if not PYVISA_DISPONIBLE:
            self._ajouter_erreur("pyvisa is not installed.")
            return False
        inst = None
        try:
            if self.gpib_rm is None:
                self.gpib_rm = pyvisa.ResourceManager()
            inst = self.gpib_rm.open_resource(adresse)
            inst.timeout = int(TIMEOUT_PORT_DEFAULT * 1000)
            inst.write_termination = "\n"
            inst.read_termination = "\n"
            inst.send_end = True
            idn = self._identifier_visa(inst)   # identité propre (best-effort, ID? pour le 3458A)
            with self._verrou:                  # T1 : publication de l'état sous verrou
                setattr(self, cible, inst)
                self._bus[cible] = "visa"
                self.noms_appareils[cible] = adresse   # nommé simplement par son adresse
                if idn:
                    self._identites[cible] = idn
            logger.info("%s connected on %s%s", cible.upper(), adresse,
                        f" ({idn})" if idn else "")
            return True
        except Exception as exc:
            # C2 : ressource ouverte mais config/identification échouée -> on ferme.
            if inst is not None:
                try:
                    inst.close()
                except Exception:
                    pass
            msg = f"Unable to open {adresse} ({cible}): {exc}"
            logger.error(msg)
            self._ajouter_erreur(msg)
            return False

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
            with self._verrou:   # T1 : publication de l'état sous verrou
                setattr(self, cible, conn)
                self._bus[cible] = "serial"
                self.noms_appareils[cible] = port
            logger.info("%s connected on %s", cible.upper(), port)
            return True
        except serial.SerialException as exc:
            msg = f"Unable to open {port} ({cible}): {exc}"
            logger.error(msg)
            self._ajouter_erreur(msg)
            return False

    def deconnecter(self, cible: str) -> None:
        """Ferme proprement une cible, qu'elle soit série ou VISA."""
        # On efface l'état sous verrou (le backboard voit aussitôt None), PUIS on
        # ferme l'I/O HORS verrou — D : close() sur GPIB legacy peut bloquer, il ne
        # doit pas retenir _verrou pendant que le backboard/join l'attend.
        with self._verrou:
            obj = getattr(self, cible, None)
            if obj is None:
                return
            bus = self._bus.get(cible)
            setattr(self, cible, None)
            self.noms_appareils.pop(cible, None)
            self._bus.pop(cible, None)
            self._identites.pop(cible, None)
            self._cmd_mesure.pop(cible, None)
        try:
            if bus == "serial":
                if obj.is_open:
                    obj.close()
            else:
                obj.close()
        except Exception:
            pass
        logger.info("%s déconnecté.", cible.upper())

    def fermer_tout(self) -> None:
        """Ferme tous les ports ouverts (série + VISA)."""
        self.arreter_backboard()
        for cible in ("com1", "com2", "thermo1"):
            self.deconnecter(cible)
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
        if self._backboard_actif:   # T3 : idempotent, pas de second thread
            return
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
        # T2 : attendre la fin du cycle en cours avant de rendre la main, pour que
        # fermer_tout ne ferme pas un port pendant que le backboard le vérifie.
        thread = self._thread_backboard
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=POLL_INTERVAL_S * 2 + 0.5)
        self._thread_backboard = None
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
                # La vérification is_open ne concerne que le série ; les ressources
                # VISA n'exposent pas cet attribut et sont considérées vivantes ici.
                if port is not None and self._bus.get(nom) == "serial":
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
        Lit T (°C) et HR (%) depuis Thermo1 selon `thermo_mode` :
          'manuel' -> valeurs saisies ; 'ruska' -> driver binaire RUSKA 2456-LEM ;
          'ascii'  -> trame ASCII "T=23.5,HR=48.2". Simule si mode_simulation.
        """
        if self.mode_simulation:
            temperature = 20.0 + self._simulation_random.gauss(0.0, 0.08)
            humidity = 50.0 + self._simulation_random.gauss(0.0, 0.25)
            return round(temperature, 2), round(humidity, 2)
        if self.thermo_mode == "manuel":
            if self._thermo_manuel is None:
                raise RuntimeError("Manual T/RH values not set.")
            return self._thermo_manuel
        if self.thermo1 is None:
            raise RuntimeError("Thermohygrometer is not connected.")
        if self.thermo_mode == "ruska":
            try:
                from models import thermo_ruska
                with self._io_lock:   # C : sérialise l'I/O instrument
                    t, hr, _pression = thermo_ruska.lire(self.thermo1)
                return (t, hr)
            except Exception as exc:
                logger.error("RUSKA read failed: %s", exc)
                raise RuntimeError("RUSKA read failed.") from exc
        cmd = self._cmd_mesure.get("thermo1", "READ?")   # mode ASCII (placeholder générique)
        try:
            with self._io_lock:   # C : sérialise l'I/O instrument
                if self._bus.get("thermo1") == "visa":
                    ligne = self.thermo1.read().strip() if cmd == "" else self.thermo1.query(cmd).strip()
                else:
                    if not self.thermo1.is_open:
                        raise RuntimeError("Thermohygrometer is not connected.")
                    if cmd:
                        self.thermo1.write((cmd + "\r\n").encode("ascii"))
                    ligne = self.thermo1.readline().decode("ascii", errors="replace").strip()
            # E2 : pas de valeur de repli fabriquée — une trame partielle doit
            # échouer, jamais livrer une fausse mesure (contexte métrologique).
            parties = dict(p.split("=", 1) for p in ligne.split(",") if "=" in p)
            if "T" not in parties or "HR" not in parties:
                raise ValueError(f"Unexpected thermo frame: {ligne!r}")
            t  = float(parties["T"])
            hr = float(parties["HR"])
            return (t, hr)
        except Exception as exc:
            logger.error("Thermohygrometer read failed: %s", exc)
            raise RuntimeError("Thermohygrometer read failed.") from exc

    def lire_com(self, cible: str) -> Optional[float]:
        """
        Lit une mesure depuis un multimètre (cible 'com1'/'com2'), série ou VISA.
        Retourne float ou None si échec. Commande de mesure configurable par rôle.
        """
        port = getattr(self, cible, None)
        if self.mode_simulation:
            self._simulation_index += 1
            base = 1.000 if cible == "com1" else 1.200
            drift = (self._simulation_index % 30) * 0.00002
            noise = self._simulation_random.gauss(0.0, 0.0015)
            return round(base + drift + noise, 6)
        if port is None:
            logger.error("Cannot read %s: instrument is not connected.", cible.upper())
            return None
        cmd = self._cmd_mesure.get(cible, "READ?")   # commande de mesure configurable par rôle
        try:
            with self._io_lock:   # C : sérialise l'I/O instrument (thermo ↔ acquisition)
                if self._bus.get(cible) == "visa":
                    # Commande vide -> lecture continue (HP 3458A en TRIG AUTO pousse la valeur).
                    reponse = port.read().strip() if cmd == "" else port.query(cmd).strip()
                else:
                    if not port.is_open:
                        logger.error("Cannot read %s: instrument is not connected.", cible.upper())
                        return None
                    if cmd:
                        port.write((cmd + "\r\n").encode("ascii"))
                    reponse = port.readline().decode("ascii", errors="replace").strip()
            return float(reponse)
        except Exception as exc:
            logger.warning("lire_com %s erreur : %s", cible, exc)
            return None
