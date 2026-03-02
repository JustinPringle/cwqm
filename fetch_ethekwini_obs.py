#!/usr/bin/env python3
"""
fetch_ethekwini_obs.py
======================
Automatically scrape the latest beach water-quality PDF from durban.gov.za,
extract E. coli counts for each model beach, and push them directly to the
observations MySQL database — replacing the manual pushObs web form.

Pipeline
--------
1. Scrape durban.gov.za homepage → find the "Beach Status" PDF href
2. Download the PDF
3. Extract text from page 1; parse lines matching  DD/MM/YYYY BEACH NUMBER OPEN|CLOSED
4. Map PDF beach names to the 6 model location names
5. INSERT one row per beach into the observations table

Database table schema (from pushObs/inc/post.php)
--------------------------------------------------
observations (UT INT, datetime VARCHAR, beach VARCHAR, ecoli FLOAT)
  UT       : unix timestamp of the time this script ran
  datetime : sample date as 'YYYY-MM-DD HH:MM:SS'  (noon used if no time in PDF)
  beach    : model location name  (point | ushaka | south | north | pirates | country club)
  ecoli    : E. coli count in CFU/100 mL

Database credentials
--------------------
Store in a  db.ini  file next to this script (never commit to git):

    [database]
    host     = www.justinpringle.com
    user     = justiixl
    password = YOUR_PASSWORD
    dbname   = justiixl_CWQM

Or export environment variables:
    export CWQM_DB_HOST=www.justinpringle.com
    export CWQM_DB_USER=justiixl
    export CWQM_DB_PASS=YOUR_PASSWORD
    export CWQM_DB_NAME=justiixl_CWQM

Dependencies
------------
    pip install pdfplumber requests beautifulsoup4 pymysql

Usage
-----
    python fetch_ethekwini_obs.py            # scrape, parse, push
    python fetch_ethekwini_obs.py --dry-run  # scrape & parse only, no DB writes
    python fetch_ethekwini_obs.py --verbose  # debug logging
    python fetch_ethekwini_obs.py --pdf-url <url>  # skip scraping, use this PDF
"""

import argparse
import configparser
import io
import logging
import os
import re
import datetime as dt
import time

import requests
import pdfplumber
from bs4 import BeautifulSoup
import pymysql
import pymysql.cursors

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DURBAN_HOME_URL = "https://www.durban.gov.za"

# Mapping: PDF beach name (upper-case, stripped) → model location name.
# Model names must match the values in observations/obLocs.csv.
BEACH_NAME_MAP = {
    "POINT":         "point",
    "USHAKA":        "ushaka",
    "SOUTH BEACH":   "south",
    "NORTH BEACH":   "north",
    "BATTERY BEACH": "pirates",      # eThekwini name for the Pirates Beach location
    "COUNTRY CLUB":  "country club",
}

MODEL_BEACHES = ["point", "ushaka", "south", "north", "pirates", "country club"]

# Regex: DD/MM/YYYY  BEACH NAME (1-3 words)  E-COLI NUMBER  OPEN|CLOSED
_ROW_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+([A-Z][A-Z ']+?)\s+(\d+)\s+(OPEN|CLOSED)"
)

_REQUEST_TIMEOUT = 60   # seconds


# ---------------------------------------------------------------------------
# Step 1 – Find the PDF URL on the durban.gov.za homepage
# ---------------------------------------------------------------------------

def find_beach_pdf_url() -> str:
    """
    Scrape the durban.gov.za homepage and return the absolute URL of the
    latest beach water-quality PDF.

    The homepage carries an <a> tag whose href matches the pattern
        /uploads/.../beach-water-quality-results-*.pdf
    and whose visible text is "Beach Status".

    Raises RuntimeError if no such link is found.
    """
    logger.info("Fetching durban.gov.za homepage …")
    resp = requests.get(DURBAN_HOME_URL, timeout=_REQUEST_TIMEOUT, verify=False)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "html.parser")

    best_href = None
    for a_tag in soup.find_all("a", href=True):
        href  = a_tag["href"]
        text  = a_tag.get_text(strip=True).lower()
        lower = href.lower()

        is_wq_pdf        = "beach-water-quality" in lower and lower.endswith(".pdf")
        is_beach_status  = "beach status" in text

        if is_wq_pdf or is_beach_status:
            best_href = href
            break   # take the first (most recent) match

    if best_href is None:
        raise RuntimeError(
            "Could not find a beach water-quality PDF link on " + DURBAN_HOME_URL
        )

    if best_href.startswith("http"):
        return best_href
    if best_href.startswith("/"):
        return DURBAN_HOME_URL + best_href
    return DURBAN_HOME_URL + "/" + best_href


