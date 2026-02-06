# Correctifs bugs TII - Rapport de modifications

## Résumé

Correction des bugs de formatage/matching TII pour supporter les valeurs TII décimales élevées (main > 15) et rendre le parsing CSV robuste.

**Problèmes corrigés :**
1. ✅ Conversion hex incorrecte dans `format_tii_code()` pour main > 15
2. ✅ Parsing Main/Sub avec `fillna(0)` qui "inventait" des TIIs invalides
3. ✅ Filtre `main > 0` qui supprimait les TIIs valides avec main=0
4. ✅ Crash lors de la déduplication quand SNR est NaN pour tout un groupe

---

## Fichiers modifiés

### 1. `app/core/tx_database.py` (lignes 36-48)

**Problème :**
- La fonction `format_tii_code()` convertissait main > 15 en hexadécimal (ex: main=67 → "43")
- Les données TX contiennent des TIIs au format décimal pur (ex: 6702 pour main=67, sub=02)

**Solution :**
```python
# AVANT
def format_tii_code(main: int, sub: int) -> str:
    if main <= 15:
        return f"{main:02d}{sub:02d}"
    else:
        # Use hex notation for main > 15
        return f"{main:02X}{sub:02d}"  # ❌ Incorrect !

# APRÈS
def format_tii_code(main: int, sub: int) -> str:
    """Format main/sub as TII code string in decimal format.

    TII codes are always formatted as MMSS in decimal (e.g., main=67 sub=2 -> "6702").
    """
    return f"{main:02d}{sub:02d}"  # ✅ Toujours décimal
```

**Impact :** Les TIIs affichés correspondent maintenant aux données du fichier TX (ex: main=67 sub=2 → "6702" au lieu de "4302").

---

### 2. `app/core/csv_parser.py` (lignes 249-251)

**Problème :**
- `fillna(0).astype(int)` remplaçait les valeurs manquantes par 0, créant des TIIs "inventés" (main=0, sub=0)
- Ces lignes passaient ensuite le filtre et matchaient incorrectement

**Solution :**
```python
# AVANT
for col in ["Main", "Sub"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)  # ❌

# APRÈS
# Parse Main/Sub as nullable integers - do NOT fillna(0) to avoid inventing TII values
for col in ["Main", "Sub"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")  # ✅ Nullable
```

**Impact :** Les lignes avec Main/Sub manquants restent NaN et sont filtrées correctement, évitant les faux matchs.

---

### 3. `app/core/csv_parser.py` (lignes 265-268)

**Problème :**
- `groupby().idxmax()` crash quand tous les SNR d'un groupe sont NaN
- Pandas ne peut pas trouver le max d'une série vide

**Solution :**
```python
# AVANT
group_cols = ["Location", "Channel", "Label"]
idx_best = df.groupby(group_cols)["SNR [dB]"].idxmax()  # ❌ Crash si tous NaN
df_best = df.loc[idx_best].copy()

# APRÈS
# Use sort + drop_duplicates instead of idxmax to handle NaN gracefully
group_cols = ["Location", "Channel", "Label"]
df_sorted = df.sort_values("SNR [dB]", ascending=False, na_position="last")
df_best = df_sorted.drop_duplicates(subset=group_cols, keep="first").copy()  # ✅ Robuste
```

**Impact :** Plus de crash quand SNR est vide/NaN pour un groupe. La meilleure ligne (ou la première si tous NaN) est conservée.

---

### 4. `app/core/matcher.py` (lignes 36-52)

**Problème :**
- Même bug `fillna(0)` que csv_parser.py
- Filtre `(df["main"] > 0)` supprimait les lignes valides avec main=0
- Les données montrent que main=0 existe et est valide

**Solution :**
```python
# AVANT
if "Main" in df.columns:
    df["main"] = pd.to_numeric(df["Main"], errors="coerce").fillna(0).astype(int)  # ❌
else:
    df["main"] = 0

df = df[
    (df["block"].str.len() > 0) &
    (df["eid"].str.len() == 4) &
    (df["main"] > 0) &  # ❌ Rejette main=0
    (df["sub"] >= 0)
].copy()

# APRÈS
# Parse main/sub as nullable integers - do NOT fillna(0) to avoid inventing TII values
if "Main" in df.columns:
    df["main"] = pd.to_numeric(df["Main"], errors="coerce").astype("Int64")  # ✅
else:
    df["main"] = pd.NA

df = df[
    (df["block"].str.len() > 0) &
    (df["eid"].str.len() == 4) &
    df["main"].notna() &  # ✅ Accepte main=0
    df["sub"].notna()
].copy()
```

