#!/usr/bin/env python3
"""
Forecast run: last historical simulation date → 8 March 2026.

Hot-starts from the final model state in results_historical/wq_all_cells.csv
(falls back to the existing start_files/init_c.csv if that file is absent).
Fetches GFS forecast data to cover the period, then runs the model with no
data assimilation (all-minus-9 observations).

Does NOT push results to SQL or trigger PHP/URL steps.

Outputs
-------
results_forecast/wq_by_beach.csv   -- hourly E. coli and WQ class per beach
results_forecast/wq_all_cells.csv  -- hourly E. coli for every grid cell
results_forecast/run_summary.txt   -- run metadata and statistics
"""
import logging
import os
import datetime as dt
import numpy as np
import pandas as pd
import configparser

from forcingSort import get_gfs
import processObs
import utils as ut
import model
from pretreatment import read_grid, read_obs_params
from postTreatment import _replaceitem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

FORECAST_END = dt.datetime(2026, 3, 8)
HIST_CELLS   = 'results_historical/wq_all_cells.csv'
OUT_DIR      = 'results_forecast'
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Hot-start: extract final model state from historical results
# ---------------------------------------------------------------------------
if os.path.exists(HIST_CELLS):
    hist_df   = pd.read_csv(HIST_CELLS)
    last_row  = hist_df.iloc[-1]
    cell_cols = [c for c in hist_df.columns if c != 'datetime']
    cell_vals = last_row[cell_cols].values.astype(float)
    init_df   = pd.DataFrame({'variable': range(len(cell_vals)),
                              'ecoli':    cell_vals})
    init_df.to_csv('start_files/init_c.csv', index=False)
    logger.info('Hot-start from historical results last row: %s', last_row['datetime'])
else:
    logger.warning('%s not found — using existing start_files/init_c.csv (cold start).',
                   HIST_CELLS)

# ---------------------------------------------------------------------------
# 2. GFS forecast — enough hours to reach FORECAST_END
# ---------------------------------------------------------------------------
now_utc          = dt.datetime.now(dt.timezone.utc)
hours_to_end     = int((FORECAST_END - now_utc).total_seconds() / 3600) + 1
forecast_length  = max(hours_to_end, 24)          # always at least 24 h
logger.info('Fetching GFS forecast for %d hours (target end: %s)',
            forecast_length, FORECAST_END.strftime('%Y-%m-%d'))

gfsDf = get_gfs(forecast_length=forecast_length)

# ---------------------------------------------------------------------------
# 3. Convert UTC → Africa/Johannesburg and write weather.csv
# ---------------------------------------------------------------------------
gfsDf['datetime'] = gfsDf['datetime'].map(
    lambda x: x.tz_convert('Africa/Johannesburg'))

gfsDf['year']  = gfsDf['datetime'].dt.year
gfsDf['month'] = gfsDf['datetime'].dt.month
gfsDf['day']   = gfsDf['datetime'].dt.day
gfsDf['hour']  = gfsDf['datetime'].dt.hour

gfsDf[['year', 'month', 'day', 'hour', 'wind_speed', 'direction', 'rain']].to_csv(
    'forcing/weather.csv', index=False)
logger.info('Written forcing/weather.csv (%d rows, %s → %s)',
            len(gfsDf),
            gfsDf['datetime'].iloc[0].strftime('%Y-%m-%d %H:%M %Z'),
            gfsDf['datetime'].iloc[-1].strftime('%Y-%m-%d %H:%M %Z'))

# ---------------------------------------------------------------------------
# 4. Umgeni flows
# ---------------------------------------------------------------------------
umgeniDf = ut.umgeniFlows(gfsDf)
umgeniDf['year']  = umgeniDf['datetime'].dt.year
umgeniDf['month'] = umgeniDf['datetime'].dt.month
umgeniDf['day']   = umgeniDf['datetime'].dt.day
umgeniDf['hour']  = umgeniDf['datetime'].dt.hour
umgeniDf[['year', 'month', 'day', 'hour', 'flow']].to_csv('forcing/umgeni_flow.csv')
logger.info('Written forcing/umgeni_flow.csv')

# ---------------------------------------------------------------------------
# 5. Observations — all -9 (pure forecast, no assimilation)
# ---------------------------------------------------------------------------
ecoliPadded = processObs.createTable2(gfsDf['datetime']).set_index('datetime')
obsNames    = list(ecoliPadded.columns)