# ---------------------------------------------------------------------------
# Step 2 – Download the PDF
# ---------------------------------------------------------------------------

def download_pdf(url: str) -> bytes:
    """Download *url* and return raw bytes."""
    logger.info("Downloading PDF: %s", url)
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT, verify=False)
    resp.raise_for_status()
    logger.info("  %.1f kB received", len(resp.content) / 1024)
    return resp.content


# ---------------------------------------------------------------------------
# Step 3 – Parse the PDF
# ---------------------------------------------------------------------------

def parse_pdf(pdf_bytes: bytes) -> dict:
    """
    Extract E. coli counts from the PDF page 1 text.

    Returns
    -------
    dict  {model_beach_name: {"ecoli": int, "sample_date": datetime, "status": str}}
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text() or ""

    logger.debug("PDF text (page 1):\n%s", text)

    results = {}
    for m in _ROW_RE.finditer(text):
        date_s, beach_raw, ecoli_s, status = m.groups()
        beach_raw  = beach_raw.strip()
        model_name = BEACH_NAME_MAP.get(beach_raw)

        if model_name is None:
            logger.debug("  skipped: %s", beach_raw)
            continue

        # Parse sample date; use noon as the time (PDFs carry date only)
        sample_date = dt.datetime.strptime(date_s, "%d/%m/%Y").replace(hour=12)

        results[model_name] = {
            "ecoli":       int(ecoli_s),
            "sample_date": sample_date,
            "status":      status,
        }
        logger.info("  %-16s  ecoli=%4d  date=%s  status=%s",
                    model_name, int(ecoli_s), date_s, status)

    missing = [b for b in MODEL_BEACHES if b not in results]
    if missing:
        logger.info("Beaches not found in PDF (will not be inserted): %s", missing)

    return results


# ---------------------------------------------------------------------------
# Step 4 – Database credentials
# ---------------------------------------------------------------------------

def load_db_config(ini_path: str = "db.ini") -> dict:
    """
    Load database credentials from environment variables (preferred) or
    a db.ini config file.

    Environment variables (override ini file):
        CWQM_DB_HOST, CWQM_DB_USER, CWQM_DB_PASS, CWQM_DB_NAME

    db.ini format:
        [database]
        host     = www.justinpringle.com
        user     = justiixl
        password = SECRET
        dbname   = justiixl_CWQM
    """
    cfg = {"host": "www.justinpringle.com", "dbname": "justiixl_CWQM"}

    if os.path.exists(ini_path):
        parser = configparser.ConfigParser()
        parser.read(ini_path)
        if parser.has_section("database"):
            cfg.update({k: v for k, v in parser.items("database")})
            logger.debug("DB config loaded from %s", ini_path)

    # Environment variables take precedence
    for env_key, cfg_key in [
        ("CWQM_DB_HOST", "host"),
        ("CWQM_DB_USER", "user"),
        ("CWQM_DB_PASS", "password"),
        ("CWQM_DB_NAME", "dbname"),
    ]:
        val = os.environ.get(env_key)
        if val:
            cfg[cfg_key] = val

    missing = [k for k in ("host", "user", "password", "dbname") if k not in cfg]
    if missing:
        raise RuntimeError(
            "Missing DB credentials: %s.  "
            "Set via environment variables or db.ini." % missing
        )
    return cfg


# ---------------------------------------------------------------------------
# Step 5 – Push to MySQL
# ---------------------------------------------------------------------------

def push_to_db(beach_data: dict, db_cfg: dict, dry_run: bool = False) -> int:
    """
    INSERT one row per beach into the observations table.

    Skips beaches whose (datetime, beach) combination already exists to
    prevent duplicate entries if the script is run multiple times.

    Parameters
    ----------
    beach_data : dict  output of parse_pdf()
    db_cfg     : dict  output of load_db_config()
    dry_run    : bool  if True, log what would be inserted but don't execute

    Returns
    -------
    int  number of rows inserted
    """
    if not beach_data:
        logger.warning("No beach data to push.")
        return 0

    now_ut = int(time.time())
    inserted = 0

    if dry_run:
        logger.info("DRY RUN — no database writes.")

    conn = None if dry_run else pymysql.connect(
        host     = db_cfg["host"],
        user     = db_cfg["user"],
        password = db_cfg["password"],
        database = db_cfg["dbname"],
        charset  = "utf8mb4",
        cursorclass = pymysql.cursors.DictCursor,
    )

    try:
        for beach, info in beach_data.items():
            datetime_str = info["sample_date"].strftime("%Y-%m-%d %H:%M:%S")
            ecoli        = info["ecoli"]

            if dry_run:
                logger.info(
                    "  [DRY RUN] INSERT beach=%-16s  ecoli=%4d  datetime=%s",
                    beach, ecoli, datetime_str,
                )
                inserted += 1
                continue

            with conn.cursor() as cur:
                # Check for existing row with same beach + datetime
                cur.execute(
                    "SELECT id FROM observations WHERE beach = %s AND datetime = %s",
                    (beach, datetime_str),
                )
                if cur.fetchone():
                    logger.info(
                        "  SKIP (already exists): beach=%-16s  datetime=%s",
                        beach, datetime_str,
                    )
                    continue

                cur.execute(
                    """INSERT INTO observations (UT, datetime, beach, ecoli)
                       VALUES (%s, %s, %s, %s)""",
                    (now_ut, datetime_str, beach, ecoli),
                )
            conn.commit()
            logger.info(
                "  INSERTED beach=%-16s  ecoli=%4d  datetime=%s",
                beach, ecoli, datetime_str,
            )
            inserted += 1

    finally:
        if conn:
            conn.close()

    return inserted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(pdf_url: str | None = None, dry_run: bool = False) -> dict:
    """
    Full pipeline: scrape → download → parse → push.

    Parameters
    ----------
    pdf_url : str or None
        If supplied, skip scraping and use this PDF URL directly.
    dry_run : bool
        If True, parse only; do not write to the database.

    Returns
    -------
    dict  {beach_name: {"ecoli": int, "sample_date": datetime, "status": str}}
    """
    url       = pdf_url or find_beach_pdf_url()
    pdf_bytes = download_pdf(url)
    data      = parse_pdf(pdf_bytes)

    if not dry_run:
        db_cfg   = load_db_config()
        n        = push_to_db(data, db_cfg, dry_run=False)
        logger.info("Done — %d row(s) inserted into observations.", n)
    else:
        push_to_db(data, db_cfg={}, dry_run=True)

    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Scrape durban.gov.za for the latest beach water-quality PDF, "
            "extract E. coli counts, and push to the observations MySQL database."
        )
    )
    p.add_argument(
        "--pdf-url",
        metavar="URL",
        default=None,
        help="Use this PDF URL directly instead of scraping durban.gov.za.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse PDF and print what would be inserted; do not write to the DB.",
    )
    p.add_argument(
        "--db-ini",
        metavar="FILE",
        default="db.ini",
        help="Path to db.ini credentials file (default: ./db.ini).",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    logging.basicConfig(
        level   = logging.DEBUG if args.verbose else logging.INFO,
        format  = "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt = "%Y-%m-%d %H:%M:%S",
    )

    # Suppress SSL warnings from urllib3 when verify=False
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url       = args.pdf_url or find_beach_pdf_url()
    pdf_bytes = download_pdf(url)
    data      = parse_pdf(pdf_bytes)

    print("\n── Parsed beach data ─────────────────────────────────")
    print(f"  {'Beach':<16}  {'E. coli':>8}  {'Date':<12}  Status")
    print(f"  {'-'*16}  {'-'*8}  {'-'*12}  ------")
    for beach in MODEL_BEACHES:
        if beach in data:
            info = data[beach]
            print(
                f"  {beach:<16}  {info['ecoli']:>8}  "
                f"{info['sample_date'].strftime('%d/%m/%Y'):<12}  {info['status']}"
            )
        else:
            print(f"  {beach:<16}  {'—':>8}  {'not in PDF':<12}")

    print()

    if args.dry_run:
        push_to_db(data, db_cfg={}, dry_run=True)
    else:
        db_cfg = load_db_config(args.db_ini)
        n      = push_to_db(data, db_cfg)
        print(f"✓ {n} row(s) inserted into observations table.")


if __name__ == "__main__":
    main()
