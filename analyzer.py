from typing import List, Dict, Any, Optional
import math
from collections import defaultdict
from statistics import mean, stdev
from datetime import datetime


# =============================================================================
# DISTANCES TEXTUELLES PMU -> LONGUEURS
# =============================================================================

DISTANCE_TO_LENGTHS = {
    "UN_NEZ": 0.05, "UNE_TETE": 0.1, "UN_DEMI_COL": 0.25, "UN_COL": 0.5,
    "UNE_LONGUEUR": 1.0, "UNE_LONGUEUR_ET_DEMIE": 1.5, "DEUX_LONGUEURS": 2.0,
    "DEUX_LONGUEURS_ET_DEMIE": 2.5, "TROIS_LONGUEURS": 3.0, "TROIS_LONGUEURS_ET_DEMIE": 3.5,
    "QUATRE_LONGUEURS": 4.0, "QUATRE_LONGUEURS_ET_DEMIE": 4.5, "CINQ_LONGUEURS": 5.0,
    "CINQ_LONGUEURS_ET_DEMIE": 5.5, "SIX_LONGUEURS": 6.0, "SIX_LONGUEURS_ET_DEMIE": 6.5,
    "SEPT_LONGUEURS": 7.0, "SEPT_LONGUEURS_ET_DEMIE": 7.5, "HUIT_LONGUEURS": 8.0,
    "DIX_LONGUEURS": 10.0, "DEMI_LONGUEUR": 0.5, "TROIS_QUARTS_DE_LONGUEUR": 0.75,
    "CINQ_QUARTS_DE_LONGUEUR": 1.25, "COURT_NEZ": 0.03, "ENCENSEUR": 0.05,
    "UN_TIERCE_DE_LONGUEUR": 0.33, "DEUX_TIERCES_DE_LONGUEUR": 0.67,
    "UN_DIXIEME_DE_LONGUEUR": 0.1, "UN_VINGTIEME_DE_LONGUEUR": 0.05,
}


def text_to_lengths(text: Optional[Any]) -> float:
    if not text:
        return 0.0
    if isinstance(text, dict):
        text = text.get("knownValue", "")
    if not isinstance(text, str):
        return 0.0
    return DISTANCE_TO_LENGTHS.get(text, 0.0)


def seconds_per_length(discipline: Optional[str]) -> float:
    if discipline == "PLAT":
        return 0.20
    if discipline in ("TROT", "TROT_ATTELE", "TROT_Monte"):
        return 0.35
    if discipline in ("OBSTACLE", "STEEPLE_CHASE", "CROSS", "HURDLES"):
        return 0.25
    return 0.20


# =============================================================================
# CALCUL TEMPS AU KM
# =============================================================================

def compute_cumulative_distances(participants_by_place: Dict[Any, Any]) -> Dict[int, float]:
    clean = {}
    for k, v in participants_by_place.items():
        try:
            key = int(k)
            clean[key] = v
        except (ValueError, TypeError):
            continue

    sorted_places = sorted(clean.keys())
    if not sorted_places:
        return {}

    cumulative = {sorted_places[0]: 0.0}
    for i in range(1, len(sorted_places)):
        place = sorted_places[i]
        prev_place = sorted_places[i - 1]
        dist_text = clean.get(place, {}).get("distanceAvecPrecedent")
        dist_lengths = text_to_lengths(dist_text)
        cumulative[place] = cumulative.get(prev_place, 0.0) + dist_lengths
    return cumulative


def compute_temps_au_km(course_data: Dict[str, Any], cheval_place: int) -> Optional[float]:
    temps_premier_cs = course_data.get("tempsDuPremier")
    if not temps_premier_cs:
        return None
    temps_premier = temps_premier_cs / 100.0
    distance = course_data.get("distance")
    if not distance or distance <= 0:
        return None
    discipline = course_data.get("discipline", "PLAT")
    participants = course_data.get("participantsByPlace", {})
    if not participants:
        return None
    cumul = compute_cumulative_distances(participants)
    distance_cumul = cumul.get(cheval_place, 0.0)
    spl = seconds_per_length(discipline)
    seconds_behind = distance_cumul * spl
    temps_cheval = temps_premier + seconds_behind
    return (temps_cheval / distance) * 1000.0


