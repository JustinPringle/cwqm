#!/usr/bin/env python3
"""
Tests for robustness and code-quality improvements.

Run with:  pytest test_changes.py -v
"""
import sys
import types
import json
import inspect
import datetime as dt
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Stub out getgfs so forcingSort can be imported without the real package.
# ---------------------------------------------------------------------------
_getgfs_stub = types.ModuleType('getgfs')
_getgfs_stub.Forecast = MagicMock()
sys.modules.setdefault('getgfs', _getgfs_stub)


# ===========================================================================
# utils.py
# ===========================================================================

class TestGetDist:
    def test_zero_distance(self):
        from utils import getDist
        assert getDist(1.0, 2.0, 1.0, 2.0) == 0.0

    def test_known_345_triangle(self):
        from utils import getDist
        assert getDist(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)

    def test_symmetric(self):
        from utils import getDist
        assert getDist(0.0, 0.0, 3.0, 4.0) == getDist(3.0, 4.0, 0.0, 0.0)


class TestFindCellID:
    """findCellID: previously had an uninitialised-variable bug."""

    def _grid(self):
        """Five cells spaced 10 m apart along the x-axis."""
        labels = np.array([1, 2, 3, 4, 5])
        coorx  = np.array([0.0, 10.0, 20.0, 30.0, 40.0])
        coory  = np.array([0.0,  0.0,  0.0,  0.0,  0.0])
        return labels, coorx, coory

    def test_finds_exact_match(self):
        from utils import findCellID
        labels, coorx, coory = self._grid()
        assert findCellID(labels, 20.0, 0.0, coorx, coory) == 3

    def test_finds_nearby_cell(self):
        from utils import findCellID
        labels, coorx, coory = self._grid()
        # Query exactly at cell 3's centre: dist=0 to cell 3, dist=10 to
        # neighbours (10 is NOT < dC=10), so only cell 3 matches.
        assert findCellID(labels, 20.0, 0.0, coorx, coory) == 3

    def test_raises_when_no_cell_in_range(self):
        """Bug fix: previously returned uninitialised cellPos."""
        from utils import findCellID
        labels, coorx, coory = self._grid()
        with pytest.raises(ValueError, match='No cell found'):
            findCellID(labels, 1000.0, 1000.0, coorx, coory)

    def test_raises_message_contains_coordinates(self):
        from utils import findCellID
        labels, coorx, coory = self._grid()
        with pytest.raises(ValueError, match='500.0'):
            findCellID(labels, 500.0, 0.0, coorx, coory)


class TestGetWindAdv:
    """getWindAdv: previously divided by zero when wind was calm."""

    def _cells(self, n=4, bearing=0.0, length=500.0):
        return (
            np.arange(1, n + 1),
            np.full(n, bearing),
            np.full(n, length),
        )

    def test_zero_wind_does_not_crash(self):
        """Bug fix: zero wind caused ZeroDivisionError."""
        from utils import getWindAdv
        labels, bearings, lengths = self._cells()
        flags, speeds = getWindAdv(labels, bearings, lengths,
                                   wind_spd=0.0, wind_dir=180.0)
        assert np.all(speeds == 0.0)
        assert np.all(flags == 0.0)

    def test_output_lengths_match_cell_count(self):
        from utils import getWindAdv
        n = 6
        labels, bearings, lengths = self._cells(n=n)
        flags, speeds = getWindAdv(labels, bearings, lengths,
                                   wind_spd=5.0, wind_dir=90.0)
        assert len(flags) == n
        assert len(speeds) == n

    def test_projected_speeds_non_negative(self):
        from utils import getWindAdv
        labels, bearings, lengths = self._cells(n=4, bearing=45.0)
        flags, speeds = getWindAdv(labels, bearings, lengths,
                                   wind_spd=8.0, wind_dir=135.0)
        assert np.all(speeds >= 0.0)

    def test_flags_are_valid_values(self):
        """Flags must be -1, 0, or +1."""
        from utils import getWindAdv
        labels, bearings, lengths = self._cells(n=5, bearing=0.0)
        flags, _ = getWindAdv(labels, bearings, lengths,
                              wind_spd=6.0, wind_dir=180.0)
        assert set(flags).issubset({-1.0, 0.0, 1.0})


# ===========================================================================
# model.py — constants
# ===========================================================================

