#!/usr/bin/env python3
"""
Dry-run the model using existing CSV forcing/observation files.
Skips all API calls, database writes, and PHP steps.

Outputs
-------
results/wq_by_beach.csv   -- hourly E. coli and WQ class for each beach
results/wq_all_cells.csv  -- hourly E. coli for every grid cell
results/run_summary.txt   -- model metadata and run statistics
"""
import os
import datetime as dt
import numpy as np
import pandas as pd

import model
from pretreatment import read_grid, read_weather, read_obs_params
from postTreatment import _replaceitem
import utils as ut
import configparser

OUT_DIR = 'results'
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Read config
# ---------------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('model_ini.ini')

file_weather   = config.get('input files', 'fileWeatherForcing')
file_grid      = config.get('input files', 'fileGrid')
file_obs_locs  = config.get('input files', 'fileObsLocs')

# ---------------------------------------------------------------------------
# Build datetime index from weather file
# ---------------------------------------------------------------------------
tab = np.genfromtxt(file_weather, delimiter=',', skip_header=1, dtype=int)
dates = [dt.datetime(r[0], r[1], r[2], r[3]) for r in tab[:, 0:4]]

# ---------------------------------------------------------------------------
# Run model
# ---------------------------------------------------------------------------
print('[%s] Running model...' % dt.datetime.now().strftime('%H:%M:%S'))
results = model.run()
print('[%s] Model finished.' % dt.datetime.now().strftime('%H:%M:%S'))

X        = results['X'][:-1]          # shape (T, N_cells)
P_final  = results['P_final']
nb_steps = len(dates)

# ---------------------------------------------------------------------------
# Extract per-beach results
# ---------------------------------------------------------------------------
ar_cell_label, ar_cell_coorx, ar_cell_coory, _, _ = read_grid(file_grid)
ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)

rows = []
for i, beach in enumerate(ar_obs_names):
    cell_id = ut.findCellID(ar_cell_label,
                            ar_obs_coorx[i], ar_obs_coory[i],
                            ar_cell_coorx, ar_cell_coory) - 1
    ecoli_series = X[:nb_steps, cell_id]
    for t, (d, e) in enumerate(zip(dates, ecoli_series)):
        rows.append({
            'datetime':  d,
            'beach':     beach,
            'ecoli_cfu': round(float(e), 1),
            'wq_class':  _replaceitem(e),
        })

beach_df = pd.DataFrame(rows)
beach_path = os.path.join(OUT_DIR, 'wq_by_beach.csv')
beach_df.to_csv(beach_path, index=False, date_format='%Y-%m-%d %H:%M')
print('Beach results  -> %s  (%d rows)' % (beach_path, len(beach_df)))

# ---------------------------------------------------------------------------
# All-cells results
# ---------------------------------------------------------------------------
cols       = ['cell_%d' % c for c in ar_cell_label]
all_cells  = pd.DataFrame(X[:nb_steps], index=dates, columns=cols)
all_cells.index.name = 'datetime'
cells_path = os.path.join(OUT_DIR, 'wq_all_cells.csv')
all_cells.to_csv(cells_path, float_format='%.2f', date_format='%Y-%m-%d %H:%M')
print('All-cells grid -> %s  (%d rows x %d cells)' % (
    cells_path, len(all_cells), len(ar_cell_label)))

# ---------------------------------------------------------------------------
# Summary text file
# ---------------------------------------------------------------------------
summary_path = os.path.join(OUT_DIR, 'run_summary.txt')
with open(summary_path, 'w') as fh:
    fh.write('CWQM dry run\n')
    fh.write('Generated : %s\n' % dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    fh.write('Time steps: %d\n' % nb_steps)
    fh.write('Grid cells: %d\n' % len(ar_cell_label))
    fh.write('Beaches   : %s\n' % ', '.join(ar_obs_names))
    fh.write('Period    : %s  ->  %s\n' % (dates[0], dates[-1]))
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

# Print summary to stdout too
with open(summary_path) as fh:
    print('\n' + fh.read())