def format_temps(total_seconds: float) -> str:
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    centis = int(round((total_seconds - int(total_seconds)) * 100))
    return f"{minutes}:{seconds:02d}.{centis:02d}"


def round_distance(d) -> Optional[int]:
    if d is None:
        return None
    try:
        return int(round(int(d) / 50) * 50)
    except Exception:
        return None


# =============================================================================
# ÉTAPE 1 : COLLECTE DE TOUTES LES PERFORMANCES
# =============================================================================

def extract_all_course_performances(performances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extrait toutes les performances (course par course) de tous les chevaux pour calculer les ajustements globaux."""
    all_perfs = []
    for p in performances or []:
        for c in p.get("courses", []):
            place = c.get("place")
            if place is None:
                continue
            takm = compute_temps_au_km(c, place)
            if takm is None:
                continue
            all_perfs.append({
                "temps_au_km": takm,
                "distance": c.get("distance"),
                "distance_rounded": round_distance(c.get("distance")),
                "discipline": c.get("discipline"),
                "allocation": c.get("allocation") or 0,
                "etatTerrain": c.get("etatTerrain"),
                "corde": c.get("corde"),
                "nbParticipants": c.get("nbParticipants") or 0,
                "poidsJockey": c.get("poidsJockey"),
                "hippodrome": c.get("hippodrome"),
                "place": place,
            })
    return all_perfs


# =============================================================================
# ÉTAPE 2 : AJUSTEMENTS GLOBAUX (calculés sur l'ensemble des données)
# =============================================================================

def compute_adjustments(all_perfs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcule les ajustements moyens par catégorie.
    Retourne des offsets à appliquer au temps au km.
    """
    adj = {
        "terrain": {},
        "corde": {},
        "distance": {},
        "allocation": 0.0,
        "participants": 0.0,
        "poids": 0.0,
    }

    if not all_perfs:
        return adj

    # Moyenne globale de temps au km
    global_mean = mean(p["temps_au_km"] for p in all_perfs)

    # Ajustement par terrain
    terrain_groups = defaultdict(list)
    for p in all_perfs:
        if p["etatTerrain"]:
            terrain_groups[p["etatTerrain"]].append(p["temps_au_km"])
    for terrain, times in terrain_groups.items():
        if len(times) >= 3:
            adj["terrain"][terrain] = round(mean(times) - global_mean, 2)

    # Ajustement par corde
    corde_groups = defaultdict(list)
    for p in all_perfs:
        if p["corde"] is not None:
            corde_groups[str(p["corde"])].append(p["temps_au_km"])
    for corde, times in corde_groups.items():
        if len(times) >= 3:
            adj["corde"][corde] = round(mean(times) - global_mean, 2)

    # Ajustement par distance (tranche de 50m)
    dist_groups = defaultdict(list)
    for p in all_perfs:
        if p["distance_rounded"] is not None:
            dist_groups[str(p["distance_rounded"])].append(p["temps_au_km"])
    for dist, times in dist_groups.items():
        if len(times) >= 3:
            adj["distance"][dist] = round(mean(times) - global_mean, 2)

    # Ajustement par allocation (régression linéaire simple : log(allocation) vs temps)
    alloc_data = [(math.log(max(1, p["allocation"])), p["temps_au_km"]) for p in all_perfs if p["allocation"] > 0]
    if len(alloc_data) >= 5:
        x_mean = mean(x for x, y in alloc_data)
        y_mean = mean(y for x, y in alloc_data)
        num = sum((x - x_mean) * (y - y_mean) for x, y in alloc_data)
        den = sum((x - x_mean) ** 2 for x, y in alloc_data)
        if den != 0:
            slope = num / den  # temps en fonction du log(allocation)
            # Si slope < 0, plus l'allocation est haute, plus le temps est rapide (logique)
            # On ajuste : pour une allocation de 50 000€ (log=10.8), offset = 0
            ref_log = math.log(50000)
            adj["allocation"] = round(-slope * ref_log, 4)  # coefficient d'ajustement

    # Ajustement par nombre de participants (régression linéaire)
    part_data = [(p["nbParticipants"], p["temps_au_km"]) for p in all_perfs if p["nbParticipants"] > 0]
    if len(part_data) >= 5:
        x_mean = mean(x for x, y in part_data)
        y_mean = mean(y for x, y in part_data)
        num = sum((x - x_mean) * (y - y_mean) for x, y in part_data)
        den = sum((x - x_mean) ** 2 for x, y in part_data)
        if den != 0:
            slope = num / den
            adj["participants"] = round(-slope, 4)  # coefficient par partant

    # Ajustement par poids (régression linéaire)
    poids_data = [(p["poidsJockey"], p["temps_au_km"]) for p in all_perfs if p["poidsJockey"] is not None]
    if len(poids_data) >= 5:
        x_mean = mean(x for x, y in poids_data)
        y_mean = mean(y for x, y in poids_data)
        num = sum((x - x_mean) * (y - y_mean) for x, y in poids_data)
        den = sum((x - x_mean) ** 2 for x, y in poids_data)
        if den != 0:
            slope = num / den
            adj["poids"] = round(-slope, 4)  # coefficient par kg

    return adj


# =============================================================================
# ÉTAPE 3 : PERFORMANCE RATING (PR) PAR COURSE
# =============================================================================

def compute_pr(course: Dict[str, Any], adjustments: Dict[str, Any]) -> Optional[float]:
    """
    Calcule le Performance Rating d'une course.
    PR = temps_au_km - ajustements (plus c'est bas, meilleur c'est)
    """
    place = course.get("place")
    if place is None:
        return None
    takm = compute_temps_au_km(course, place)
    if takm is None:
        return None

    pr = takm

    # Ajustement terrain
    terrain = course.get("etatTerrain")
    if terrain and terrain in adjustments.get("terrain", {}):
        pr -= adjustments["terrain"][terrain]

    # Ajustement corde
    corde = course.get("corde")
    if corde is not None and str(corde) in adjustments.get("corde", {}):
        pr -= adjustments["corde"][str(corde)]

    # Ajustement distance
    dist_r = round_distance(course.get("distance"))
    if dist_r is not None and str(dist_r) in adjustments.get("distance", {}):
        pr -= adjustments["distance"][str(dist_r)]

    # Ajustement allocation (niveau de course)
    allocation = course.get("allocation") or 0
    if allocation > 0 and adjustments.get("allocation", 0) != 0:
        # Plus l'allocation est élevée, plus on déduite de temps (c'est une course de meilleur niveau)
        alloc_coeff = adjustments["allocation"]
        pr -= alloc_coeff * math.log(max(1, allocation) / 50000)

    # Ajustement nombre de participants
    nb_part = course.get("nbParticipants") or 0
    if nb_part > 0 and adjustments.get("participants", 0) != 0:
        pr -= adjustments["participants"] * (nb_part - 10)

    # Ajustement poids
    poids = course.get("poidsJockey")
    if poids is not None and adjustments.get("poids", 0) != 0:
        pr -= adjustments["poids"] * (poids - 58.0)

    return round(pr, 2)


# =============================================================================
# ÉTAPE 4 : RATINGS DU CHEVAL
# =============================================================================

def compute_horse_ratings(courses_history: List[Dict[str, Any]], adjustments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcule tous les ratings pour un cheval.
    """
    prs = []
    for c in courses_history:
        pr = compute_pr(c, adjustments)
        if pr is not None:
            prs.append({
                "pr": pr,
                "date": c.get("date"),
                "distance": c.get("distance"),
                "distance_rounded": round_distance(c.get("distance")),
                "corde": c.get("corde"),
                "discipline": c.get("discipline"),
                "hippodrome": c.get("hippodrome"),
                "nomJockey": c.get("nomJockey"),
                "etatTerrain": c.get("etatTerrain"),
                "allocation": c.get("allocation") or 0,
                "place": c.get("place"),
                "temps_au_km": compute_temps_au_km(c, c.get("place")) if c.get("place") is not None else None,
            })

    if not prs:
        return {
            "total_courses": 0,
            "rating_moyen": None,
            "rating_recent": None,
            "rating_tendance": None,
            "rating_fiabilite": None,
            "rating_adaptation": None,
            "score_final": 999.9,
            "details": [],
        }

    # Moyenne pondérée par allocation (courses plus importantes = plus de poids)
    weights = [max(1, p["allocation"] / 10000) for p in prs]
    rating_moyen = round(sum(p["pr"] * w for p, w in zip(prs, weights)) / sum(weights), 2)

    # 3 dernières courses
    recent = prs[:3]
    if recent:
        rating_recent = round(mean(p["pr"] for p in recent), 2)
    else:
        rating_recent = rating_moyen

    # Tendance (régression linéaire sur les 3 dernières)
    if len(recent) >= 2:
        xs = list(range(len(recent)))
        ys = [p["pr"] for p in recent]
        x_mean = mean(xs)
        y_mean = mean(ys)
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        rating_tendance = round(num / den, 3) if den != 0 else 0.0
    else:
        rating_tendance = 0.0

    # Fiabilité (écart-type des PR)
    if len(prs) >= 2:
        try:
            rating_fiabilite = round(stdev([p["pr"] for p in prs]), 2)
        except:
            rating_fiabilite = 0.0
    else:
        rating_fiabilite = 0.0

    return {
        "total_courses": len(prs),
        "rating_moyen": rating_moyen,
        "rating_recent": rating_recent,
        "rating_tendance": rating_tendance,
        "rating_fiabilite": rating_fiabilite,
        "details": prs,
    }


# =============================================================================
# ÉTAPE 5 : ADAPTATION À LA COURSE DU JOUR
# =============================================================================

def compute_adaptation(ratings: Dict[str, Any], course_context: Dict[str, Any], att: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcule le rating d'adaptation à la course du jour.
    Compare le PR sur les critères similaires vs le PR global.
    """
    prs = ratings.get("details", [])
    if not prs:
        return {"rating_adaptation": None, "details": []}

    rating_moyen = ratings.get("rating_moyen")
    if rating_moyen is None:
        return {"rating_adaptation": None, "details": []}

    adapt_details = []
    adapt_scores = []

    # Corde
    corde_jour = att.get("corde")
    if corde_jour is not None:
        prs_corde = [p["pr"] for p in prs if p["corde"] == corde_jour]
        if prs_corde:
            m = round(mean(prs_corde), 2)
            adapt_scores.append(m)
            adapt_details.append({"nom": "Corde", "valeur": corde_jour, "pr": m, "delta": round(m - rating_moyen, 2), "courses": len(prs_corde)})

    # Distance
    dist_jour = round_distance(course_context.get("distance")) if course_context else None
    if dist_jour is not None:
        prs_dist = [p["pr"] for p in prs if p["distance_rounded"] == dist_jour]
        if prs_dist:
            m = round(mean(prs_dist), 2)
            adapt_scores.append(m)
            adapt_details.append({"nom": "Distance", "valeur": f"~{dist_jour}m", "pr": m, "delta": round(m - rating_moyen, 2), "courses": len(prs_dist)})

    # Discipline
    disc_jour = course_context.get("discipline") if course_context else None
    if disc_jour:
        prs_disc = [p["pr"] for p in prs if p["discipline"] == disc_jour]
        if prs_disc:
            m = round(mean(prs_disc), 2)
            adapt_scores.append(m)
            adapt_details.append({"nom": "Discipline", "valeur": disc_jour, "pr": m, "delta": round(m - rating_moyen, 2), "courses": len(prs_disc)})

    # Hippodrome
    hippo_jour = (course_context.get("hippodrome") or {}).get("libelleCourt") if course_context else None
    if hippo_jour:
        prs_hippo = [p["pr"] for p in prs if p["hippodrome"] == hippo_jour]
        if prs_hippo:
            m = round(mean(prs_hippo), 2)
            adapt_scores.append(m)
            adapt_details.append({"nom": "Hippodrome", "valeur": hippo_jour, "pr": m, "delta": round(m - rating_moyen, 2), "courses": len(prs_hippo)})

    # Jockey
    jockey_jour = att.get("jockey")
    if jockey_jour:
        prs_jock = [p["pr"] for p in prs if p["nomJockey"] == jockey_jour]
        if prs_jock:
            m = round(mean(prs_jock), 2)
            adapt_scores.append(m)
            adapt_details.append({"nom": "Jockey", "valeur": jockey_jour, "pr": m, "delta": round(m - rating_moyen, 2), "courses": len(prs_jock)})

    # Terrain
    # On n'a pas l'état terrain du jour, donc on ne l'inclut pas

    if adapt_scores:
        rating_adaptation = round(mean(adapt_scores), 2)
    else:
        rating_adaptation = rating_moyen

    return {"rating_adaptation": rating_adaptation, "details": adapt_details}


# =============================================================================
# ÉTAPE 6 : SCORE FINAL
# =============================================================================

def compute_final_score(ratings: Dict[str, Any], adaptation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score final combiné. Plus c'est bas, meilleur c'est.
    """
    rm = ratings.get("rating_moyen")
    rr = ratings.get("rating_recent")
    rt = ratings.get("rating_tendance")
    rf = ratings.get("rating_fiabilite")
    ra = adaptation.get("rating_adaptation")

    if rm is None:
        return {"score": 999.9, "components": {}}

    # Si pas de rating récent, on utilise le global
    if rr is None:
        rr = rm
    if ra is None:
        ra = rm

    # Tendance : si négative (s'améliore), c'est un bonus
    # On convertit la tendance en ajustement : -0.5 pts par unité de tendance négative
    tendance_bonus = 0.0
    if rt is not None:
        tendance_bonus = -rt * 2.0  # si rt = -0.5 (s'améliore), bonus = +1.0

    # Fiabilité : plus l'écart-type est faible, meilleur c'est
    # On pénalise l'irrégularité : +0.3 pts par point d'écart-type
    fiabilite_penalty = 0.0
    if rf is not None:
        fiabilite_penalty = rf * 0.3

    score = (
        rm * 0.35 +
        rr * 0.30 +
        ra * 0.20 +
        tendance_bonus +
        fiabilite_penalty
    )

    return {
        "score": round(score, 2),
        "components": {
            "rating_moyen": rm,
            "rating_recent": rr,
            "rating_adaptation": ra,
            "tendance_bonus": round(tendance_bonus, 2),
            "fiabilite_penalty": round(fiabilite_penalty, 2),
        }
    }


# =============================================================================
# ANALYZER PRINCIPAL
# =============================================================================

def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Pipeline complet :
    1. Extraire toutes les performances
    2. Calculer les ajustements globaux
    3. Pour chaque cheval, calculer les PR, ratings, adaptation, score
    4. Classer par score croissant
    """
    # Étape 1 & 2 : ajustements globaux
    all_perfs = extract_all_course_performances(performances)
    adjustments = compute_adjustments(all_perfs)

    # Indexer les performances par cheval
    perf_by_num = {}
    for p in performances or []:
        num = p.get("numPmu")
        if num is not None:
            perf_by_num[num] = p.get("courses", [])

    analyses = []
    for horse in participants:
        num = horse.get("numPmu")
        hist = perf_by_num.get(num, [])

        # Attitude
        att = {
            "nom": horse.get("nom"),
            "numPmu": horse.get("numPmu"),
            "age": horse.get("age"),
            "sexe": horse.get("sexe"),
            "race": horse.get("race"),
            "statut": horse.get("statut"),
            "corde": horse.get("placeCorde"),
            "poids": horse.get("handicapPoids"),
            "jockey": horse.get("driver"),
            "jockey_change": horse.get("driverChange"),
            "entraineur": horse.get("entraineur"),
            "oeilleres": horse.get("oeilleres"),
            "robe": (horse.get("robe") or {}).get("libelleLong"),
            "musique": horse.get("musique"),
            "gainsCarriere": (horse.get("gainsParticipant") or {}).get("gainsCarriere"),
            "gainsAnneeEnCours": (horse.get("gainsParticipant") or {}).get("gainsAnneeEnCours"),
        }

        # Ratings
        ratings = compute_horse_ratings(hist, adjustments)
        adaptation = compute_adaptation(ratings, course_context or {}, att)
        final = compute_final_score(ratings, adaptation)

        analyses.append({
            "attitude": att,
            "ratings": ratings,
            "adaptation": adaptation,
            "score": final,
            "adjustments_used": {
                "terrain": len(adjustments.get("terrain", {})),
                "corde": len(adjustments.get("corde", {})),
                "distance": len(adjustments.get("distance", {})),
            }
        })

    # Classement : score croissant (plus bas = meilleur)
    analyses.sort(key=lambda x: x.get("score", {}).get("score", 999.9))
    return analyses
