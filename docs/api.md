# CWQM — API Reference

Full function-level documentation for all modules.

---

## `utils.py` — Grid and flow utilities

### `getDist(x1, y1, x2, y2)`

Computes the Euclidean distance between two points.

| Parameter | Type | Description |
|---|---|---|
| `x1`, `y1` | `float` | Coordinates of the first point (UTM metres) |
| `x2`, `y2` | `float` | Coordinates of the second point (UTM metres) |

**Returns** `float` — distance in metres.

---

### `findCellID(ar_cell_label, XIn, YIn, ar_coorx, ar_coory)`

Finds the grid cell whose centre is within one cell-length of the query point. If multiple cells qualify, returns the last one found. If none qualify, raises `ValueError`.

| Parameter | Type | Description |
|---|---|---|
| `ar_cell_label` | `ndarray (N,)` | Integer cell IDs |
| `XIn` | `float` | X coordinate of the query point (UTM metres) |
| `YIn` | `float` | Y coordinate of the query point (UTM metres) |
| `ar_coorx` | `ndarray (N,)` | X coordinates of cell centres |
| `ar_coory` | `ndarray (N,)` | Y coordinates of cell centres |

**Returns** `int` — label of the nearest cell.

**Raises** `ValueError` — if no cell centre is within one cell-length of `(XIn, YIn)`.

**Notes:** Cell-length `dC` is computed from the separation between cells 0 and 1, so the grid must have uniform spacing.

---

### `getWindAdv(ar_cell_label, ar_cell_bearing, ar_cell_length, wind_spd, wind_dir)`

Projects the wind velocity vector onto each cell's along-cell direction using a dot-product projection. Returns a flag (+1/−1/0) and the magnitude of the projection for each cell.

| Parameter | Type | Description |
|---|---|---|
| `ar_cell_label` | `ndarray (N,)` | Cell IDs |
| `ar_cell_bearing` | `ndarray (N,)` | Bearing of each cell clockwise from True North (degrees) |
| `ar_cell_length` | `ndarray (N,)` | Length of each cell (metres) |
| `wind_spd` | `float` | Wind speed (m/s) |
| `wind_dir` | `float` | Wind direction: direction wind is coming **from**, clockwise from North (degrees) |

**Returns** `(ar_wind_flag, ar_wind_along_cell)` — both `ndarray (N,)`.

- `ar_wind_flag`: +1 where wind has a positive along-cell component (S→N), −1 negative, 0 when calm.
- `ar_wind_along_cell`: magnitude of the wind projection onto each cell (m/s).

**Notes:** An internal 180° rotation converts the meteorological "coming from" convention to a "going to" vector before projection. Zero wind (norm_proj == 0) is guarded against division by zero.

---

### `umgeniFlows(weatherDf, period='monthly')`

Estimates hourly Umgeni River flow by combining Mardon (2003) monthly base flows with a rational-method storm-flow contribution.

| Parameter | Type | Description |
|---|---|---|
| `weatherDf` | `pd.DataFrame` | Must contain `datetime` (timezone-aware) and `rain` (mm/hr) columns |
| `period` | `str` | Reserved for future sub-monthly modes. Default `'monthly'` |

**Returns** `pd.DataFrame` with columns `datetime` and `flow` (m³/s).

**Method:**
- Base flow `bFlow` is looked up from a monthly table (Jan=15, Feb=28, … m³/s).
- Base flows are smoothed with an exponential moving average (`alpha=0.01`) to avoid step changes at month boundaries.
- Storm flow `Q = C × rain × A / 3.6` where `C=0.1` (runoff coefficient), `A=340 km²` (catchment area).
- Total flow = smoothed base flow + storm flow.

---

## `forcingSort.py` — Weather forcing

### `get_gfs(var_list=None, lat=-29.75, lon=31, forecast_length=48)`

