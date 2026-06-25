# 🏇 Analyse Turf - Statistiques PMU

Application web Flask qui récupère les données de courses PMU via les endpoints publics de Turfinfo, et produit une analyse statistique détaillée par cheval.

## ⚠️ Avertissement

Cette application utilise les endpoints JSON publics de `turfinfo.api.pmu.fr`. Leur utilisation est à des fins personnelles / éducatives. Respecte les CGU de PMU.fr.

## Fonctionnalités

- Sélection de la date, de la réunion et de la course.
- Analyse de l'**attitude** de chaque cheval sur la course du jour (corde, poids, jockey, entraîneur, musique, gains...).
- Analyse des **performances passées** sur tous les critères turf :
  - Corde
  - Distance (groupée par tranches de 50m)
  - Discipline / spécialité
  - Jockey
  - Hippodrome
  - Terrain (état du sol)
- Statistiques globales : victoires, places, place moyenne, forme sur les 5 dernières courses.
- Historique détaillé des 10 dernières courses avec place, poids, jockey, terrain...
- **Aucune cote n'est affichée ni analysée** : uniquement de la statistique pure.

## Architecture

- `app.py` : serveur Flask et routes API.
- `pmu_client.py` : client HTTP vers les endpoints PMU (programme, participants, performances détaillées).
- `analyzer.py` : moteur de calcul statistique (regroupements par critères, pourcentages, place moyenne).
- `templates/index.html` : interface web monopage.
- `static/css/style.css` : styles sombres et responsifs.

## Endpoints PMU utilisés

- `https://offline.turfinfo.api.pmu.fr/rest/client/7/programme/DDMMYYYY`
- `https://offline.turfinfo.api.pmu.fr/rest/client/7/programme/DDMMYYYY/RX/CY/participants`
- `https://online.turfinfo.api.pmu.fr/rest/client/61/programme/DDMMYYYY/RX/CY/performances-detaillees/pretty`

## Installation

```bash
cd turf_analyzer
pip install -r requirements.txt
```

## Lancement

```bash
python app.py
```

Puis ouvre `http://localhost:5000` dans ton navigateur.

## Utilisation

1. La date du jour est pré-remplie (format JJMMAAAA).
2. Les réunions disponibles se chargent automatiquement.
3. Choisis une réunion, puis une course.
4. Clique sur **Analyser la course**.
5. Les cartes de chaque cheval s'affichent avec attitude + stats + historique.

## Stack technique

- Python 3.10+
- Flask
- requests
- Vanilla JS (frontend)
