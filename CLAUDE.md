# AbracaDABra Logger WebUI - Guide Claude

## Description du projet

Interface web (FastAPI) pour visualiser les logs de réception DAB+ produits par le logiciel AbracaDABra.
Elle parse les fichiers CSV de scan, les confronte à une base de données des émetteurs TX (dab-tx-list.csv),
et affiche les résultats sur un tableau et une carte.

## Stack technique

- **Backend** : Python 3.11, FastAPI, uvicorn, pydantic v2, pydantic-settings
- **Data** : pandas (Int64 nullable obligatoire pour Main/Sub)
- **Templates** : Jinja2
- **Bot** : Telegram via API HTTP (lib `requests` + thread `schedule`)
- **Config** : `data/config.json` (persistant) + variables d'env legacy

## Lancer l'application

```bash
source venv/bin/activate
python run.py                          # http://0.0.0.0:8000
python run.py --reload --debug         # dev avec auto-reload
```

## Architecture

```
app/
  main.py           # FastAPI app, lifespan, routers, index
  config.py         # AppConfig (pydantic), load/save/get_config()
  api/routes/
    status.py       # /api/status
    dx_data.py      # /api/dx/table
    map_data.py     # /api/map/markers
    config.py       # /api/config (GET/POST)
    telegram.py     # /api/telegram/...
  core/
    csv_parser.py   # Parsing CSV AbracaDABra, CSVCache, parse_all_abraca_csvs()
    matcher.py      # Matching RX <-> TX (TII matching)
    tx_database.py  # Chargement dab-tx-list.csv, format_tii_code()
    aggregator.py   # Agregation des données pour l'UI
    telegram_bot.py # Bot Telegram (thread separé)
  static/           # CSS, JS
  templates/        # index.html (Jinja2)
```

## Conventions critiques

### Format TII (IMPORTANT)
- Les codes TII sont **TOUJOURS en decimal** : `f"{main:02d}{sub:02d}"`
- Exemple : main=67, sub=2 → `"6702"` (PAS `"4302"` en hex)
- Voir `app/core/tx_database.py` : `format_tii_code()`

### Parsing Main/Sub (IMPORTANT)
- Toujours utiliser `pd.to_numeric(..., errors="coerce").astype("Int64")` (nullable)
- **Ne jamais** utiliser `.fillna(0)` : cela invente des TIIs invalides
- Filtrer avec `.notna()` et non `> 0` (main=0 est valide)

### Deduplication CSV
- Utiliser `sort_values + drop_duplicates` (pas `idxmax`) : robuste aux SNR NaN
- Grouper par `["Location", "Channel", "Label"]`

## Configuration

Fichier : `data/config.json` (créé automatiquement)

Sections :
- `paths.csv_dir` : dossier des CSV de scan AbracaDABra
- `paths.tx_db_path` : chemin vers `dab-tx-list.csv`
- `rx.lat` / `rx.lon` / `rx.name` : position du récepteur
- `telegram.token` / `telegram.enabled` : bot Telegram
- `refresh_interval_sec` : intervalle auto-refresh UI

Variables d'environnement legacy : `ABRACA_TG_TOKEN`, `ABRACA_CSV_DIR`, etc.

## Format CSV AbracaDABra

Séparateur `;`, encodage UTF-8.
Colonnes requises : `Label`, `Channel`, `Location`, `SNR [dB]`
Colonnes optionnelles : `Main`, `Sub`, `UEID`, `Distance [km]`, `Power [kW]`, `Azimuth [deg]`, `Services`
Nom de fichier attendu : `YYYY-MM-DD_HHMMSS.csv`

## Tests

```bash
pytest tests/ -v
pytest tests/test_tii_formatting.py -v   # Tests critiques TII
```
