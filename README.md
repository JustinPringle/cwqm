# CWQM — Coastal Water Quality Model

A 1-D advection-diffusion model for predicting *E. coli* concentrations along the Durban coastline (South Africa). Observations from the obscape.com weather network and beach monitoring databases are assimilated in real-time using an Ensemble Kalman Filter.

Results are served to the public-facing PWA at [wozolwandle.com](https://wozolwandle.com).

---

## How it works

```
Weather (obscape API)   ──┐
GFS Forecast (Open-Meteo)─┤
Umgeni River flow         ├──► forcing/weather.csv
                           │   forcing/umgeni_flow.csv
E. coli observations ──────┼──► observations/observations.csv
(internal DB)              │
                           ▼
                    model.run()   ← Kalman Filter + advection-diffusion
                           │
                    results/      → SQL DB → PHP JSON → PWA
```

Each coastal cell exchanges *E. coli* with its neighbours via wind-driven advection. Storm-water discharges (SWDs) and the Umgeni River inject bacteria. Decay is parameterised by a first-order time scale `Td`. The Kalman Filter corrects predictions whenever beach observations are available.

---

## Project structure

```
cwqm/
├── main.py                  # Live operational run (API fetch → model → SQL push)
├── run_dry.py               # Offline test run using existing CSV files
├── run_historical.py        # Hindcast run (Jan 2025 – Mar 2026)
├── run_forecast.py          # 7-day GFS forecast run
│
├── model.py                 # Core simulation + Kalman filter
├── forcingSort.py           # GFS forecast fetch (Open-Meteo) + raw weather formatting
├── obscape.py               # obscape.com weather observation API client
├── processObs.py            # E. coli observation database client
├── pretreatment.py          # CSV readers for all input files
├── postTreatment.py         # Results → SQL database writer
├── utils.py                 # Grid utilities (cell lookup, wind projection, Umgeni flows)
│
├── model_ini.ini            # Master configuration (all file paths)
├── param_files/
│   ├── params.txt           # Global model parameters (Cac, Td, dT)
│   ├── cells.csv            # Grid cell geometry (UTM coords, bearing, length)
│   └── inputs.csv           # Storm-water discharge locations and E. coli loads
├── forcing/
│   ├── weather.csv          # Runtime: hourly wind speed, direction, rain
│   └── umgeni_flow.csv      # Runtime: hourly Umgeni River flow (m³/s)
├── observations/
│   ├── obLocs.csv           # Beach observation locations (UTM coords)
│   └── observations.csv     # Runtime: hourly E. coli observations (-9 = missing)
├── start_files/
│   ├── init_c.csv           # Initial E. coli concentrations per cell
│   ├── init_C.csv           # Saved model state from previous run
│   └── p.out                # Saved error covariance matrix from previous run
└── test_changes.py          # 44-test pytest suite
```

---

## Setup

### Dependencies

```bash
pip install numpy scipy pandas tqdm fuzzywuzzy sqlalchemy mysql-connector-python
```

> **Note:** GFS forecast data is fetched from [Open-Meteo](https://open-meteo.com/) — no API key or extra packages required. The old `getgfs`/NOMADS OpenDAP service was permanently shut down on 24 Feb 2026.

### Environment variables

The obscape API credentials are read from the environment:

```bash
export OBSCAPE_USERNAME=Justin
export OBSCAPE_API_KEY=your_key_here
```

---

## Running the model

### Dry run (no network, no database)

Uses existing CSV files in `forcing/` and `observations/`. Good for testing after code changes.

```bash
python run_dry.py
# Output: results/wq_by_beach.csv, results/wq_all_cells.csv, results/run_summary.txt
```

### Hindcast (historical period)

Fetches obscape weather data and E. coli observations from the database for a defined period, runs the model, and saves results locally without pushing to the database.

```bash
python run_historical.py
# Output: results_historical/
```

Edit `START` / `END` at the top of the script to change the period.

### Forecast

Hot-starts from the final state of the historical run and fetches a GFS forecast via Open-Meteo.

```bash
python run_forecast.py
# Output: results_forecast/
```

Edit `FORECAST_END` at the top of the script to change the target end date.

### Live operational run

Fetches current observations and a 48-hour GFS forecast, runs the model, pushes results to the SQL database, and triggers the PHP JSON generator.

```bash
python main.py
```

---

## Configuration (`model_ini.ini`)

| Key | Description |
|---|---|
| `fileParams` | Global model parameters (Cac, Td, dT) |
| `fileGrid` | Grid cell geometry |
| `fileInitC` | Initial E. coli concentrations |
| `fileWeatherForcing` | Hourly wind speed, direction, rain |
| `fileRivers` | JSON list of river flow CSV paths |
| `fileInputs` | Storm-water discharge locations |
| `fileObsLocs` | Beach observation locations |
| `fileObs` | Hourly E. coli observations |
| `fileCov` | Error covariance matrix (P) |

---

## Testing

```bash
pytest test_changes.py -v
```

44 tests covering: cell lookup, wind projection, wind-direction bug fixes, model constants, Kalman filter update, HTTP error handling (mocked), obscape formatting, GFS NaN fallback, and WQ classification thresholds.

---

## Water quality classification

| Class | E. coli (CFU / 100 mL) |
|---|---|
| Good | < 250 |
| Accept | 250 – 499 |
| Bad | ≥ 500 |

Thresholds are defined as `_WQ_GOOD_THRESHOLD` and `_WQ_ACCEPT_THRESHOLD` in `postTreatment.py`.

---

## Coordinate system

Grid cells are in **UTM Zone 36S** (EPSG:32736, metres). Observation and input locations in `obLocs.csv` and `inputs.csv` must use the same projection.

---

## Acknowledgements

- Mardon (2003) — monthly Umgeni base-flow estimates
- NOAA GFS via [Open-Meteo](https://open-meteo.com/)
- [obscape.com](https://obscape.com) — coastal weather station network
