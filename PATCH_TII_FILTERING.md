# Patch : Filtrage intelligent des TII (3 cas)

## Résumé

Implémentation d'une logique de filtrage à 3 cas pour gérer :
1. Les matches parfaits TX (afficher avec détails)
2. Les EID inconnus = nouveautés DX (afficher sans TX)
3. Les faux TII bugs AbracaDABra (ne pas afficher)

**Date** : 2026-02-06
**Complète** : PATCH_TII_FIXES.md (correctifs bugs TII)

---

## Problème

AbracaDABra génère parfois des TII erronés (bugs du logiciel). Ces faux TII polluent la liste des réceptions :
- Affichent des ensembles qui ne correspondent à aucun émetteur réel
- Empêchent de distinguer les vraies nouveautés DX des erreurs
- Créent de la confusion dans les résultats

---

## Solution : Logique à 3 cas

### ✅ Cas 1 : Match parfait (block, eid, main, sub) dans TX
```
RX: 9A + F069 + main=67 sub=2
TX: 9A + F069 + TII=6702 existe → Charleville-Mézières

→ AFFICHER avec sites TX, distance, azimut, etc.
```

### ✅ Cas 2 : EID totalement inconnu dans TX (nouveauté DX)
```
RX: 12D + 10D3 + main=18 sub=1 (LeBonMux)
TX: EID=10D3 n'existe pas dans la base

→ AFFICHER quand même (surprise DX !)
   - Label: "LeBonMux"
   - EID: "10D3"
   - TII: "1801" (affiché mais pas matché)
   - Sites TX: 0 (inconnu)
```

### ❌ Cas 3 : EID connu dans TX MAIS TII ne matche pas (bug)
```
RX: 5B + 6103 + main=99 sub=99
TX: EID=6103 existe avec d'autres TII (0301, 0307) mais pas 9999

→ NE PAS AFFICHER (faux TII = bug AbracaDABra)
```

---

## Fichiers modifiés

### 1. `app/core/aggregator.py`

**Changements majeurs :**
- Réécriture de `aggregate_to_mux_groups()` avec paramètre `tx_df` pour filtrage
- Séparation en 2 fonctions helper :
  - `_create_mux_group_with_tx()` : Cas 1 (avec détails TX)
  - `_create_mux_group_without_tx()` : Cas 2 (EID inconnu, sans TX)

**Logique :**
```python
# 1. Extraire les EID connus de la base TX
known_eids = set(tx_df["eid"].dropna().unique())

# 2. Grouper les réceptions RX par (Channel, Label, EID)
for (bloc, ensemble, eid), rx_group in grouped_rx:

    # Cas 1: Match parfait → avec TX
    if ensemble_matched.notna():
        mux_group = _create_mux_group_with_tx(...)

    # Cas 3: EID connu mais TII ne matche pas → SKIP
    elif eid in known_eids:
        continue  # Ignorer (faux TII)

    # Cas 2: EID inconnu → sans TX
    else:
        mux_group = _create_mux_group_without_tx(...)
```

**Lignes modifiées :** 20-204

---

### 2. `app/api/routes/dx_data.py`

**Changement :**
Ajout du chargement de `tx_df` pour passer à `aggregate_to_mux_groups()`.

```python
# Get TX database for EID filtering
from ...core.tx_database import get_tx_database
tx_db = get_tx_database()
tx_df = tx_db.get_dataframe()

mux_groups = aggregate_to_mux_groups(
    matched_df=matched_df,
    processed_df=processed_df,
    raw_df=raw_df,
    time_col=time_col,
    tx_df=tx_df,  # ← Nouveau paramètre
)
```

**Lignes modifiées :** 42-62

---

### 3. `app/api/routes/map_data.py`

**Changement :**
Même ajout de `tx_df` pour la cohérence.

**Lignes modifiées :** 40-60

---

## Tests sur données réelles

### Données du fichier `2026-01-29_174343.csv`

**Avant le patch :**
- 77 ensembles reçus (dont beaucoup de faux TII)

