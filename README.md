# IPQ/LFR — Calibration des photomètres et luximètres

Application de bureau Python pour le **Laboratório de Fotometria e Radiometria** de l'**Instituto Português da Qualidade (IPQ)**. Elle pilote l'acquisition, le traitement statistique et l'export Excel des données de calibration des photomètres et luximètres.

---

## Table des matières

- [Aperçu](#aperçu)
- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Lancement](#lancement)
- [Workflow opérateur](#workflow-opérateur)
  - [1. Connexion](#1-connexion)
  - [2. Initialisation](#2-initialisation)
  - [3. Mesurage](#3-mesurage)
- [Structure du projet](#structure-du-projet)
- [Export Excel](#export-excel)
- [Mode simulation](#mode-simulation)
- [Sécurité administrateur](#sécurité-administrateur)
- [Tests](#tests)
- [Instruments supportés](#instruments-supportés)

---

## Aperçu

L'application remplace un programme LabVIEW historique. Elle effectue :

1. **L'initialisation** — deux acquisitions de 30 points sur COM1 et COM2 (multimètres), avec lecture simultanée de la température et de l'humidité relative.
2. **Le mesurage** — N séries de 30 acquisitions espacées par un délai inter-série configurable (60 s par défaut, avec signal sonore).
3. **L'export automatique** en Excel (`.xlsx`) : 30 points bruts + synthèse (moyenne, variance de population, T moy, HR moy, distance, date, heure).

---

## Architecture

Le projet suit le patron **MVC** :

```
main.py              Point d'entrée, gestion DPI Windows
├── views/           Vue (Tkinter) — fenêtre principale, thème, moniteur temps réel
├── controllers/     Contrôleurs — orchestration sans widgets
│   ├── connexion_controller.py
│   ├── init_controller.py
│   ├── mesure_controller.py
│   ├── thermo_controller.py
│   └── admin_controller.py
├── models/          Modèles — logique métier et données
│   ├── acquisition.py     Boucle 30 points + stats
│   ├── calibration.py     Boucle X séries + audio
│   ├── detection.py       Détection automatique COM/VISA
│   ├── export_xls.py      Export Excel multi-séries
│   ├── ports.py           Abstraction RS-232 / GPIB-VISA
│   ├── initialisation.py  État global d'initialisation
│   ├── stats.py           Calculs métrologiques (moyenne, variance)
│   ├── audit.py           Journal des événements
│   ├── security.py        Clé administrateur (hachage PBKDF2)
│   ├── thermo.py          Pilote Hart Scientific 1620 (RS-232)
│   └── thermo_ruska.py    Pilote Ruska (RS-232)
└── core/
    ├── config.py    Constantes (baud, NB_POINTS=30, délais…)
    ├── logger.py    Configuration des journaux
    └── paths.py     Chemins système (bureau, noms de fichiers)
```

---

## Prérequis

| Composant | Version minimale |
|-----------|-----------------|
| Python    | 3.8             |
| pyserial  | 3.5             |
| pyvisa    | 1.12.0          |
| openpyxl  | 3.1.0           |
| numpy     | 1.24.0          |

> **Windows uniquement :** le signal sonore inter-série utilise `winsound` (inclus dans Python).  
> Sur Linux/macOS : décommenter `simpleaudio>=1.0.4` dans `requirements.txt`.

---

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/houblou/ipq-lfr-calibration-mvc.git
cd ipq-lfr-calibration-mvc

# Créer un environnement virtuel (recommandé)
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# Installer les dépendances
pip install -r requirements.txt
```

---

## Lancement

```bash
python main.py
```

L'application détecte automatiquement le DPI de l'écran et ajuste l'interface en conséquence (Windows 10/11).

---

## Workflow opérateur

### 1. Connexion

1. Sélectionner les ports pour **COM1**, **COM2** (multimètres Agilent 34401A) et **Thermo1** (Hart Scientific 1620) dans les listes déroulantes.  
   Le bouton **Auto-detect** scanne tous les ports COM disponibles et identifie automatiquement les instruments.
2. Renseigner le **nom de l'opérateur** et l'**identifiant de la fiche** de calibration.
3. Cliquer **Valider** : crée le fichier Excel de session sur le bureau.

### 2. Initialisation

1. Lancer l'acquisition sur **COM1** puis **COM2** (ou les deux en séquence automatique).  
   Chaque acquisition collecte **30 points** espacés de ~0,9 s, avec lecture de T et HR à chaque point.
2. Saisir la **distance source–détecteur** (mm).
3. Cliquer **Approuver** : exporte les deux colonnes d'initialisation dans l'Excel et déverrouille l'onglet Mesurage.

### 3. Mesurage

1. Choisir le nombre de **séries X** et le **canal** (COM1 ou COM2).
2. Cliquer **Démarrer** : la boucle exécute X séries de 30 acquisitions.  
   Entre deux séries : attente de 60 s avec bip sonore progressif (700 Hz → 1400 Hz).
3. Chaque série est immédiatement exportée dans une nouvelle colonne Excel.
4. Le bouton **Arrêter** interrompt proprement la boucle après la série en cours.

---

## Structure du projet

```
ipq-lfr-calibration-mvc/
├── main.py
├── requirements.txt
├── controllers/
├── core/
├── models/
├── views/
└── tests/
    ├── test_metrologie.py     Tests unitaires (stats, Excel, sécurité, simulation)
    └── test_integration.py    Tests d'intégration
```

---

## Export Excel

Le fichier généré suit la structure suivante :

| Ligne | Colonne A (étiquette) | Colonnes B, C, … (séries) |
|-------|-----------------------|--------------------------|
| 1 | `i` | En-tête de série |
| 2–31 | — | N[1] à N[30] (points bruts) |
| 32 | `MEAN` | Moyenne M |
| 33 | `VARIANCE` | Variance de population V |
| 34 | `Mean T (°C)` | Température moyenne |
| 35 | `Mean RH (%)` | Humidité relative moyenne |
| 36 | `Distance (mm)` | Distance source–détecteur |
| 37 | `Date` | Date de début |
| 38 | `Start time` | Heure de début |
| 39 | `Operator` | Nom de l'opérateur |

> Les deux premières colonnes de données (B et C) correspondent aux acquisitions d'initialisation COM1 et COM2. Les colonnes suivantes correspondent aux séries de mesurage.

---

## Mode simulation

En l'absence d'instruments physiques, l'application peut fonctionner en **mode simulation** : les lectures COM retournent des valeurs synthétiques aléatoires réalistes. Le fichier Excel est alors créé dans un dossier `IPQ_LFR_Simulation` sur le bureau et porte la mention **SIMULATION DATA — NOT VALID FOR METROLOGY**.

---

## Sécurité administrateur

Certaines fonctions sont protégées par une clé administrateur stockée sous forme de hash PBKDF2-SHA256 dans `%APPDATA%\IPQ_LFR\security.json` (jamais en clair).

Pour configurer la clé :

```bash
python -m models.security
```

La clé doit contenir **au moins 12 caractères**.

---

## Tests

```bash
python -m pytest tests/
```

Les tests couvrent :
- Les calculs métrologiques (moyenne et variance de population, gestion des points invalides)
- L'export Excel (structure des colonnes, rejet des séries incomplètes)
- Le stockage et la vérification de la clé administrateur
- La gestion du mode simulation dans `GestionPorts`
- La gestion des erreurs dans `BoucleCalibration`

---

## Instruments supportés

| Rôle | Instrument | Interface |
|------|-----------|-----------|
| Multimètre (COM1) | Agilent 34401A | RS-232 (SCPI) ou GPIB/VISA |
| Multimètre (COM2) | Agilent 34401A | RS-232 (SCPI) ou GPIB/VISA |
| Thermohygromètre | Hart Scientific 1620 | RS-232 (ASCII) |
| Thermohygromètre (alternatif) | Ruska | RS-232 |

La détection automatique teste les combinaisons de baudrate (9600, 19200, 38400, 57600), parité (N/E/O), bits de stop (1/2) et RTS/CTS pour identifier les instruments sans configuration manuelle.
