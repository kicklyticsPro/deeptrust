from typing import List, Dict, Any, Optional
import math
from collections import defaultdict
from statistics import mean, stdev, median
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
# TEMPS AU KM
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
# VITESSE ET SPEED FIGURE
# =============================================================================

def compute_vitesse_ms(temps_au_km: float) -> float:
    """Vitesse en m/s."""
    if temps_au_km <= 0:
        return 0.0
    return 1000.0 / temps_au_km


def compute_speed_figure(temps_au_km: float, allocation: float, nb_participants: int,
                         poids: float, distance: int, discipline: str) -> float:
    """
    Speed Figure (Beyer-like) : score de vitesse ajusté.
    Base 100 = temps de référence standard pour la distance/discipline.
    """
    # Temps de référence standard (en s/km) par discipline
    refs = {
        "PLAT": {1000: 58.0, 1200: 70.0, 1400: 82.0, 1600: 95.0, 1800: 107.0,
                 1900: 113.0, 2000: 119.0, 2100: 125.0, 2200: 131.0, 2400: 143.0,
                 2500: 149.0, 2600: 155.0, 2800: 167.0, 3000: 179.0},
        "TROT": {1600: 72.0, 2100: 95.0, 2700: 122.0, 3000: 135.0},
    }
    ref_temps = None
    for dist, t in refs.get(discipline, {}).items():
        if abs(dist - distance) <= 100:
            ref_temps = t
            break
    if ref_temps is None:
        # Approximation par distance
        ref_temps = (distance / 1000.0) * 58.0 if discipline == "PLAT" else (distance / 1000.0) * 72.0

    # Différence de temps vs référence (plus rapide = plus de points)
    diff = ref_temps - temps_au_km
    base_sf = 100 + diff * 2.0

    # Ajustement allocation : plus la course est riche, plus les points sont valorisés
    alloc_factor = 1.0 + math.log(max(1, allocation) / 10000) * 0.05

    # Ajustement poids : plus lourd = pénalité
    poids_factor = 1.0 - (poids - 55.0) * 0.002 if poids else 1.0

    # Ajustement nombre de participants : plus il y a de monde, plus c'est dur
    part_factor = 1.0 + (nb_participants - 10) * 0.01

    sf = base_sf * alloc_factor * poids_factor * part_factor
    return round(sf, 1)


# =============================================================================
# EXTRACT ALL PERFORMANCES
# =============================================================================

