# AbracaDABra Logger – WebUI SDR

AbracaDABra Logger WebUI est une interface Web moderne de type **SDR dashboard** permettant de visualiser, analyser et exploiter les logs CSV générés par **AbracaDABra** (réception DAB+).

L’interface regroupe en une seule application :
- un **tableau dynamique des multiplex (MUX)**,
- une **carte interactive des sites d’émission (TII / TX)**,
- une **interface de configuration complète**,
- un **backend Python** chargé de l’agrégation et du calcul des distances.

Le projet est pensé pour un usage **DX / monitoring**, local ou sur Raspberry Pi.

---

## ✨ Fonctionnalités principales

### 🔹 Tableau dynamique MUX
- **1 ligne = 1 MUX sur 1 bloc (fréquence)**
  - Exemple :
    - M1 sur **5C** → 1 ligne
    - M1 sur **8C** → 1 autre ligne
- Chaque ligne regroupe **plusieurs sites d’émission** (via plusieurs TII)
- Menu déroulant par ligne :
  - TII (Main-Sub)
  - site d’émission (si connu)
  - distance RX → TX
  - dates de première et dernière réception
- Filtres : bloc, recherche texte, statut actif/inactif

---

### 🔹 Carte interactive
- Basée sur **Leaflet**
- Affichage :
  - position RX
  - sites TX connus (via `dab-tx-list.csv`)
- Calcul automatique des distances (Haversine)
- Interactions croisées tableau ↔ carte

---

### 🔹 Configuration via l’interface Web
- Définition du **dossier des CSV AbracaDABra**
- Détection automatique du **dernier CSV**
- **Suggestions automatiques de dossiers** si l’emplacement est inconnu
- Configuration complète du **bot Telegram**
  - token
  - chat ID(s)
  - activation/désactivation
  - seuils de perte MUX / TII

---

## 🧱 Architecture

```
AbracaDABra-Logger/
│
├── app.py                 # Backend Flask (API + serveur WebUI)
├── config.json            # Configuration sauvegardée
│
├── webui/
│   ├── index.html         # Interface Web (style SDR)
│   ├── styles.css         # Thème sombre / dashboard
│   └── app.js             # Logique UI
│
├── data/
│   └── dab-tx-list.csv    # Base sites TX (optionnelle)
│
└── README.md
```

---

## 🧩 Dépendances

### Système
- Linux (Debian / Raspberry Pi OS recommandé)
- Python **3.9+**

### Python
```bash
pip3 install flask pandas
```

---

## 🚀 Installation

```bash
git clone https://github.com/DABodr/AbracaDABra-Logger.git
cd AbracaDABra-Logger
pip3 install flask pandas
```

---

## ▶️ Démarrage

```bash
python3 app.py
```

Interface accessible sur :
- `http://localhost:5000`
- `http://IP_DU_SERVEUR:5000`

---

## ⚙️ Première configuration

1. Ouvrir l’onglet **Configuration**
2. Cliquer sur **Suggérer dossiers**
3. Vérifier / ajuster le dossier CSV
4. Cliquer sur **Valider**
5. Cliquer sur **Sauver**

Le tableau et la carte se remplissent automatiquement.

---

## 🤖 Bot Telegram (optionnel)

- Renseigner le token et les Chat ID
- Activer les notifications
- Tester avec le bouton **Test Telegram**

---

## 🧠 Logique d’agrégation

- Clé MUX :
```
(bloc, EID)
```
- Plusieurs TII regroupés dans une même ligne MUX
- Distinction stricte par bloc (fréquence)

---

## 🛠️ Évolutions possibles
- Historisation longue durée
- Alertes Telegram avancées
- Export CSV / JSON
- Mode multi-RX

---

## 📄 Licence
Projet expérimental – licence à définir.

---

## 👍 Conclusion
AbracaDABra Logger WebUI fournit une vision claire, moderne et exploitable des réceptions DAB+, sans complexifier l’installation.
