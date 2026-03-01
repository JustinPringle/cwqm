#!/usr/bin/env python3
"""
Historical model run: Jan 2025 – March 2026.

Fetches weather observations from the obscape API in monthly chunks and
E. coli observations from the internal database (read-only).
Does NOT push results to the SQL database or trigger any PHP/URL steps.

NOTE: This script overwrites the files in forcing/ and observations/.
      Back them up first if you want to keep the current short test data.
      The model uses start_files/init_c.csv and start_files/p.out as the
      initial state; those files are left unchanged (cold start from zeros).

Outputs
-------
results_historical/wq_by_beach.csv   -- hourly E. coli and WQ class per beach
results_historical/wq_all_cells.csv  -- hourly E. coli for every grid cell
results_historical/run_summary.txt   -- run metadata and statistics
"""
import logging
import os
import datetime as dt
import numpy as np
import pandas as pd
import configparser

import obscape
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

# ---------------------------------------------------------------------------
# Period (timezone-naive SAST datetimes, matching main.py convention)
# ---------------------------------------------------------------------------
START = dt.datetime(2025, 1, 1)
END   = dt.datetime(2026, 3, 1)
OUT_DIR = 'results_historical'
os.makedirs(OUT_DIR, exist_ok=True)


def _month_boundaries(start: dt.datetime, end: dt.datetime):
    """Yield (chunk_start, chunk_end) pairs, one per calendar month."""
    cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur < end:
        if cur.month == 12:
            nxt = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            nxt = cur.replace(month=cur.month + 1, day=1)
        yield (max(cur, start), min(nxt, end))
        cur = nxt


# ---------------------------------------------------------------------------
# 1. Fetch obscape weather data in monthly chunks
# ---------------------------------------------------------------------------
chunks = []
for chunk_start, chunk_end in _month_boundaries(START, END):
    logger.info('Fetching obscape weather  %s → %s',
                chunk_start.strftime('%Y-%m-%d'), chunk_end.strftime('%Y-%m-%d'))
    try:
        df_chunk = obscape.getData(chunk_end, chunk_start)
        chunks.append(df_chunk)
    except Exception as exc:
        logger.warning('obscape fetch failed for %s → %s: %s; skipping chunk.',
                       chunk_start.strftime('%Y-%m-%d'),
                       chunk_end.strftime('%Y-%m-%d'), exc)

if not chunks:
    raise RuntimeError('No weather data could be fetched from obscape. '
                       'Check API credentials (OBSCAPE_USERNAME / OBSCAPE_API_KEY).')

weatherDf = (
    pd.concat(chunks, ignore_index=True)
    .drop_duplicates('datetime')
    .sort_values('datetime')
    .reset_index(drop=True)
)
logger.info('Weather data: %d hourly rows  (%s → %s)',
            len(weatherDf),
            weatherDf['datetime'].iloc[0],
            weatherDf['datetime'].iloc[-1])

# Convert UTC → Africa/Johannesburg (matching main.py)
weatherDf['datetime'] = weatherDf['datetime'].map(
    lambda x: x.tz_convert('Africa/Johannesburg'))

weatherDf['year']  = weatherDf['datetime'].dt.year
weatherDf['month'] = weatherDf['datetime'].dt.month
weatherDf['day']   = weatherDf['datetime'].dt.day
weatherDf['hour']  = weatherDf['datetime'].dt.hour

weatherDf[['year', 'month', 'day', 'hour', 'wind_speed', 'direction', 'rain']].to_csv(
    'forcing/weather.csv', index=False)
logger.info('Written forcing/weather.csv')

# ---------------------------------------------------------------------------
# 2. Umgeni flows
# ---------------------------------------------------------------------------
umgeniDf = ut.umgeniFlows(weatherDf)
umgeniDf['year']  = umgeniDf['datetime'].dt.year
umgeniDf['month'] = umgeniDf['datetime'].dt.month
umgeniDf['day']   = umgeniDf['datetime'].dt.day
umgeniDf['hour']  = umgeniDf['datetime'].dt.hour
# Written WITH default pandas index to match the format expected by read_river
# (pretreatment.read_river reads column 4 which is 'hour' in this layout;
# this preserves the behaviour of the existing production main.py).
umgeniDf[['year', 'month', 'day', 'hour', 'flow']].to_csv('forcing/umgeni_flow.csv')
logger.info('Written forcing/umgeni_flow.csv')

# ---------------------------------------------------------------------------
# 3. E. coli observations (read-only from database)
# ---------------------------------------------------------------------------
ecoliPadded = processObs.createTable2(weatherDf['datetime']).set_index('datetime')
obsNames = list(ecoliPadded.columns)