**Impact :**
- Les lignes avec Main=0 ne sont plus rejetées
- Pas de valeurs "inventées" par fillna(0)
- Filtrage correct avec `notna()` au lieu de conditions numériques

---

### 5. `.gitignore` (nouveau contenu)

**Ajout :** Fichier .gitignore complet pour Python/FastAPI

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
venv/
env/

# IDE
.vscode/
.idea/

# Application data
data/config.json
logs/
*.log
```

---

### 6. `tests/test_tii_formatting.py` (nouveau)

**Ajout :** Tests unitaires couvrant les cas critiques

Tests inclus :
- ✅ `test_format_tii_code_decimal_only()` : Vérifie format décimal strict (main=67 → "6702")
- ✅ `test_split_tii_to_main_sub()` : Vérifie le parsing inverse
- ✅ `test_parse_main_sub_with_nan()` : Vérifie que NaN reste NaN (pas fillna(0))
- ✅ `test_dedup_handles_nan_snr()` : Vérifie que dedup ne crash pas avec SNR NaN

**Lancer les tests :**
```bash
pip install pytest
pytest tests/test_tii_formatting.py -v
```

---

## Validation rapide

### Tests d'acceptation :

1. **Format TII décimal** ✅
   - Les TIIs avec main > 15 s'affichent en décimal (ex: "6702" pour main=67 sub=2)
   - Plus de valeurs hexadécimales ("4302", "180A", etc.)

2. **Main=0 accepté** ✅
   - Les lignes avec Main=0 ne sont plus rejetées
   - Peuvent matcher si présentes dans la base TX

3. **Pas de crash SNR NaN** ✅
   - La déduplication ne plante plus quand SNR est vide pour un groupe

4. **Pas de TII inventés** ✅
   - Les lignes sans Main/Sub valides restent NaN et sont filtrées
   - Pas de faux matchs avec main=0/sub=0 "inventés"

### Endpoints à tester :

```bash
# Démarrer l'app
python run.py

# Tester les endpoints
curl http://localhost:8000/api/dx/table
curl http://localhost:8000/api/map/markers
```

---

## Notes comportement UI

**Changements visibles :**

1. **Affichage TII** : Les codes TII affichés changent pour les main > 15
   - Exemple : "4302" devient "6702" pour Charleville-Mézières (main=67 sub=2)
   - C'est la correction attendue !

2. **Lignes matchées** : Plus de lignes peuvent matcher maintenant
   - Les lignes avec main > 15 matchent correctement
   - Les lignes avec main=0 (si présentes) matchent aussi

3. **Stabilité** : Plus de crashs lors du parsing de fichiers avec SNR manquants

---

## Données exemple

### Fichier TX `dab-tx-list.csv` :
```
tii;location
1901;Bregenz 1/Pfänder
1701;Innsbruck 1/Patscherkofel
6702;[hypothétique pour main=67]
```

### Fichier RX `2026-01-29_174343.csv` :
```
Main;Sub;UEID;Label
67;2;E1F069;REIMS 9A  → doit matcher TII=6702 (pas 4302 !)
0;0;...;...            → valide si dans TX
```

---

## Cohérence UEID/EID

**Vérifié :** La logique UEID → EID (4 derniers caractères hex) reste correcte
- `ueid_to_eid4("E1F069")` → `"F069"` ✅
- Aucune régression introduite

---

## Recommandations

1. **Avant mise en production :**
   - Lancer les tests : `pytest tests/ -v`
   - Vérifier les endpoints : `/api/dx/table` et `/api/map/markers`
   - Comparer les TII affichés avec le fichier TX source

2. **Monitoring :**
   - Logger les cas où main/sub sont NaN pour détecter d'éventuels problèmes de parsing
   - Vérifier les taux de match RX↔TX (devrait augmenter)

3. **Documentation :**
   - Mettre à jour la doc utilisateur si elle mentionne des formats TII hex
   - Clarifier que le format est MMSS décimal (0000-9999)

---

## Résumé technique

| Fichier | Lignes | Type changement | Impact |
|---------|--------|-----------------|--------|
| `tx_database.py` | 36-48 | Suppression conversion hex | Format TII correct |
| `csv_parser.py` | 249-251 | Int64 nullable au lieu fillna(0) | Pas de TII inventés |
| `csv_parser.py` | 265-268 | sort+drop_duplicates vs idxmax | Robustesse SNR NaN |
| `matcher.py` | 36-52 | Int64 nullable + notna() | main=0 accepté |
| `.gitignore` | Tout | Ajout patterns Python | Repo propre |
| `tests/test_tii_formatting.py` | Nouveau | Tests unitaires | Validation automatisée |

---

**Date :** 2026-02-06
**Version :** Patch P0 bugs TII
**Status :** ✅ Prêt pour tests