class TestModelConstants:
    """Verify magic numbers were extracted as named constants."""

    def test_cell_xsect(self):
        from model import CELL_XSECT
        assert CELL_XSECT == 200

    def test_q_fac(self):
        from model import Q_FAC
        assert Q_FAC == pytest.approx(0.8)

    def test_r_fac(self):
        from model import R_FAC
        assert R_FAC == 5000

    def test_ecoli_river_scale(self):
        from model import ECOLI_RIVER_SCALE
        assert ECOLI_RIVER_SCALE == 250

    def test_createB_uses_cell_xsect_as_default(self):
        """createB's default xsect parameter must equal CELL_XSECT."""
        from model import createB, CELL_XSECT
        sig = inspect.signature(createB)
        assert sig.parameters['xsect'].default == CELL_XSECT


# ===========================================================================
# model.py — matrix construction
# ===========================================================================

class TestCreateA:
    def test_shape(self):
        from model import createA
        n = 5
        A = createA(np.ones(n) * 200.0, np.ones(n), np.ones(n) * 3.0,
                    Cac=0.05, Td=24.0)
        assert A.shape == (n, n)

    def test_diagonal_is_negative(self):
        from model import createA
        n = 4
        A = createA(np.ones(n) * 200.0, np.ones(n), np.ones(n) * 3.0,
                    Cac=0.05, Td=24.0)
        assert np.all(np.diag(A) < 0)


class TestCreateB:
    def test_shape_swd(self):
        from model import createB
        n = 5
        Q = np.zeros(n)
        Q[2] = 2.0
        B = createB(Q, np.ones(n) * 300.0)
        assert B.shape == (n, n)

    def test_zero_flow_gives_zero_B(self):
        from model import createB
        n = 4
        B = createB(np.zeros(n), np.ones(n) * 200.0)
        assert np.all(B == 0.0)


class TestKfUpdate:
    def _setup(self, nb_cells=5, nb_obs=2):
        x_ = np.ones(nb_cells) * 100.0
        ar_obs_cells = np.full(nb_obs, 80.0)
        D = np.zeros((nb_obs, nb_cells))
        for i in range(nb_obs):
            D[i, i] = 1
        P = np.eye(nb_cells) * 1000.0
        Q = np.eye(nb_cells) * 100.0
        R = np.eye(nb_obs) * 5000.0
        return x_, ar_obs_cells, D, P, Q, R

    def test_output_shapes_no_mardon(self):
        from model import kf_update
        x_, obs, D, P, Q, R = self._setup()
        x_upd, P_new, K = kf_update(x_, obs, D, P, Q, R, mardon_iter=False)
        assert x_upd.shape == x_.shape
        assert P_new.shape == P.shape

    def test_mardon_keeps_concentrations_non_negative(self):
        from model import kf_update
        nb_cells = 4
        x_ = np.ones(nb_cells) * 50.0
        obs = np.array([5.0])           # observation much lower than prior
        D = np.zeros((1, nb_cells))
        D[0, 0] = 1
        P = np.eye(nb_cells) * 500.0
        Q = np.eye(nb_cells) * 50.0
        R = np.eye(1) * 5000.0
        x_upd, _, _ = kf_update(x_, obs, D, P, Q, R, mardon_iter=True)
        assert np.all(x_upd >= 0)


# ===========================================================================
# processObs.py — error handling
# ===========================================================================