try:
    ecoliDf = processObs.queryDB(START)
    ecoliDf['datetime'] = ecoliDf['datetime'].map(
        lambda x: x.tz_localize('Africa/Johannesburg'))
    ecoliDf = (ecoliDf
               .pivot(index='datetime', columns='beach', values='ecoli')
               .rename_axis(None, axis=1))
    mergedEcoli = ecoliDf.combine_first(ecoliPadded)
    logger.info('Merged %d observation records from database', len(ecoliDf))
except (ValueError, KeyError, RuntimeError) as exc:
    logger.warning('No usable observations from DB (%s); running without assimilation.', exc)
    mergedEcoli = ecoliPadded

mergedEcoli['year']  = mergedEcoli.index.year
mergedEcoli['month'] = mergedEcoli.index.month
mergedEcoli['day']   = mergedEcoli.index.day
mergedEcoli['hour']  = mergedEcoli.index.hour
obs_cols = list(mergedEcoli.columns.values)
obs_cols = obs_cols[-4:] + obsNames
mergedEcoli[obs_cols].to_csv('observations/observations.csv', index=False)
logger.info('Written observations/observations.csv')

# ---------------------------------------------------------------------------
# 4. Run model (cold start from existing start_files/)
# ---------------------------------------------------------------------------
logger.info('Starting model run (%s → %s) …',
            START.strftime('%Y-%m-%d'), END.strftime('%Y-%m-%d'))
results = model.run()
logger.info('Model run complete.')

X = results['X'][:-1]   # shape (T, N_cells)

# ---------------------------------------------------------------------------
# 5. Build datetime index from the written weather file
# ---------------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('model_ini.ini')
file_weather  = config.get('input files', 'fileWeatherForcing')
file_grid     = config.get('input files', 'fileGrid')
file_obs_locs = config.get('input files', 'fileObsLocs')

tab = np.genfromtxt(file_weather, delimiter=',', skip_header=1, dtype=int)
dates = [dt.datetime(r[0], r[1], r[2], r[3]) for r in tab[:, 0:4]]
nb_steps = len(dates)

ar_cell_label, ar_cell_coorx, ar_cell_coory, _, _ = read_grid(file_grid)
ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)

# ---------------------------------------------------------------------------
# 6. Per-beach results
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

beach_df = pd.DataFrame(rows)
beach_path = os.path.join(OUT_DIR, 'wq_by_beach.csv')
beach_df.to_csv(beach_path, index=False, date_format='%Y-%m-%d %H:%M')
logger.info('Beach results  -> %s  (%d rows)', beach_path, len(beach_df))

# ---------------------------------------------------------------------------
# 7. All-cells results
# ---------------------------------------------------------------------------
cell_cols = ['cell_%d' % c for c in ar_cell_label]
all_cells = pd.DataFrame(X[:nb_steps], index=dates, columns=cell_cols)
all_cells.index.name = 'datetime'
cells_path = os.path.join(OUT_DIR, 'wq_all_cells.csv')
all_cells.to_csv(cells_path, float_format='%.2f', date_format='%Y-%m-%d %H:%M')
logger.info('All-cells grid -> %s  (%d rows × %d cells)',
            cells_path, len(all_cells), len(ar_cell_label))

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
summary_path = os.path.join(OUT_DIR, 'run_summary.txt')
with open(summary_path, 'w') as fh:
    fh.write('CWQM historical run\n')
    fh.write('Period    : %s → %s\n' % (START.strftime('%Y-%m-%d'), END.strftime('%Y-%m-%d')))
    fh.write('Generated : %s\n' % dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    fh.write('Time steps: %d\n' % nb_steps)
    fh.write('Grid cells: %d\n' % len(ar_cell_label))
    fh.write('Beaches   : %s\n' % ', '.join(ar_obs_names))
    fh.write('Data range: %s  →  %s\n' % (dates[0], dates[-1]))
    fh.write('Init state: cold start (start_files/init_c.csv)\n')
    fh.write('\nPer-beach statistics (E. coli CFU/100 mL)\n')
    fh.write('-' * 56 + '\n')
    fh.write('%-16s %8s %8s %8s %8s\n' % ('beach', 'min', 'mean', 'max', '% Bad'))
    fh.write('-' * 56 + '\n')
    for beach, grp in beach_df.groupby('beach', sort=False):
        e = grp['ecoli_cfu']
        pct_bad = 100 * (grp['wq_class'] == 'Bad').sum() / len(grp)
        fh.write('%-16s %8.1f %8.1f %8.1f %7.1f%%\n' % (
            beach, e.min(), e.mean(), e.max(), pct_bad))
    fh.write('-' * 56 + '\n')

with open(summary_path) as fh:
    print('\n' + fh.read())
