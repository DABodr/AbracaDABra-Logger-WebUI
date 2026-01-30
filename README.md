# AbracaDABra Logger WebUI

Interface web moderne pour visualiser et partager les logs de réception DAB/DAB+ d'**AbracaDABra**.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Fonctionnalités

### WebUI (nouvelle)
- **Tableau DX** interactif avec regroupement par mux/fréquence
- **Dropdown TII** cliquable affichant les émetteurs (site, distance, SNR)
- **Carte Leaflet** avec marqueurs RX (bleu) et TX (rouge)
- **Thème sombre** style FM-DX Webserver
- **Auto-refresh** configurable (15s à 2min)
- **Configuration** via interface web (chemins, Telegram, FTP)

### Bot Telegram (intégré)
Commandes disponibles :
- `DX` → tous les mux
- `DX 9B` → filtrer par bloc
- `DX >300` → filtrer par distance
- `LAST` / `LAST 5` → réceptions les plus récentes
- `STATUS` → état du système
- `HELP` → aide

### Export FTP (optionnel)
Upload automatique du tableau HTML vers un serveur FTP.

---

## Installation

### Prérequis
- Python 3.10+
- AbracaDABra avec export CSV activé

### Installation des dépendances

```bash
# Créer un environnement virtuel (recommandé)
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# ou: venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt
```

---

## Lancement

```bash
# Activer l'environnement virtuel
source venv/bin/activate

# Lancer le serveur
python run.py
```

Puis ouvrir http://localhost:8000 dans votre navigateur.

### Options de lancement

```bash
python run.py --host 0.0.0.0 --port 8000        # Accessible sur le réseau local
python run.py --reload                           # Mode développement (auto-reload)
```

---

## Configuration

### Via l'interface web

1. Ouvrir http://localhost:8000
2. Aller dans l'onglet **Configuration**
3. Configurer :
   - **Position RX** : nom et coordonnées du récepteur
   - **Chemins** : dossier CSV AbracaDABra et base TX TII
   - **Telegram** : token du bot et chat IDs autorisés
   - **FTP** : serveur, identifiants, dossier distant

### Via fichier JSON

Le fichier `data/config.json` est créé automatiquement :

```json
{
  "paths": {
    "csv_dir": "/chemin/vers/dossier/csv",
    "tx_db_path": "/chemin/vers/dab-tx-list.csv"
  },
  "rx": {
    "name": "Mon Récepteur",
    "lat": 49.768,
    "lon": 4.72
  },
  "telegram": {
    "token": "123456:ABC...",
    "enabled": true
  }
}
```

### Via variables d'environnement (legacy)

```bash
export ABRACA_CSV_DIR="/home/user/Documents"
export ABRACA_TG_TOKEN="123456:ABC..."
```

---

## Structure du projet

```
AbracaDABra-Logger-WebUI/
├── app/
│   ├── api/
│   │   ├── models/         # Modèles Pydantic
│   │   └── routes/         # Endpoints API REST
│   ├── core/
│   │   ├── csv_parser.py   # Parsing CSV AbracaDABra
│   │   ├── tx_database.py  # Base TX TII
│   │   ├── matcher.py      # Matching RX/TX
│   │   └── telegram_bot.py # Bot Telegram
│   ├── static/             # JS, CSS
│   ├── templates/          # HTML (Jinja2)
│   ├── config.py           # Gestion configuration
│   └── main.py             # Application FastAPI
├── data/
│   └── config.json         # Configuration utilisateur
├── requirements.txt
├── run.py                  # Point d'entrée
└── README.md
```

---

## API REST

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | État du système |
| `GET /api/dx/table` | Données du tableau DX |
| `GET /api/map/markers` | Marqueurs pour la carte |
| `GET /api/config` | Configuration actuelle |
| `PUT /api/config` | Mettre à jour la configuration |

---

## Scripts legacy

Les scripts originaux sont toujours disponibles :

- `abracadabra_dx_bot.py` - Bot Telegram + HTML standalone
- `map_acadabra.py` - Générateur de carte Folium

---

## Dépendances

- **FastAPI** - Framework web async
- **Uvicorn** - Serveur ASGI
- **Pandas** - Traitement des données CSV
- **Pydantic** - Validation des données
- **Requests** - API Telegram
- **Jinja2** - Templates HTML

Frontend (CDN) :
- **Tailwind CSS** - Styling
- **Alpine.js** - Interactivité
- **Leaflet.js** - Carte interactive

---

## Licence

MIT - Voir [LICENSE](LICENSE)