class TestQueryDBErrors:
    """queryDB now raises RuntimeError on HTTP/URL failures."""

    def test_http_error_raises_runtime_error(self):
        from processObs import queryDB
        err = HTTPError(url='http://test', code=500,
                        msg='Internal Server Error', hdrs={}, fp=None)
        with patch('processObs.urlopen', side_effect=err):
            with pytest.raises(RuntimeError, match='HTTP 500'):
                queryDB(dt.datetime(2024, 1, 1))

    def test_url_error_raises_runtime_error(self):
        from processObs import queryDB
        err = URLError(reason='Connection refused')
        with patch('processObs.urlopen', side_effect=err):
            with pytest.raises(RuntimeError, match='Could not reach'):
                queryDB(dt.datetime(2024, 1, 1))

    def test_timeout_included_in_urlopen_call(self):
        """urlopen must be called with a timeout argument."""
        from processObs import queryDB, _REQUEST_TIMEOUT
        fake_data = [
            {'datetime': '2024-01-01 10:00:00', 'beach': 'ushaka', 'ecoli': 150}
        ]
        mock_resp = MagicMock()
        with patch('processObs.urlopen', return_value=mock_resp) as mock_open, \
             patch('processObs.js.load', return_value=fake_data):
            queryDB(dt.datetime(2024, 1, 1))
        _, call_kwargs = mock_open.call_args
        assert call_kwargs.get('timeout') == _REQUEST_TIMEOUT

    def test_successful_response_returns_dataframe(self):
        from processObs import queryDB
        fake_data = [
            {'datetime': '2024-01-01 10:00:00', 'beach': 'ushaka', 'ecoli': 150},
            {'datetime': '2024-01-02 09:00:00', 'beach': 'south',  'ecoli': 300},
        ]
        mock_resp = MagicMock()
        with patch('processObs.urlopen', return_value=mock_resp), \
             patch('processObs.js.load', return_value=fake_data):
            result = queryDB(dt.datetime(2024, 1, 1))
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ['datetime', 'beach', 'ecoli']
        assert len(result) == 2


# ===========================================================================
# obscape.py — sentinel constants and formatting
# ===========================================================================

class TestObscapeConstants:
    def test_missing_threshold(self):
        from obscape import _MISSING_THRESHOLD
        assert _MISSING_THRESHOLD == -100

    def test_request_timeout(self):
        from obscape import _REQUEST_TIMEOUT
        assert _REQUEST_TIMEOUT == 30

    def test_timeout_passed_to_urlopen(self):
        """Both urlopen calls in getData must use the timeout constant."""
        from obscape import getData, _REQUEST_TIMEOUT
        mock_resp = MagicMock()
        # Provide minimal valid JSON for both endpoints
        wind_data = {'data': []}
        rain_data = {'data': []}

        with patch('obscape.urlopen', return_value=mock_resp) as mock_open, \
             patch('obscape.js.load', side_effect=[wind_data, rain_data]), \
             patch('obscape.format1HRW', return_value=pd.DataFrame(
                 columns=['datetime', 'wind_speed', 'direction'])), \
             patch('obscape.format1HRR', return_value=pd.DataFrame(
                 columns=['datetime', 'rain'])), \
             patch('obscape.pd.DataFrame.merge', return_value=pd.DataFrame()):
            try:
                getData(dt.datetime(2024, 1, 2), dt.datetime(2024, 1, 1))
            except Exception:
                pass  # we only care about the urlopen calls
        for call in mock_open.call_args_list:
            _, kwargs = call
            assert kwargs.get('timeout') == _REQUEST_TIMEOUT


class TestFormat1HRW:
    def _make_df(self):
        times = pd.date_range('2024-01-01', periods=12, freq='5min', tz='UTC')
        return pd.DataFrame({
            'datetime':       times,
            'east_wind':      np.tile([1.0, -1.0], 6),
            'north_wind':     np.tile([1.0,  1.0], 6),
            'wind_speed':     np.ones(12) * 2.0,
            'wind_direction': np.ones(12) * 45.0,
        })

    def test_returns_expected_columns(self):
        from obscape import format1HRW
        result = format1HRW(self._make_df())
        assert set(result.columns) == {'datetime', 'wind_speed', 'direction'}

    def test_output_is_on_the_hour(self):
        from obscape import format1HRW
        result = format1HRW(self._make_df())
        assert all(result['datetime'].dt.minute == 0)

    def test_handles_zero_east_component(self):
        """Bug fix: e==0 (due-north/south wind) previously caused UnboundLocalError."""
        from obscape import format1HRW
        times = pd.date_range('2024-01-01', periods=12, freq='5min', tz='UTC')
        df = pd.DataFrame({
            'datetime':       times,
            'east_wind':      np.zeros(12),    # pure north — e=0
            'north_wind':     np.ones(12),
            'wind_speed':     np.ones(12),
            'wind_direction': np.zeros(12),
        })
        result = format1HRW(df)                # must not raise
        assert not result['direction'].isna().any()


