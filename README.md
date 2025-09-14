# Scraper Marchés Publics Maroc (PRADO)

Scraper modulaire pour extraire les annonces du site `marchespublics.gov.ma`, gérer la pagination PRADO et stocker dans MongoDB.
Will Include a Flask API to query the saved announcements.

---

## Prérequis

- Python 3.8+
- MongoDB (local)
- Packages:
```bash
pip install requests lxml pymongo flask bson
```
## Fichiers fournis

- `config.py` : configuration (URL, selectors, timeouts, Mongo).
- `fetch.py` : manage HTTP session and PRADO pagination (always refreshes PRADO_PAGESTATE before POST).
- `extraction.py` : robust HTML parsing & extraction (returns schema-ready dicts).
- `mongodb_utils.py` : connect & upsert into MongoDB.
- `main.py` : orchestrator to run the scraper.
- `api.py` : small Flask API to query the MongoDB collection.
- `state.json` : (created by scraper) resume state (`current_page`, `prado_state`).
- `scraper.log` : logs.

---
## Installation
1. After cloning the repo.
2. Install dependencies:
```bash
pip install requests lxml pymongo flask bson
```
3. Start MongoDB:
```bash
sudo systemctl start mongod
```
## Usage
### Run scraper (one-shot / limited pages)
```bash
python3 main.py 5 # to scrape 5 pages for testing
```
To force start from page 1, remove `state.json` or run:
```bash
python3 main.py --no-resume 5
```

Run scraper continuously (cron / systemd)
```bash
*/15 * * * * cd /path/to/project && /usr/bin/python3 main.py >> /path/to/project/scraper.log 2>&1
```
`main.py` saves progress to `state.json`, so subsequent runs resume.

---

# API

> [!Warning]
> Not Yet Imlimented
>

## Start API
```bash
python3 api.py
```
Endpoints:
- `GET /api/health`
- `GET /api/annonces` (query params: `reference`, `procedure`, `categorie`, `acheteurPublic`, `datePublication_from` (YYYY-MM-DD), `datePublication_to` (YYYY-MM-DD), `limit`, `skip`)
- `GET /api/annonces/<mongo_object_id>`

Returned JSON keys match the MongoDB document fields:  
`_id, procedure, categorie, datePublication, reference, objet, acheteurPublic, lots, lieuExecution, dateLimite, piecesJointes, lienDeConsultation`

---
## Notes & Tips
- Page-state token: the code always GETs the base search page before POSTing a pagination request to ensure `PRADO_PAGESTATE` is fresh. This is necessary for reliability.
- If the site HTML changes, adapt XPaths in `extraction.py`. Use `simple_body.html` to test selectors.
- Logs: check `scraper.log`.
- To debug extraction quickly, run:
```bash
python3 extraction.py simple_body.html
```