def extract_all_course_performances(performances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
# AJUSTEMENTS GLOBAUX PAR RÉGRESSION
# =============================================================================

def regression_simple(xs: List[float], ys: List[float]) -> tuple[float, float]:
    """Retourne (pente, intercept) par moindres carrés."""
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return 0.0, y_mean
    slope = num / den
    intercept = y_mean - slope * x_mean
    return slope, intercept


def compute_adjustments(all_perfs: List[Dict[str, Any]]) -> Dict[str, Any]:
    adj = {
        "terrain": {}, "corde": {}, "distance": {},
        "allocation_slope": 0.0, "allocation_intercept": 0.0,
        "participants_slope": 0.0, "participants_intercept": 0.0,
        "poids_slope": 0.0, "poids_intercept": 0.0,
        "global_mean_takm": 0.0,
    }

    if not all_perfs:
        return adj

    global_mean = mean(p["temps_au_km"] for p in all_perfs)
    adj["global_mean_takm"] = round(global_mean, 2)

    # Ajustement terrain
    terrain_groups = defaultdict(list)
    for p in all_perfs:
        if p["etatTerrain"]:
            terrain_groups[p["etatTerrain"]].append(p["temps_au_km"])
    for terrain, times in terrain_groups.items():
        if len(times) >= 3:
            adj["terrain"][terrain] = round(mean(times) - global_mean, 2)

    # Ajustement corde
    corde_groups = defaultdict(list)
    for p in all_perfs:
        if p["corde"] is not None:
            corde_groups[str(p["corde"])].append(p["temps_au_km"])
    for corde, times in corde_groups.items():
        if len(times) >= 3:
            adj["corde"][corde] = round(mean(times) - global_mean, 2)

    # Ajustement distance
    dist_groups = defaultdict(list)
    for p in all_perfs:
        if p["distance_rounded"] is not None:
            dist_groups[str(p["distance_rounded"])].append(p["temps_au_km"])
    for dist, times in dist_groups.items():
        if len(times) >= 3:
            adj["distance"][dist] = round(mean(times) - global_mean, 2)

    # Régression allocation (log)
    alloc_data = [(math.log(max(1, p["allocation"])), p["temps_au_km"]) for p in all_perfs if p["allocation"] > 0]
    if len(alloc_data) >= 5:
        xs, ys = zip(*alloc_data)
        slope, intercept = regression_simple(list(xs), list(ys))
        adj["allocation_slope"] = round(slope, 4)
        adj["allocation_intercept"] = round(intercept, 2)

    # Régression participants
    part_data = [(p["nbParticipants"], p["temps_au_km"]) for p in all_perfs if p["nbParticipants"] > 0]
    if len(part_data) >= 5:
        xs, ys = zip(*part_data)
        slope, intercept = regression_simple(list(xs), list(ys))
        adj["participants_slope"] = round(slope, 4)
        adj["participants_intercept"] = round(intercept, 2)

    # Régression poids
    poids_data = [(p["poidsJockey"], p["temps_au_km"]) for p in all_perfs if p["poidsJockey"] is not None]
    if len(poids_data) >= 5:
        xs, ys = zip(*poids_data)
        slope, intercept = regression_simple(list(xs), list(ys))
        adj["poids_slope"] = round(slope, 4)
        adj["poids_intercept"] = round(intercept, 2)

    return adj


# =============================================================================
# PERFORMANCE RATING AJUSTÉ (PRA)
# =============================================================================

def compute_pra(course: Dict[str, Any], adjustments: Dict[str, Any]) -> Optional[float]:
    """Performance Rating Ajusté = temps au km ajusté de tous les facteurs."""
    place = course.get("place")
    if place is None:
        return None
    takm = compute_temps_au_km(course, place)
    if takm is None:
        return None

    pra = takm

    # Ajustement terrain
    terrain = course.get("etatTerrain")
    if terrain and terrain in adjustments.get("terrain", {}):
        pra -= adjustments["terrain"][terrain]

    # Ajustement corde
    corde = course.get("corde")
    if corde is not None and str(corde) in adjustments.get("corde", {}):
        pra -= adjustments["corde"][str(corde)]

    # Ajustement distance
    dist_r = round_distance(course.get("distance"))
    if dist_r is not None and str(dist_r) in adjustments.get("distance", {}):
        pra -= adjustments["distance"][str(dist_r)]

    # Ajustement allocation (régression)
    allocation = course.get("allocation") or 0
    if allocation > 0 and adjustments.get("allocation_slope", 0) != 0:
        log_alloc = math.log(max(1, allocation))
        expected_takm = adjustments["allocation_slope"] * log_alloc + adjustments["allocation_intercept"]
        pra -= (expected_takm - adjustments["global_mean_takm"])

    # Ajustement participants
    nb_part = course.get("nbParticipants") or 0
    if nb_part > 0 and adjustments.get("participants_slope", 0) != 0:
        expected_takm = adjustments["participants_slope"] * nb_part + adjustments["participants_intercept"]
        pra -= (expected_takm - adjustments["global_mean_takm"])

    # Ajustement poids
    poids = course.get("poidsJockey")
    if poids is not None and adjustments.get("poids_slope", 0) != 0:
        expected_takm = adjustments["poids_slope"] * poids + adjustments["poids_intercept"]
        pra -= (expected_takm - adjustments["global_mean_takm"])

    return round(pra, 2)


# =============================================================================
# RATINGS DU CHEVAL
# =============================================================================

def compute_horse_ratings(courses_history: List[Dict[str, Any]], adjustments: Dict[str, Any],
                          course_context: Dict[str, Any], att: Dict[str, Any]) -> Dict[str, Any]:
    pras = []
    speed_figures = []
    for c in courses_history:
        pra = compute_pra(c, adjustments)
        if pra is not None:
            takm = compute_temps_au_km(c, c.get("place", 0)) or pra
            sf = compute_speed_figure(
                takm,
                c.get("allocation") or 0,
                c.get("nbParticipants") or 0,
                c.get("poidsJockey") or 0,
                c.get("distance") or 0,
                c.get("discipline", "PLAT")
            )
            pras.append({
                "pra": pra,
                "sf": sf,
                "takm": takm,
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
                "poidsJockey": c.get("poidsJockey"),
                "nbParticipants": c.get("nbParticipants") or 0,
            })
            speed_figures.append(sf)

    if not pras:
        return {
            "total_courses": 0, "pra_moyen": None, "pra_recent": None,
            "pra_mediane": None, "pra_min": None, "pra_max": None,
            "tendance": None, "fiabilite": None, "speed_figures": [],
            "sf_moyen": None, "sf_recent": None, "details": [],
        }

    # Moyenne pondérée par allocation
    weights = [max(1, p["allocation"] / 10000) for p in pras]
    pra_moyen = round(sum(p["pra"] * w for p, w in zip(pras, weights)) / sum(weights), 2)

    # Médiane
    pra_mediane = round(median([p["pra"] for p in pras]), 2)
    pra_min = round(min(p["pra"] for p in pras), 2)
    pra_max = round(max(p["pra"] for p in pras), 2)

    # Récent (3 dernières)
    recent = pras[:3]
    pra_recent = round(mean(p["pra"] for p in recent), 2) if recent else pra_moyen

    # Tendance (régression polynomiale degré 2 sur les 5 dernières)
    tendance = 0.0
    acceleration = 0.0
    if len(pras) >= 3:
        xs = list(range(len(pras[:5])))
        ys = [p["pra"] for p in pras[:5]]
        if len(xs) >= 3:
            # Régression linéaire simple pour la tendance
            slope, _ = regression_simple(xs, ys)
            tendance = round(slope, 3)

    # Fiabilité (écart-type)
    if len(pras) >= 2:
        try:
            fiabilite = round(stdev([p["pra"] for p in pras]), 2)
        except:
            fiabilite = 0.0
    else:
        fiabilite = 0.0

    # Speed Figures
    sf_moyen = round(mean(speed_figures), 1) if speed_figures else None
    sf_recent = round(mean(speed_figures[:3]), 1) if len(speed_figures) >= 3 else sf_moyen

    return {
        "total_courses": len(pras),
        "pra_moyen": pra_moyen,
        "pra_recent": pra_recent,
        "pra_mediane": pra_mediane,
        "pra_min": pra_min,
        "pra_max": pra_max,
        "tendance": tendance,
        "fiabilite": fiabilite,
        "speed_figures": speed_figures,
        "sf_moyen": sf_moyen,
        "sf_recent": sf_recent,
        "details": pras,
    }


# =============================================================================
# ADAPTATION À LA COURSE DU JOUR
# =============================================================================

def compute_adaptation(ratings: Dict[str, Any], course_context: Dict[str, Any], att: Dict[str, Any]) -> Dict[str, Any]:
    pras = ratings.get("details", [])
    if not pras:
        return {"pra_adaptation": None, "pra_adaptation_vs_moyen": None, "details": [], "adaptation_score": 0}

    pra_moyen = ratings.get("pra_moyen")
    if pra_moyen is None:
        return {"pra_adaptation": None, "pra_adaptation_vs_moyen": None, "details": [], "adaptation_score": 0}

    adapt_details = []
    adapt_pras = []

    # Corde
    corde_jour = att.get("corde")
    if corde_jour is not None:
        pras_corde = [p["pra"] for p in pras if p["corde"] == corde_jour]
        if pras_corde:
            m = round(mean(pras_corde), 2)
            adapt_pras.append(m)
            adapt_details.append({"nom": "Corde", "valeur": corde_jour, "pra": m, "delta": round(m - pra_moyen, 2), "courses": len(pras_corde)})

    # Distance
    dist_jour = round_distance(course_context.get("distance")) if course_context else None
    if dist_jour is not None:
        pras_dist = [p["pra"] for p in pras if p["distance_rounded"] == dist_jour]
        if pras_dist:
            m = round(mean(pras_dist), 2)
            adapt_pras.append(m)
            adapt_details.append({"nom": "Distance", "valeur": f"~{dist_jour}m", "pra": m, "delta": round(m - pra_moyen, 2), "courses": len(pras_dist)})

    # Discipline
    disc_jour = course_context.get("discipline") if course_context else None
    if disc_jour:
        pras_disc = [p["pra"] for p in pras if p["discipline"] == disc_jour]
        if pras_disc:
            m = round(mean(pras_disc), 2)
            adapt_pras.append(m)
            adapt_details.append({"nom": "Discipline", "valeur": disc_jour, "pra": m, "delta": round(m - pra_moyen, 2), "courses": len(pras_disc)})

    # Hippodrome
    hippo_jour = (course_context.get("hippodrome") or {}).get("libelleCourt") if course_context else None
    if hippo_jour:
        pras_hippo = [p["pra"] for p in pras if p["hippodrome"] == hippo_jour]
        if pras_hippo:
            m = round(mean(pras_hippo), 2)
            adapt_pras.append(m)
            adapt_details.append({"nom": "Hippodrome", "valeur": hippo_jour, "pra": m, "delta": round(m - pra_moyen, 2), "courses": len(pras_hippo)})

    # Jockey
    jockey_jour = att.get("jockey")
    if jockey_jour:
        pras_jock = [p["pra"] for p in pras if p["nomJockey"] == jockey_jour]
        if pras_jock:
            m = round(mean(pras_jock), 2)
            adapt_pras.append(m)
            adapt_details.append({"nom": "Jockey", "valeur": jockey_jour, "pra": m, "delta": round(m - pra_moyen, 2), "courses": len(pras_jock)})

    if adapt_pras:
        pra_adaptation = round(mean(adapt_pras), 2)
    else:
        pra_adaptation = pra_moyen

    # Score d'adaptation : 0-100 (plus c'est haut, mieux c'est adapté)
    adaptation_score = 0
    for d in adapt_details:
        if d["delta"] < -1.0:
            adaptation_score += 20  # très bon sur ce critère
        elif d["delta"] < 0:
            adaptation_score += 15
        elif d["delta"] < 1.0:
            adaptation_score += 10
        elif d["delta"] < 2.0:
            adaptation_score += 5
        else:
            adaptation_score += 2

    return {
        "pra_adaptation": pra_adaptation,
        "pra_adaptation_vs_moyen": round(pra_adaptation - pra_moyen, 2) if pra_moyen else None,
        "details": adapt_details,
        "adaptation_score": adaptation_score,
    }


# =============================================================================
# SCORE FINAL ET INDICE DE CONFIANCE
# =============================================================================

def compute_final_score(ratings: Dict[str, Any], adaptation: Dict[str, Any], att: Dict[str, Any]) -> Dict[str, Any]:
    rm = ratings.get("pra_moyen")
    rr = ratings.get("pra_recent")
    ra = adaptation.get("pra_adaptation")
    rt = ratings.get("tendance")
    rf = ratings.get("fiabilite")
    sf = ratings.get("sf_moyen")
    sf_r = ratings.get("sf_recent")
    nb = ratings.get("total_courses", 0)

    if rm is None:
        return {"score": 999.9, "indice_confiance": 0, "components": {}}

    if rr is None:
        rr = rm
    if ra is None:
        ra = rm

    # Tendance : si négative (s'améliore = temps diminuent), c'est un bonus
    tendance_bonus = 0.0
    if rt is not None:
        tendance_bonus = -rt * 3.0  # rt négatif = bonus

    # Fiabilité : pénalité si irrégulier
    fiabilite_penalty = 0.0
    if rf is not None:
        fiabilite_penalty = rf * 0.2

    # Score PRA (plus bas = meilleur)
    score_pra = rm * 0.30 + rr * 0.30 + ra * 0.20 + tendance_bonus + fiabilite_penalty

    # Score Speed Figure (plus haut = meilleur, donc on soustrait)
    score_sf = 0.0
    if sf is not None:
        score_sf = -sf * 0.15  # négatif car plus haut SF = meilleur
    if sf_r is not None:
        score_sf += -sf_r * 0.05

    score = score_pra + score_sf

    # Indice de confiance (0-100)
    confiance = 0
    if nb >= 10:
        confiance += 30
    elif nb >= 5:
        confiance += 20
    elif nb >= 3:
        confiance += 10
    elif nb >= 1:
        confiance += 5
    else:
        confiance += 0

    # Fiabilité faible = plus confiant
    if rf is not None:
        if rf <= 1.0:
            confiance += 25
        elif rf <= 2.0:
            confiance += 20
        elif rf <= 3.0:
            confiance += 15
        elif rf <= 5.0:
            confiance += 10
        else:
            confiance += 5

    # Nombre de critères d'adaptation
    nb_adapt = len(adaptation.get("details", []))
    confiance += min(nb_adapt * 5, 25)

    # Tendance claire
    if rt is not None:
        if abs(rt) >= 1.0:
            confiance += 10
        elif abs(rt) >= 0.5:
            confiance += 5

    confiance = min(100, confiance)

    return {
        "score": round(score, 2),
        "indice_confiance": confiance,
        "components": {
            "pra_moyen": rm,
            "pra_recent": rr,
            "pra_adaptation": ra,
            "tendance_bonus": round(tendance_bonus, 2),
            "fiabilite_penalty": round(fiabilite_penalty, 2),
            "sf_moyen": sf,
            "sf_recent": sf_r,
        }
    }


# =============================================================================
# ÉCART ESTIMÉ EN LONGUEURS
# =============================================================================

def compute_ecart_longueurs(pra_cheval: float, pra_meilleur: float, distance: int, discipline: str = "PLAT") -> float:
    """
    Estime l'écart en longueurs vs le meilleur cheval.
    pra_cheval et pra_meilleur sont en secondes au km.
    distance en mètres.
    """
    if pra_cheval == pra_meilleur or pra_meilleur is None:
        return 0.0
    diff = pra_cheval - pra_meilleur  # en secondes au km
    # Convertir en secondes sur la distance de la course
    diff_course = diff * (distance / 1000.0)
    # 1 longueur = 0.20s pour le plat, 0.35s pour le trot
    spl = seconds_per_length(discipline)
    longueurs = diff_course / spl
    return round(longueurs, 1)


# =============================================================================
# BUILD ANALYSES
# =============================================================================

def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    all_perfs = extract_all_course_performances(performances)
    adjustments = compute_adjustments(all_perfs)

    perf_by_num = {}
    for p in performances or []:
        num = p.get("numPmu")
        if num is not None:
            perf_by_num[num] = p.get("courses", [])

    analyses = []
    for horse in participants:
        num = horse.get("numPmu")
        hist = perf_by_num.get(num, [])

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

        ratings = compute_horse_ratings(hist, adjustments, course_context or {}, att)
        adaptation = compute_adaptation(ratings, course_context or {}, att)
        final = compute_final_score(ratings, adaptation, att)

        analyses.append({
            "attitude": att,
            "ratings": ratings,
            "adaptation": adaptation,
            "score": final,
            "adjustments": {
                "terrain_count": len(adjustments.get("terrain", {})),
                "corde_count": len(adjustments.get("corde", {})),
                "distance_count": len(adjustments.get("distance", {})),
                "global_mean_takm": adjustments.get("global_mean_takm"),
            }
        })

    # Classement : score croissant
    analyses.sort(key=lambda x: x.get("score", {}).get("score", 999.9))

    # Calculer les écarts en longueurs basés sur le PRA (pas le score composite)
    best_pra = analyses[0].get("ratings", {}).get("pra_moyen") if analyses else None
    distance = course_context.get("distance", 0) if course_context else 0
    discipline = course_context.get("discipline", "PLAT") if course_context else "PLAT"
    for a in analyses:
        pra = a.get("ratings", {}).get("pra_moyen")
        if best_pra is not None and pra is not None and distance > 0:
            a["ecart_longueurs"] = compute_ecart_longueurs(pra, best_pra, distance, discipline)
        else:
            a["ecart_longueurs"] = None

    return analyses