ecoliPadded['year']  = ecoliPadded.index.year
ecoliPadded['month'] = ecoliPadded.index.month
ecoliPadded['day']   = ecoliPadded.index.day
ecoliPadded['hour']  = ecoliPadded.index.hour
obs_cols = list(ecoliPadded.columns.values)
obs_cols = obs_cols[-4:] + obsNames
ecoliPadded[obs_cols].to_csv('observations/observations.csv', index=False)
logger.info('Written observations/observations.csv (all-minus-9, no assimilation)')

# ---------------------------------------------------------------------------
# 6. Run model
# ---------------------------------------------------------------------------
logger.info('Starting forecast model run …')
results = model.run()
logger.info('Model run complete.')

X = results['X'][:-1]   # shape (T, N_cells)

# ---------------------------------------------------------------------------
# 7. Build datetime index from the written weather file
# ---------------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('model_ini.ini')
file_weather  = config.get('input files', 'fileWeatherForcing')
file_grid     = config.get('input files', 'fileGrid')
file_obs_locs = config.get('input files', 'fileObsLocs')

tab = np.genfromtxt(file_weather, delimiter=',', skip_header=1, dtype=int)
dates     = [dt.datetime(r[0], r[1], r[2], r[3]) for r in tab[:, 0:4]]
nb_steps  = len(dates)

ar_cell_label, ar_cell_coorx, ar_cell_coory, _, _ = read_grid(file_grid)
ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)

# ---------------------------------------------------------------------------
# 8. Per-beach results
# ---------------------------------------------------------------------------
rows = []
for i, beach in enumerate(ar_obs_names):
    cell_id = ut.findCellID(ar_cell_label,
                            ar_obs_coorx[i], ar_obs_coory[i],
                            ar_cell_coorx, ar_cell_coory) - 1
    ecoli_series = X[:nb_steps, cell_id]
    for d, e in zip(dates, ecoli_series):
        rows.append({
            'datetime':  d,
            'beach':     beach,
            'ecoli_cfu': round(float(e), 1),
            'wq_class':  _replaceitem(e),
        })

beach_df   = pd.DataFrame(rows)
beach_path = os.path.join(OUT_DIR, 'wq_by_beach.csv')
beach_df.to_csv(beach_path, index=False, date_format='%Y-%m-%d %H:%M')
logger.info('Beach results  -> %s  (%d rows)', beach_path, len(beach_df))

# ---------------------------------------------------------------------------
# 9. All-cells results
# ---------------------------------------------------------------------------
cell_cols  = ['cell_%d' % c for c in ar_cell_label]
all_cells  = pd.DataFrame(X[:nb_steps], index=dates, columns=cell_cols)
all_cells.index.name = 'datetime'
cells_path = os.path.join(OUT_DIR, 'wq_all_cells.csv')
all_cells.to_csv(cells_path, float_format='%.2f', date_format='%Y-%m-%d %H:%M')
logger.info('All-cells grid -> %s  (%d rows × %d cells)',
            cells_path, len(all_cells), len(ar_cell_label))

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------
summary_path = os.path.join(OUT_DIR, 'run_summary.txt')
with open(summary_path, 'w') as fh:
    fh.write('CWQM forecast run\n')
    fh.write('Period    : %s → %s\n' % (dates[0].strftime('%Y-%m-%d %H:%M'),
                                         dates[-1].strftime('%Y-%m-%d %H:%M')))
    fh.write('Generated : %s\n' % dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    fh.write('Time steps: %d\n' % nb_steps)
    fh.write('Grid cells: %d\n' % len(ar_cell_label))
    fh.write('Beaches   : %s\n' % ', '.join(ar_obs_names))
    fh.write('Init state: %s\n' % (
        'hot-start from ' + HIST_CELLS if os.path.exists(HIST_CELLS)
        else 'cold start (start_files/init_c.csv)'))
    fh.write('Assimil.  : none (pure forecast)\n')
    fh.write('\nPer-beach statistics (E. coli CFU/100 mL)\n')
    fh.write('-' * 56 + '\n')
    fh.write('%-16s %8s %8s %8s %8s\n' % ('beach', 'min', 'mean', 'max', '% Bad'))
    fh.write('-' * 56 + '\n')
    for beach, grp in beach_df.groupby('beach', sort=False):
        e       = grp['ecoli_cfu']
        pct_bad = 100 * (grp['wq_class'] == 'Bad').sum() / len(grp)
        fh.write('%-16s %8.1f %8.1f %8.1f %7.1f%%\n' % (
            beach, e.min(), e.mean(), e.max(), pct_bad))
    fh.write('-' * 56 + '\n')

with open(summary_path) as fh:
    print('\n' + fh.read())
