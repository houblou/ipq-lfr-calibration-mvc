# -*- coding: utf-8 -*-
"""models/thermo_ruska.py — driver RUSKA 2456-LEM (moniteur d'environnement).

Protocole série binaire vérifié sur l'appareil réel (voir device.py de référence) :
  9600 8N1, RTS=True (critique), DTR=False (critique — DTR haut supprime les réponses).
  Commande R (référence calibrée) : TX 26 00 01 52 75
    RX 25 00 07 72 <temp:i16LE> <rh:i16LE> <press:i16LE> <chk>  (valeurs ×100)

Fonctionne sur un serial.Serial DÉJÀ ouvert (ouvert par GestionPorts.connecter_serie) :
on force juste RTS/DTR avant la lecture.
"""
import struct

REPLY_START = 0x25              # '%'
CMD_R = bytes([0x26, 0x00, 0x01, 0x52, 0x75])   # Read Reference values (T/RH/press)


def _lrc(data: bytes) -> int:
    """XOR de tous les octets. Une trame intègre donne _lrc(trame_complète) == 0."""
    r = 0
    for b in data:
        r ^= b
    return r


def preparer_port(ser) -> None:
    """Force les lignes de contrôle attendues par le RUSKA (RTS haut, DTR bas)."""
    try:
        ser.rts = True
        ser.dtr = False
    except Exception:
        pass


def _send_recv(ser, frame: bytes, expected_cmd: str):
    """Envoie une trame, lit la réponse, renvoie le payload (ou None)."""
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(frame)
    ser.flush()

    start = ser.read(1)
    if not start or start[0] != REPLY_START:
        return None
    header = ser.read(2)
    if len(header) < 2:
        return None
    _, size = header
    body = ser.read(size + 1)
    if len(body) < size + 1:
        return None
    # F : rejeter une trame au checksum invalide plutôt que livrer une valeur de
    # référence corrompue (bruit RS-232). _lrc de la trame complète doit valoir 0.
    if _lrc(start + header + body) != 0:
        return None
    if chr(body[0]) != expected_cmd.lower():
        return None
    return body[1:-1]   # payload seul (sans écho de commande ni checksum)


def lire(ser):
    """
    Lecture des valeurs de référence calibrées.
    Retourne (temperature_C, humidity_pct, pressure_kPa). Lève RuntimeError si muet.
    """
    preparer_port(ser)
    p = _send_recv(ser, CMD_R, "R")
    if p is None or len(p) < 6:
        raise RuntimeError("RUSKA: no/short reply (check LEMCal is closed, RTS/DTR).")
    t, h, pr = struct.unpack_from("<hhh", p)
    return (t / 100.0, h / 100.0, pr / 100.0)