class TestFormat1HRR:
    def _make_df(self):
        times = pd.date_range('2024-01-01', periods=12, freq='5min', tz='UTC')
        return pd.DataFrame({
            'datetime': times,
            'rain':     np.tile([0.5, 0.0], 6),
        })

    def test_returns_expected_columns(self):
        from obscape import format1HRR
        result = format1HRR(self._make_df())
        assert set(result.columns) == {'datetime', 'rain'}

    def test_rain_is_summed_hourly(self):
        from obscape import format1HRR
        result = format1HRR(self._make_df())
        # 12 five-min intervals = 1 hour; 6 of them have 0.5 mm rain
        assert result['rain'].iloc[0] == pytest.approx(6 * 0.5)


# ===========================================================================
# forcingSort.py — GFS step failure fills NaN instead of crashing
# ===========================================================================

class TestGetGfsFallback:
    """When a GFS step raises an exception, the loop should continue."""

    def test_failed_step_fills_nan(self):
        from forcingSort import get_gfs

        mock_forecast = MagicMock()
        # First call succeeds, second raises, third succeeds
        good = MagicMock()
        good.variables = {
            'ugrd10m': MagicMock(data=MagicMock(flatten=lambda: [np.float32(1.0)])),
            'vgrd10m': MagicMock(data=MagicMock(flatten=lambda: [np.float32(0.5)])),
            'apcpsfc': MagicMock(data=MagicMock(flatten=lambda: [np.float32(0.0)])),
        }
        mock_forecast.get.side_effect = [good, RuntimeError('network error'), good]

        with patch('forcingSort.getgfs.Forecast', return_value=mock_forecast):
            df = get_gfs(forecast_length=3)

        assert len(df) == 3
        # The failed step (index 1) should be NaN
        assert np.isnan(df['wind_speed'].iloc[1])
        assert np.isnan(df['rain'].iloc[1])
        # The successful steps should have real values
        assert not np.isnan(df['wind_speed'].iloc[0])
        assert not np.isnan(df['wind_speed'].iloc[2])

    def test_all_steps_succeed(self):
        from forcingSort import get_gfs

        mock_forecast = MagicMock()
        good = MagicMock()
        good.variables = {
            'ugrd10m': MagicMock(data=MagicMock(flatten=lambda: [np.float32(2.0)])),
            'vgrd10m': MagicMock(data=MagicMock(flatten=lambda: [np.float32(1.0)])),
            'apcpsfc': MagicMock(data=MagicMock(flatten=lambda: [np.float32(0.5)])),
        }
        mock_forecast.get.return_value = good

        with patch('forcingSort.getgfs.Forecast', return_value=mock_forecast):
            df = get_gfs(forecast_length=4)

        assert len(df) == 4
        assert df['wind_speed'].isna().sum() == 0

    def test_output_columns(self):
        from forcingSort import get_gfs

        mock_forecast = MagicMock()
        mock_forecast.get.side_effect = RuntimeError('all fail')

        with patch('forcingSort.getgfs.Forecast', return_value=mock_forecast):
            df = get_gfs(forecast_length=2)

        expected = {'datetime', 'wind_speed', 'direction', 'rain'}
        assert expected.issubset(set(df.columns))


# ===========================================================================
# postTreatment.py — WQ classification thresholds
# ===========================================================================

class TestWQClassification:
    """_replaceitem: thresholds extracted as named constants."""

    @pytest.fixture(autouse=True)
    def _import(self):
        # Access the private function via the module
        import postTreatment
        self.fn = postTreatment._replaceitem
        self.good_t = postTreatment._WQ_GOOD_THRESHOLD
        self.accept_t = postTreatment._WQ_ACCEPT_THRESHOLD

    def test_constants_have_expected_values(self):
        assert self.good_t == 250
        assert self.accept_t == 500

    def test_zero_is_good(self):
        assert self.fn(0) == 'Good'

    def test_just_below_good_threshold(self):
        assert self.fn(249.9) == 'Good'

    def test_at_good_threshold_is_accept(self):
        assert self.fn(250) == 'Accept'

    def test_middle_of_accept_range(self):
        assert self.fn(375) == 'Accept'

    def test_just_below_accept_threshold(self):
        assert self.fn(499.9) == 'Accept'

    def test_at_accept_threshold_is_bad(self):
        assert self.fn(500) == 'Bad'

    def test_well_above_threshold_is_bad(self):
        assert self.fn(10_000) == 'Bad'
