IPQ/LFR — Photometer & Luxmeter Calibration
A Python desktop application for the Laboratory of Photometry and Radiometry at the Instituto Português da Qualidade (IPQ). It drives instrument communication, statistical processing, and Excel export for photometer and luxmeter calibration workflows.

Table of Contents
Overview
Architecture
Requirements
Installation
Running the Application
Operator Workflow
Excel Output
Simulation Mode
Administrator Security
Tests
Supported Instruments
Overview
This application replaces a legacy LabVIEW program and performs three main phases:

Initialization — two 30-point acquisitions on COM1 and COM2 (multimeters), with simultaneous temperature and relative humidity readings.
Measurement — N series of 30 acquisitions, separated by a configurable inter-series delay (60 s by default) with an audio countdown.
Automatic Excel export — 30 raw data points per series plus a summary row (mean, population variance, mean temperature, mean RH, distance, date, time).
Architecture
The project follows the MVC pattern:

Code
main.py                   Entry point, Windows DPI scaling
├── views/                View layer (Tkinter) — main window, theme, live monitor
├── controllers/          Controllers — UI-free orchestration logic
│   ├── connexion_controller.py
│   ├── init_controller.py
│   ├── mesure_controller.py
│   ├── thermo_controller.py
│   └── admin_controller.py
├── models/               Business logic and data
│   ├── acquisition.py        30-point loop + statistics
│   ├── calibration.py        X-series loop + audio beeps
│   ├── detection.py          Automatic COM/VISA instrument detection
│   ├── export_xls.py         Multi-series Excel export
│   ├── ports.py              RS-232 / GPIB-VISA abstraction
│   ├── initialisation.py     Global initialization state
│   ├── stats.py              Metrological calculations (mean, variance)
│   ├── audit.py              Event journal
│   ├── security.py           Admin key storage (PBKDF2 hash)
│   ├── thermo.py             Hart Scientific 1620 driver (RS-232)
│   └── thermo_ruska.py       Ruska thermometer driver (RS-232)
└── core/
    ├── config.py             Constants (baud rate, NB_POINTS=30, delays…)
    ├── logger.py             Logging configuration
    └── paths.py              System paths (desktop, file naming)
Requirements
Package	Minimum version
Python	3.8
pyserial	3.5
pyvisa	1.12.0
openpyxl	3.1.0
numpy	1.24.0
Windows only: the inter-series audio countdown uses winsound (bundled with Python). On Linux/macOS: uncomment simpleaudio>=1.0.4 in requirements.txt.

Installation
bash
git clone https://github.com/houblou/ipq-lfr-calibration-mvc.git
cd ipq-lfr-calibration-mvc

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
Running the Application
bash
python main.py
On Windows 10/11, the application automatically detects the display DPI and scales the interface accordingly.

Operator Workflow
1. Connection
Select the ports for COM1, COM2 (Agilent 34401A multimeters) and Thermo1 (Hart Scientific 1620) from the drop-down lists. Use Auto-detect to scan all available COM ports and identify instruments automatically.
Enter the operator name and the calibration record identifier.
Click Validate — this creates the Excel session file on the desktop.
2. Initialization
Start the acquisition on COM1 then COM2 (or both in automatic sequence). Each acquisition collects 30 points at ~0.9 s intervals, with a T/RH reading at every point.
Enter the source-to-detector distance (mm).
Click Approve — this exports the two initialization columns to Excel and unlocks the Measurement tab.
3. Measurement
Set the number of series X and choose the target channel (COM1 or COM2).
Click Start — the loop runs X series of 30 acquisitions. Between series: 60 s wait with a progressive audio beep (700 Hz → 1400 Hz).
Each completed series is immediately exported to a new Excel column.
Click Stop to interrupt the loop cleanly after the current series finishes.
Excel Output
Row	Column A (label)	Columns B, C, … (series data)
1	i	Series header
2–31	—	N[1] to N[30] (raw points)
32	MEAN	Mean M
33	VARIANCE	Population variance V
34	Mean T (°C)	Mean temperature
35	Mean RH (%)	Mean relative humidity
36	Distance (mm)	Source-to-detector distance
37	Date	Start date
38	Start time	Start time
39	Operator	Operator name
The first two data columns (B and C) are the COM1 and COM2 initialization acquisitions. All subsequent columns are measurement series.

Simulation Mode
When no physical instruments are connected, the application can run in simulation mode: COM readings return realistic synthetic values. The Excel file is saved to an IPQ_LFR_Simulation folder on the desktop and is clearly marked SIMULATION DATA — NOT VALID FOR METROLOGY.

Administrator Security
Restricted application features are protected by an administrator key stored as a PBKDF2-SHA256 hash in %APPDATA%\IPQ_LFR\security.json — never in plain text.

To configure the key:

bash
python -m models.security
The key must be at least 12 characters long.

Tests
bash
python -m pytest tests/
Test coverage includes:

Metrological calculations (mean, population variance, handling of invalid points)
Excel export structure and rejection of incomplete series
Administrator key hashing and verification
Simulation mode behaviour in GestionPorts
Error handling in BoucleCalibration
Supported Instruments
Role	Instrument	Interface
Multimeter (COM1)	Agilent 34401A	RS-232 (SCPI) or GPIB/VISA
Multimeter (COM2)	Agilent 34401A	RS-232 (SCPI) or GPIB/VISA
Thermohygrometer	Hart Scientific 1620	RS-232 (ASCII)
Thermohygrometer (alt.)	Ruska	RS-232
Auto-detection tests every combination of baud rate (9600 / 19200 / 38400 / 57600), parity (N/E/O), stop bits (1/2), and RTS/CTS to identify instruments without manual configuration.

