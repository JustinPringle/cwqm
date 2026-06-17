#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created Tue Jun 17 2026

@author: justinpringle

Open-Meteo weather sourcing for the wozolwandle model. Replaces BOTH the
Obscape observed feed and get_gfs():

    getWeather()  -> one continuous hourly series: the historical-forecast
                     archive for the recent past, spliced to the live forecast
                     for the days ahead. This is the operational entry point.

    getData()     -> a single historical window only. Used for back-fill and
                     for validate.py.

All functions return the same columns, matching the old obscape contract:

    datetime    UTC, tz-aware, hourly
    wind_speed  m/s    (Open-Meteo defaults to km/h -- forced to ms below)
    direction   deg, meteorological "from" bearing (matches model convention)
    rain        mm, preceding-hour sum
"""
import logging
import json as js
import datetime as dt
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

import pandas as pd

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30

# Same parameters and response format across all three; only the host differs.
_FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
_HIST_FORECAST_URL = 'https://historical-forecast-api.open-meteo.com/v1/forecast'
_ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'

_HOURLY_VARS = 'wind_speed_10m,wind_direction_10m,precipitation'

# Durban Point / uShaka. Adjust to taste, or align with the old GFS cell
# (gfs.py used -29.75, 31.0) so the whole series comes from one grid point.
_DEFAULT_LAT = -29.87
_DEFAULT_LON = 31.04


def _fetch(base, params):
    '''GET an Open-Meteo endpoint, applying the shared unit/timezone settings.'''
    params = dict(params)
    params.update({
        'hourly': _HOURLY_VARS,
        'wind_speed_unit': 'ms',      # default is km/h -- the model expects m/s
        'precipitation_unit': 'mm',
        'timezone': 'GMT',            # keep everything UTC internally
    })
    url = base + '?' + urlencode(params)
    logger.info('Open-Meteo GET %s', url)            # no API key -> safe to log
    resp = urlopen(url, timeout=_REQUEST_TIMEOUT)
    data = js.load(resp)
    if data.get('error'):
        raise ValueError('Open-Meteo error: %s' % data.get('reason'))
    return data


def _parse(data):
    '''Turn an Open-Meteo JSON response into the model's weather DataFrame.'''
    h = data['hourly']
    df = pd.DataFrame({
        'datetime': pd.to_datetime(h['time'], utc=True),
        'wind_speed': h['wind_speed_10m'],
        'direction': h['wind_direction_10m'],
        'rain': h['precipitation'],
    })
    # Missing hours come back as null -> NaN. Mirror obscape: rain gaps are dry,
    # wind gaps are filled forward/back. (direction ffill across a gap is a mild
    # circular-mean abuse, as in the original; fine for the rare isolated gap.)
    df['rain'] = df['rain'].fillna(0.0)
    df['wind_speed'] = df['wind_speed'].ffill().bfill()
    df['direction'] = df['direction'].ffill().bfill()
    # wind_direction_10m is already the meteorological "from" bearing, so NO
    # 270-atan2 conversion is needed (unlike the old GFS path).
    return df[['datetime', 'wind_speed', 'direction', 'rain']]


def getData(nowDate: dt.datetime, fromDate: dt.datetime,
            lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON,
            source: str = 'historical_forecast', **_ignored) -> pd.DataFrame:
    '''
    Fetch a historical window [fromDate, nowDate].

    source : {'historical_forecast', 'archive'}
        'historical_forecast' tracks actual conditions, current to within hours.
        'archive' is ERA5 reanalysis (long-term-consistent, but lags ~5 days).
    '''
    base = {'historical_forecast': _HIST_FORECAST_URL,
            'archive': _ARCHIVE_URL}.get(source)
    if base is None:
        raise ValueError("source must be 'historical_forecast' or 'archive'")
    data = _fetch(base, {
        'latitude': lat, 'longitude': lon,
        'start_date': fromDate.strftime('%Y-%m-%d'),
        'end_date': nowDate.strftime('%Y-%m-%d'),
    })
    return _parse(data)


def _getForecast(lat, lon, forecast_days):
    '''Live forecast from 00:00 today through forecast_days.'''
    data = _fetch(_FORECAST_URL, {
        'latitude': lat, 'longitude': lon,
        'forecast_days': forecast_days,
        'past_days': 0,
    })
    return _parse(data)


def getWeather(nowDate: dt.datetime, lat: float = _DEFAULT_LAT,
               lon: float = _DEFAULT_LON, past_days: int = 60,
               forecast_days: int = 2) -> pd.DataFrame:
    '''
    Operational weather series replacing obscape.getData AND get_gfs().

    Recent past (historical-forecast archive) spliced to the live forecast,
    with the boundary set at the last hour the archive actually provides so
    there is no gap between past and forecast.
    '''
    fromDate = nowDate - dt.timedelta(days=past_days)
    past = getData(nowDate, fromDate, lat, lon, source='historical_forecast')
    fut = _getForecast(lat, lon, forecast_days)

    if len(past):
        boundary = past['datetime'].max()
        fut = fut[fut['datetime'] > boundary]

    out = (pd.concat([past, fut], ignore_index=True)
             .drop_duplicates('datetime')
             .sort_values('datetime')
             .reset_index(drop=True))
    return out


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _now = dt.datetime.utcnow()
    w = getWeather(_now)
    print(w.head())
    print(w.tail())
    print('rows:', len(w), 'span:', w['datetime'].min(), '->', w['datetime'].max())