Fetches a GFS weather forecast for a single lat/lon point from the [Open-Meteo API](https://open-meteo.com/).

> **History:** The original implementation used the NCEP NOMADS OpenDAP service (`getgfs` package). NOMADS permanently shut down OpenDAP access on 24 Feb 2026 (SCN25-81). Open-Meteo now provides the same GFS-seamless model output as JSON with no API key.

| Parameter | Type | Description |
|---|---|---|
| `var_list` | ignored | Kept for backward compatibility with old NOMADS-based calls |
| `lat` | `float` | Latitude of the forecast point. Default `-29.75` (Durban) |
| `lon` | `float` | Longitude of the forecast point. Default `31` |
| `forecast_length` | `int` | Number of hourly time steps to return. Default `48` |

**Returns** `pd.DataFrame` with columns:

| Column | Units | Description |
|---|---|---|
| `datetime` | UTC timezone-aware | Hourly forecast timestamps |
| `wind_speed` | m/s | 10-metre wind speed |
| `direction` | degrees from N | Meteorological wind direction (direction wind is coming *from*) |
| `rain` | mm/hr | Precipitation |

**Raises** `RuntimeError` on HTTP or connection errors.

**Notes:** Open-Meteo works in whole forecast days. `forecast_days = ceil(forecast_length/24) + 1`, capped at 16 days. `None` values in the API response are replaced with `np.nan` (wind) or `0.0` (rain).

---

### `read_raw_weather(fileName)`

Reads a raw CSV weather file exported from an obscape station (timestamp in Unix seconds UTC).

| Parameter | Type | Description |
|---|---|---|
| `fileName` | `str` | Full path to the raw weather CSV |

**Returns** `pd.DataFrame` with columns `datetime` (Africa/Johannesburg timezone-aware), `Rainfall intensity [mm]`, `Wind speed [m/s]`, `Wind direction [deg N]`.

---

### `formatDfWeather(df)`

Aggregates 5-minute raw weather observations to hourly means, fills gaps, and converts wind speed + direction into east/north components then back to speed and direction.

| Parameter | Type | Description |
|---|---|---|
| `df` | `pd.DataFrame` | Output of `read_raw_weather` |

**Returns** `pd.DataFrame` with columns `year`, `month`, `day`, `hour`, `wind speed` (m/s), `direction` (degrees), `rainfall` (mm/hr sum).

**Notes:** Missing wind observations are filled by averaging forward-fill and back-fill. Missing rain is set to zero. Wind direction is computed from hourly-averaged east/north components using `np.arctan2`, which correctly handles all quadrants including zero east or north components.

---

### `read_raw_umgeni(fileName)`

Reads a raw Umgeni River CSV file exported from an obscape station (timestamp in Unix seconds UTC).

| Parameter | Type | Description |
|---|---|---|
| `fileName` | `str` | Full path to the raw Umgeni CSV |

**Returns** `pd.DataFrame` with columns `datetime` (Africa/Johannesburg timezone-aware) and the raw obscape data columns.

---

### `formatUmgeni(df)`

Aggregates obscape Umgeni water-level data to hourly means and converts level to flow using a simple linear rating curve (`flow = 20 × level`).

| Parameter | Type | Description |
|---|---|---|
| `df` | `pd.DataFrame` | Output of `read_raw_umgeni` |

**Returns** `pd.DataFrame` with columns `year`, `month`, `day`, `hour`, `level` (m), `flow` (m³/s).

---

### `formatUmgeni_dws(fileName)`

Reads and aggregates a DWS-format Umgeni flow CSV to hourly means. The DWS file must already contain `Year`, `Month`, `Day`, `Hour`, `Flow` columns.

| Parameter | Type | Description |
|---|---|---|
| `fileName` | `str` | Full path to the DWS CSV |

**Returns** `pd.DataFrame` with columns `Year`, `Month`, `Day`, `Hour`, `level` (mean flow, m³/s).

---

## `obscape.py` — Weather observation API client

### `getData(nowDate, fromDate, stationID=457, hours=168)`

Fetches wind and rain observations from the obscape.com API for a specified time window. Wind data is fetched from a wind station; rain data from a separate rain gauge at Durban Point.

| Parameter | Type | Description |
|---|---|---|
| `nowDate` | `dt.datetime` | End of the requested data window (used as `to` in the API query) |
| `fromDate` | `dt.datetime` | Start of the requested data window (used as `from` in the API query) |
| `stationID` | `int` | Obscape wind station ID. Default `457` (Ushaka) |
| `hours` | `int` | Legacy parameter kept for API compatibility. Not used internally |

**Returns** `pd.DataFrame` with columns `datetime` (UTC timezone-aware), `wind_speed` (m/s), `direction` (degrees from N), `rain` (mm/hr).

**Raises** `HTTPError` or `URLError` on network failures.

**Environment variables:**
- `OBSCAPE_USERNAME` — API username (default `'Justin'`)
- `OBSCAPE_API_KEY` — API key (default empty string)

**Notes:** The API returns Unix timestamps which are converted to UTC `datetime` objects internally. Values below `_MISSING_THRESHOLD = -100` are replaced with `np.nan`. Rain `None` values are set to zero.

---

### `format1HRW(df)`

Aggregates sub-hourly wind observations to hourly means. Fills gaps by averaging forward-fill and back-fill. Computes hourly wind speed and meteorological direction from averaged east/north components using `np.arctan2`.

| Parameter | Type | Description |
|---|---|---|
| `df` | `pd.DataFrame` | Must contain `datetime`, `east_wind`, `north_wind`, `wind_speed` |

**Returns** `pd.DataFrame` with columns `datetime` (UTC timezone-aware), `wind_speed` (m/s), `direction` (degrees from N).

**Notes:** Wind direction is computed as `(90 - degrees(arctan2(north, east))) % 360` — meteorological convention (direction wind is coming from). Handles zero east or north components correctly.

---

### `format1HRR(df)`

Aggregates sub-hourly rain observations to hourly sums. Missing values are set to zero before aggregation.

| Parameter | Type | Description |
|---|---|---|
| `df` | `pd.DataFrame` | Must contain `datetime` and `rain` columns |

**Returns** `pd.DataFrame` with columns `datetime` (UTC timezone-aware), `rain` (mm/hr).

---

## `processObs.py` — E. coli observation database client

### `queryDB(_from)`

Queries the internal database HTTP endpoint for *E. coli* beach observations from `_from` to the present.

| Parameter | Type | Description |
|---|---|---|
| `_from` | `dt.datetime` | Start of the query window. Timezone-naive datetime in Africa/Johannesburg local time |

**Returns** `pd.DataFrame` with columns `datetime` (timezone-naive, Africa/Johannesburg), `beach` (str), `ecoli` (float, CFU/100 mL).

**Raises** `RuntimeError` wrapping `HTTPError` or `URLError` on network failures.

**Notes:** The endpoint is `http://justinpringle.com/woza_ewandle/getObs/getObs.php?from=<ISO8601>`. The response is a JSON array of objects with `datetime`, `beach`, and `ecoli` keys.

---

### `readObs(fileName)`

Reads a pre-formatted *E. coli* observation CSV from disk.

| Parameter | Type | Description |
|---|---|---|
| `fileName` | `str` | Full path to the observations CSV |

**Returns** `pd.DataFrame` — raw contents of the file.

---

### `createTable(fileName)`

*(Legacy)* Reads raw *E. coli* CSV data, pivots it by beach location, and pads the result with −9 for the full year 2022. Saves to `observations/ecoli_sorted.csv`.

| Parameter | Type | Description |
|---|---|---|
| `fileName` | `str` | Ignored — internally hardcoded to `ecoli.csv` |

**Returns** `None` (writes file as side effect).

---

### `createTable2(dates, ini_file='model_ini.ini')`

Creates a time-indexed DataFrame padded with −9 for every observation location, covering exactly the supplied date range. Used to initialise the observation array when no real observations are available.

| Parameter | Type | Description |
|---|---|---|
| `dates` | array-like of `datetime` | The model's time axis (must match `forcing/weather.csv`) |
| `ini_file` | `str` | Path to the model configuration file |

**Returns** `pd.DataFrame` with `datetime` as the first column and one column per beach (all values −9).

---

## `pretreatment.py` — Input file readers

All functions in this module read CSV or text files from disk and return NumPy arrays. They are called by `model.run()` during initialisation.

---

### `read_global_params(fileName)`

Reads the global model parameter file (`param_files/params.txt`).

**Returns** `(Cac, Td, dT)`:
- `Cac` — wind reduction coefficient (dimensionless)
- `Td` — *E. coli* decay time scale (hours)
- `dT` — model time step (hours)

---

### `read_grid(fileName)`

Reads the grid geometry CSV (`param_files/cells.csv`). Columns: cell_label, x (UTM), y (UTM), length (m), bearing (degrees from N).

**Returns** `(ar_cell_label, ar_cell_coorx, ar_cell_coory, ar_cell_length, ar_cell_bearing)` — all `ndarray (N,)`.

---

### `read_input(fileName)`

Reads the storm-water discharge (SWD) input file (`forcing/inputs.csv`). Columns: index, name, x (UTM), y (UTM), catchment area (m²), flow factor, mean *E. coli* (CFU/100 mL), std *E. coli*, base flow (m³/s).

**Returns** `(ar_in_names, ar_in_coorx, ar_in_coory, ar_in_catch, ar_in_qFac, ar_in_mean_ecoli, ar_in_std_ecoli, ar_in_bflow)`.

---

### `read_init(fileName)`

Reads the initial *E. coli* concentration file (`start_files/init_c.csv`). File format (from `main.py` melt output): two columns — `variable` (cell index) and `ecoli` (CFU/100 mL).

**Returns** `ar_init_conc` — `ndarray (N,)` of initial concentrations.

---

### `read_weather(fileName)`

Reads the hourly weather forcing CSV (`forcing/weather.csv`). Columns: year, month, day, hour, wind_speed, direction, rain.

**Returns** `(ar_rain, ar_wind_spd, ar_wind_dir)` — all `ndarray (T,)` where T is the number of time steps.

---

### `read_river(fileName)`

Reads a river flow forcing CSV (`forcing/umgeni_flow.csv`). The file is written by `main.py` **with** the default pandas index, so the column layout is: pandas_idx, year, month, day, hour, flow. Column index 4 (hour) is currently read — see note below.

**Returns** `ar_river` — `ndarray (T,)`.

> **Known issue:** Due to `main.py` writing the file without `index=False`, `read_river` reads column 4 which is `hour` rather than `flow` (column 5). This is a pre-existing behaviour that has not been changed to preserve compatibility with the calibrated model.

---

### `read_obs_vals(fileName)`

Reads the hourly *E. coli* observation CSV (`observations/observations.csv`). Columns: year, month, day, hour, beach_1, beach_2, …

**Returns** `ar_obs_vals` — `ndarray (T, nb_obs_locs)` where −9 indicates a missing observation.

---

### `read_obs_params(fileName)`

Reads the beach observation location file (`observations/obLocs.csv`). Columns: index, name, x (UTM), y (UTM).

**Returns** `(ar_obs_names, ar_obs_coorx, ar_obs_coory)`.

---

## `model.py` — Core simulation

### Module constants

| Constant | Value | Description |
|---|---|---|
| `CELL_XSECT` | `200` | Cross-sectional area of each coastal cell (m²) |
| `Q_FAC` | `0.8` | Process noise scaling factor: `Q = I × e_load × Q_FAC` |
| `R_FAC` | `5000` | Observation noise scaling factor: `R = I × obs × R_FAC` |
| `ECOLI_RIVER_SCALE` | `250` | Divisor applied to raw river *E. coli* mean loads from config |

---

### `createA(cell_lengths, w_flag, wind, Cac, Td)`

Constructs the advection-decay matrix **A** for the current time step.

| Parameter | Type | Description |
|---|---|---|
| `cell_lengths` | `ndarray (N,)` | Length of each cell (m) |
| `w_flag` | `ndarray (N,)` | Wind direction flag: +1 (S→N advection), −1 (N→S), 0 (calm) |
| `wind` | `ndarray (N,)` | Along-cell wind speed for each cell (m/s) |
| `Cac` | `float` | Wind reduction coefficient |
| `Td` | `float` | Decay time scale (hours) |

**Returns** `ndarray (N, N)` — the system matrix A.

**Method:** Diagonal terms contain `−1/Td − Cac×wind/length×3600`. Off-diagonal terms encode up-cell advection: if `w_flag[i] > 0`, cell `i` receives input from cell `i−1`; if `w_flag[i] < 0`, from cell `i+1`. Boundary cells have no advective input from outside the domain.

---

### `createB(Q, cell_lengths, xsect=CELL_XSECT)`

Constructs the input (point-source) matrix **B**.

| Parameter | Type | Description |
|---|---|---|
| `Q` | `ndarray (N,)` or `ndarray (N, nb_rivs)` | Flow rates at each cell (m³/hr). 1-D for SWDs, 2-D for rivers |
| `cell_lengths` | `ndarray (N,)` | Cell lengths (m) |
| `xsect` | `float` | Cell cross-sectional area (m²). Default `CELL_XSECT=200` |

**Returns** `ndarray (N, N)` for SWDs or `ndarray (N, N, nb_rivs)` for rivers.

**Method:** `Tp_inv = Q / (length × xsect)` — the inverse of the flushing time scale for each source cell. Stored on the diagonal.

---

### `createH(A, phi, B)`

Constructs the integrated input matrix **H** = A⁻¹ (Φ − I) B, which maps source concentrations to cell concentrations over one time step.

| Parameter | Type | Description |
|---|---|---|
| `A` | `ndarray (N, N)` | System matrix |
| `phi` | `ndarray (N, N)` | State transition matrix `expm(A × dT)` |
| `B` | `ndarray (N, N)` | Input matrix |

**Returns** `ndarray (N, N)` — the integrated input matrix H.

---

### `kf_update(x_, ar_obs_cells, D, P, Q, R, niter=50, mardon_iter=True)`

Performs the Kalman filter observation update step, with an optional Mardon iteration to prevent negative concentrations.

| Parameter | Type | Description |
|---|---|---|
| `x_` | `ndarray (N,)` | Predicted *E. coli* concentrations (CFU/100 mL) |
| `ar_obs_cells` | `ndarray (M,)` | Observed *E. coli* values at observation locations |
| `D` | `ndarray (M, N)` | Observation operator — maps model cells to observation locations |
| `P` | `ndarray (N, N)` | Error covariance matrix |
| `Q` | `ndarray (N, N)` | Process noise covariance |
| `R` | `ndarray (M, M)` | Observation noise covariance |
| `niter` | `int` | Maximum Mardon iterations per observation. Default `50` |
| `mardon_iter` | `bool` | Use Mardon sequential iteration (True) or standard batch update (False). Default `True` |

**Returns** `(x_update, Pk, K)`:
- `x_update` — updated concentration vector `ndarray (N,)`
- `Pk` — updated covariance matrix `ndarray (N, N)`
- `K` — Kalman gain matrix `ndarray (N, M)`

**Mardon iteration:** Each observation is processed sequentially. If any updated concentration goes negative, the gain is scaled by 0.8 and the update is re-attempted, up to `niter` times. This prevents physically unrealisable negative concentrations.

---

### `run(ini_file='model_ini.ini')`

Top-level entry point. Reads all input files specified in `ini_file`, assembles the parameter dictionary, and delegates to `_exec`.

| Parameter | Type | Description |
|---|---|---|
| `ini_file` | `str` | Path to the INI configuration file. Default `'model_ini.ini'` |

**Returns** `dict` with keys:
- `X` — `ndarray (T+1, N)` — *E. coli* concentrations at each time step (row 0 = initial condition)
- `X_nkf` — `ndarray (T+1, N)` — concentrations without Kalman filter update (open-loop)
- `P_final` — `ndarray (N, N)` — final error covariance matrix
- `P_prev` — `ndarray (N, N)` — error covariance from the previous time step
- `Q` — `ndarray (N, N)` — final process noise covariance

---

### `_exec(params)` *(internal)*

Runs the time-stepping loop. Called by `run()`. Not intended for direct use.

**Loop logic per time step:**
1. Project wind onto each cell → `w_flag`, `wsp`
2. Build `A`, `phi = expm(A × dT)`, `B_SWD`, `B_rivers`, `H_SWD`, `H_rivers`
3. Predict: `x = Φ x + H_SWD e_SWD + Σ H_riv e_riv`
4. Update `P` with exponential decay weighting
5. If observations exist at this time step: Kalman update via `kf_update`
6. Store `x` in `xk[t+1]`

**E. coli loads** for both SWDs and rivers are drawn from log-normal distributions parameterised by the mean and standard deviation specified in the input files.

---

## `postTreatment.py` — Results and database

### Module constants

| Constant | Value | Description |
|---|---|---|
| `_WQ_GOOD_THRESHOLD` | `250` | Upper bound (exclusive) for "Good" classification (CFU/100 mL) |
| `_WQ_ACCEPT_THRESHOLD` | `500` | Upper bound (exclusive) for "Accept" classification (CFU/100 mL) |

---

### `_replaceitem(x)`

Classifies a single *E. coli* value according to the South African beach water quality thresholds.

| Parameter | Type | Description |
|---|---|---|
| `x` | `float` | *E. coli* concentration (CFU/100 mL) |

**Returns** `str` — `'Good'`, `'Accept'`, or `'Bad'`.

---

### `gatherObsFile(ini_file='model_ini.ini')`

Reads the beach observation location file specified in the model configuration.

| Parameter | Type | Description |
|---|---|---|
| `ini_file` | `str` | Path to the configuration file |

**Returns** `pd.DataFrame` — contents of `fileObsLocs`.

---

### `createSQL_db(obsDF, con)`

Creates or replaces a `beachLocs` table in the connected SQL database, including UTM→lat/lon conversion.

| Parameter | Type | Description |
|---|---|---|
| `obsDF` | `pd.DataFrame` | Beach observation locations DataFrame (must include `X`, `Y`, `name` columns) |
| `con` | SQLAlchemy engine | Active database connection |

**Returns** `None`.

**Notes:** Uses `utm.to_latlon` for coordinate conversion. The `utm` package must be installed.

---

### `create_sql_table_result(res_array, con, ini_file='model_ini.ini', db='WQ')`

Writes model output (per-beach WQ classification) to the SQL database.

| Parameter | Type | Description |
|---|---|---|
| `res_array` | `ndarray (T, N)` | *E. coli* concentration array from `model.run()['X'][:-1]` |
| `con` | SQLAlchemy engine | Active database connection |
| `ini_file` | `str` | Path to the configuration file |
| `db` | `str` | Target SQL table name. Default `'WQ'` |

**Returns** `None`.

**Process:** For each observation location, extracts the time series from the nearest model cell using `utils.findCellID`, applies `_replaceitem` to classify each hourly value, and writes `datetime`, `Year`, `Month`, `Day`, `Hour`, `beach`, `wq` to the target table (replacing if it exists).

---

### `create_con()`

Creates and returns a SQLAlchemy MySQL connection engine for the production database.

**Returns** SQLAlchemy `Engine`.

**Notes:** Credentials are currently hardcoded. Consider moving to environment variables before deploying to a new server.

---

## Runner scripts

### `run_dry.py`

Runs the model using whatever CSV files are already present in `forcing/` and `observations/`. No network calls, no database access. Useful for testing code changes and verifying model output format.

**Output directory:** `results/`

| Output file | Description |
|---|---|
| `wq_by_beach.csv` | Hourly `datetime`, `beach`, `ecoli_cfu`, `wq_class` for each observation location |
| `wq_all_cells.csv` | Hourly *E. coli* (CFU/100 mL) for every grid cell |
| `run_summary.txt` | Run metadata and per-beach statistics (min, mean, max, % Bad) |

---

### `run_historical.py`

Fetches weather observations from the obscape API in monthly chunks and *E. coli* observations from the database (read-only), then runs the model over the defined historical period.

**Key variables at top of script:**

| Variable | Default | Description |
|---|---|---|
| `START` | `dt.datetime(2025, 1, 1)` | Start of the hindcast period (SAST naive) |
| `END` | `dt.datetime(2026, 3, 1)` | End of the hindcast period |
| `OUT_DIR` | `'results_historical'` | Output directory |

**Process:**
1. Build monthly `(chunk_start, chunk_end)` pairs and call `obscape.getData` for each.
2. Concatenate, deduplicate, sort; convert UTC → Africa/Johannesburg.
3. Write `forcing/weather.csv` and `forcing/umgeni_flow.csv`.
4. Call `processObs.queryDB(START)` (read-only); fall back to all-minus-9 if unavailable.
5. Write `observations/observations.csv`.
6. Run `model.run()` using existing `start_files/init_c.csv` (cold start from zeros if no saved state).
7. Write per-beach and all-cells results to `OUT_DIR/`. Does **not** update the SQL database.

**Output directory:** `results_historical/` — same file structure as `run_dry.py`.

> **Warning:** Overwrites `forcing/weather.csv`, `forcing/umgeni_flow.csv`, and `observations/observations.csv`.

---

### `run_forecast.py`

Hot-starts the model from the final state of the historical run and fetches a GFS forecast from Open-Meteo. Runs the model as a pure forecast with no data assimilation.

**Key variables at top of script:**

| Variable | Default | Description |
|---|---|---|
| `FORECAST_END` | `dt.datetime(2026, 3, 8)` | Target end of the forecast |
| `HIST_CELLS` | `'results_historical/wq_all_cells.csv'` | Source of the hot-start initial state |
| `OUT_DIR` | `'results_forecast'` | Output directory |

**Process:**
1. Load the last row of `HIST_CELLS` and write it to `start_files/init_c.csv` as the hot-start. Falls back to the existing `init_c.csv` if the file is absent.
2. Calculate `forecast_length` = hours from now to `FORECAST_END` (minimum 24 h).
3. Fetch GFS forecast via `forcingSort.get_gfs(forecast_length=N)`.
4. Convert UTC → Africa/Johannesburg; write `forcing/weather.csv` and `forcing/umgeni_flow.csv`.
5. Write all-minus-9 `observations/observations.csv` (no assimilation).
6. Run `model.run()`.
7. Write per-beach and all-cells results to `OUT_DIR/`. Does **not** update the SQL database.

**Output directory:** `results_forecast/` — same file structure as `run_dry.py`.

> **Warning:** Overwrites `forcing/weather.csv`, `forcing/umgeni_flow.csv`, `observations/observations.csv`, and `start_files/init_c.csv`.