**Après le patch :**
- 18 ensembles affichés :
  - 16 avec sites TX (Cas 1)
  - 2 nouveautés DX (Cas 2)
  - ~59 faux TII filtrés (Cas 3)

### Exemples validés

**Cas 1 - Match parfait :**
```
✅ 5B NAM-LUX 1 (EID=6103): 3 sites TX
✅ 9A REIMS 9A (EID=F069): 2 sites TX (dont Charleville main=67 sub=2)
✅ 6C NAM-LUX 2 (EID=6104): 3 sites TX
```

**Cas 2 - Nouveautés DX :**
```
🆕 5A EXPE TDF TFL 5A (EID=FFFE): 0 sites TX (expérimentation TDF)
🆕 12D LeBonMux (EID=10D3): 0 sites TX, TII 1801, 14 stations
```

**Cas 3 - Filtrés (pas affichés) :**
```
❌ Environ 59 ensembles avec EID connus mais TII ne matchant pas
   (bugs AbracaDABra ou TII aberrants)
```

---

## Impact UI

### Avant
```
77 ensembles affichés (beaucoup de bruit/erreurs)
- Impossible de distinguer les vrais des faux
- Liste polluée par des bugs AbracaDABra
```

### Après
```
18 ensembles affichés (signal propre)
- 16 ensembles avec sites TX identifiés
- 2 nouveautés DX à découvrir (EID inconnus)
- Faux TII automatiquement filtrés
```

**Résultat :** Liste DX beaucoup plus claire et pertinente ! 🎯

---

## Validation

### Tests unitaires
Les tests existants continuent de passer :
```bash
./venv/bin/pytest tests/test_tii_formatting.py -v
# 4/4 passed
```

### Test intégration
```bash
./venv/bin/python3 -c "from app.main import app; print('✅ OK')"
# ✅ OK
```

### Test sur données réelles
```python
# 77 ensembles RX → 18 après filtrage ✓
# Cas 1: 16 ensembles avec TX ✓
# Cas 2: 2 nouveautés DX ✓
# Cas 3: ~59 faux TII ignorés ✓
```

---

## Lancement de l'application

```bash
# Activer le venv
source venv/bin/activate

# Ou utiliser directement
./venv/bin/python run.py

# Tester
curl http://localhost:8000/api/dx/table
```

**Résultat attendu :**
- `total_mux`: 18 (au lieu de 77)
- `LeBonMux` apparaît avec `tx_site_count: 0`
- Pas de faux TII dans la liste

---

## Notes techniques

### Groupement par EID
Le groupement est maintenant fait sur `(Channel, Label, EID)` au lieu de `(Channel, Label)` pour gérer correctement les cas où plusieurs EID utilisent le même label.

### Performance
- Pas d'impact significatif (extraction des EID connus en O(n))
- Filtrage en mémoire (pas de requête SQL)
- Cache CSV toujours actif

### Rétrocompatibilité
- Si `tx_df` n'est pas fourni, la fonction utilise la logique fallback (tous les ensembles affichés)
- Pas de breaking change sur l'API publique

---

## Recommandations

1. **Monitoring** : Logger les ensembles filtrés (Cas 3) pour déboguer AbracaDABra si nécessaire
2. **UI** : Ajouter un badge "NOUVEAU" pour les ensembles Cas 2 (EID inconnu)
3. **Documentation** : Expliquer aux utilisateurs pourquoi certains ensembles n'apparaissent pas

---

## Combiné avec PATCH_TII_FIXES.md

Ce patch complète les corrections de bugs TII :
1. **PATCH_TII_FIXES.md** : Format décimal TII + parsing robuste
2. **PATCH_TII_FILTERING.md** (ce patch) : Filtrage intelligent 3 cas

**Ensemble**, ils assurent :
- ✅ Format TII correct (décimal)
- ✅ Parsing robuste (Int64 nullable)
- ✅ Filtrage intelligent (3 cas)
- ✅ Liste DX propre et pertinente

---

**Status** : ✅ Testé et validé sur données réelles
