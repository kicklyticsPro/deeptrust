from typing import List, Dict, Any, Optional, Tuple
import math
from collections import defaultdict
from statistics import mean, stdev, median
from datetime import datetime


# =============================================================================
# DISTANCES PMU
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


def format_temps(total_seconds: float) -> str:
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    centis = int(round((total_seconds - int(total_seconds)) * 100))
    return f"{minutes}:{seconds:02d}.{centis:02d}"


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


def round_distance(d) -> Optional[int]:
    if d is None:
        return None
    try:
        return int(round(int(d) / 50) * 50)
    except Exception:
        return None


# =============================================================================
# RÉGRESSION LINÉAIRE
# =============================================================================
def regression_simple(xs: List[float], ys: List[float]) -> Tuple[float, float]:
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


# =============================================================================
# AJUSTEMENTS GLOBAUX (calculés sur toutes les courses de tous les chevaux)
# =============================================================================
def extract_all_performances(performances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                "takm": takm,
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
                "date": c.get("date"),
                "nomJockey": c.get("nomJockey"),
                "nomCheval": c.get("nomCheval"),
            })
    return all_perfs


def compute_global_adjustments(all_perfs: List[Dict[str, Any]]) -> Dict[str, Any]:
    adj = {
        "terrain": {}, "corde": {}, "distance": {},
        "allocation_slope": 0.0, "allocation_intercept": 0.0,
        "participants_slope": 0.0, "participants_intercept": 0.0,
        "poids_slope": 0.0, "poids_intercept": 0.0,
        "global_mean_takm": 0.0,
    }
    if not all_perfs:
        return adj

    global_mean = mean(p["takm"] for p in all_perfs)
    adj["global_mean_takm"] = round(global_mean, 2)

    # Terrain
    terrain_groups = defaultdict(list)
    for p in all_perfs:
        if p["etatTerrain"]:
            terrain_groups[p["etatTerrain"]].append(p["takm"])
    for terrain, times in terrain_groups.items():
        if len(times) >= 3:
            adj["terrain"][terrain] = round(mean(times) - global_mean, 2)

    # Corde
    corde_groups = defaultdict(list)
    for p in all_perfs:
        if p["corde"] is not None:
            corde_groups[str(p["corde"])].append(p["takm"])
    for corde, times in corde_groups.items():
        if len(times) >= 3:
            adj["corde"][corde] = round(mean(times) - global_mean, 2)

    # Distance
    dist_groups = defaultdict(list)
    for p in all_perfs:
        if p["distance_rounded"] is not None:
            dist_groups[str(p["distance_rounded"])].append(p["takm"])
    for dist, times in dist_groups.items():
        if len(times) >= 3:
            adj["distance"][dist] = round(mean(times) - global_mean, 2)

    # Allocation (log)
    alloc_data = [(math.log(max(1, p["allocation"])), p["takm"]) for p in all_perfs if p["allocation"] > 0]
    if len(alloc_data) >= 5:
        xs, ys = zip(*alloc_data)
        slope, intercept = regression_simple(list(xs), list(ys))
        adj["allocation_slope"] = round(slope, 4)
        adj["allocation_intercept"] = round(intercept, 2)

    # Participants
    part_data = [(p["nbParticipants"], p["takm"]) for p in all_perfs if p["nbParticipants"] > 0]
    if len(part_data) >= 5:
        xs, ys = zip(*part_data)
        slope, intercept = regression_simple(list(xs), list(ys))
        adj["participants_slope"] = round(slope, 4)
        adj["participants_intercept"] = round(intercept, 2)

    # Poids
    poids_data = [(p["poidsJockey"], p["takm"]) for p in all_perfs if p["poidsJockey"] is not None]
    if len(poids_data) >= 5:
        xs, ys = zip(*poids_data)
        slope, intercept = regression_simple(list(xs), list(ys))
        adj["poids_slope"] = round(slope, 4)
        adj["poids_intercept"] = round(intercept, 2)

    return adj


# =============================================================================
# TEMPS AJUSTÉ STANDARD (TAS) - temps "normalisé" pour comparer
# =============================================================================
def compute_tas(course: Dict[str, Any], adjustments: Dict[str, Any]) -> Optional[float]:
    """
    Temps Ajusté Standard : temps au km corrigé de tous les facteurs externes.
    Plus le TAS est bas, plus le cheval est rapide en conditions égales.
    """
    place = course.get("place")
    if place is None:
        return None
    takm = compute_temps_au_km(course, place)
    if takm is None:
        return None

    tas = takm
    global_mean = adjustments.get("global_mean_takm", 0)

    # Ajustement terrain
    terrain = course.get("etatTerrain")
    if terrain and terrain in adjustments.get("terrain", {}):
        tas -= adjustments["terrain"][terrain]

    # Ajustement corde
    corde = course.get("corde")
    if corde is not None and str(corde) in adjustments.get("corde", {}):
        tas -= adjustments["corde"][str(corde)]

    # Ajustement distance
    dist_r = round_distance(course.get("distance"))
    if dist_r is not None and str(dist_r) in adjustments.get("distance", {}):
        tas -= adjustments["distance"][str(dist_r)]

    # Ajustement allocation
    allocation = course.get("allocation") or 0
    if allocation > 0 and adjustments.get("allocation_slope", 0) != 0:
        log_alloc = math.log(max(1, allocation))
        expected = adjustments["allocation_slope"] * log_alloc + adjustments["allocation_intercept"]
        tas -= (expected - global_mean)

    # Ajustement participants
    nb_part = course.get("nbParticipants") or 0
    if nb_part > 0 and adjustments.get("participants_slope", 0) != 0:
        expected = adjustments["participants_slope"] * nb_part + adjustments["participants_intercept"]
        tas -= (expected - global_mean)

    # Ajustement poids
    poids = course.get("poidsJockey")
    if poids is not None and adjustments.get("poids_slope", 0) != 0:
        expected = adjustments["poids_slope"] * poids + adjustments["poids_intercept"]
        tas -= (expected - global_mean)

    return round(tas, 2)


# =============================================================================
# PONDÉRATION TEMPORELLE (exponentielle décroissante)
# =============================================================================
def temporal_weight(date_timestamp: Optional[int], half_life_days: float = 365.0) -> float:
    """
    Poids exponentiel : une course il y a 1 an = 0.5, 2 ans = 0.25, etc.
    Les chevaux ne courent pas tous les mois, donc half-life longue.
    """
    if not date_timestamp:
        return 1.0
    now = datetime.now().timestamp() * 1000
    days_ago = (now - date_timestamp) / (1000.0 * 86400.0)
    return math.exp(-days_ago / half_life_days * math.log(2))


# =============================================================================
# ANALYSE D'UN CHEVAL
# =============================================================================
class HorseAnalyzer:
    def __init__(self, horse_info: Dict[str, Any], courses_history: List[Dict[str, Any]],
                 all_courses: List[Dict[str, Any]], adjustments: Dict[str, Any]):
        self.info = horse_info
        self.history = courses_history
        self.all_courses = all_courses  # toutes les courses de tous les chevaux pour head-to-head
        self.adjustments = adjustments

    def attitude(self) -> Dict[str, Any]:
        return {
            "nom": self.info.get("nom"),
            "numPmu": self.info.get("numPmu"),
            "age": self.info.get("age"),
            "sexe": self.info.get("sexe"),
            "race": self.info.get("race"),
            "statut": self.info.get("statut"),
            "corde": self.info.get("placeCorde"),
            "poids": self.info.get("handicapPoids"),
            "jockey": self.info.get("driver"),
            "jockey_change": self.info.get("driverChange"),
            "entraineur": self.info.get("entraineur"),
            "oeilleres": self.info.get("oeilleres"),
            "robe": (self.info.get("robe") or {}).get("libelleLong"),
            "musique": self.info.get("musique"),
            "gainsCarriere": (self.info.get("gainsParticipant") or {}).get("gainsCarriere"),
            "gainsAnneeEnCours": (self.info.get("gainsParticipant") or {}).get("gainsAnneeEnCours"),
            "jumentPleine": self.info.get("jumentPleine"),
            "indicateurInedit": self.info.get("indicateurInedit"),
        }

    def compute_tas_history(self) -> List[Dict[str, Any]]:
        """Calcule le TAS pour chaque course historique."""
        results = []
        for c in self.history:
            place = c.get("place")
            if place is None:
                continue
            tas = compute_tas(c, self.adjustments)
            if tas is None:
                continue
            takm = compute_temps_au_km(c, place)
            results.append({
                "date": c.get("date"),
                "hippodrome": c.get("hippodrome"),
                "distance": c.get("distance"),
                "discipline": c.get("discipline"),
                "place": place,
                "tas": tas,
                "takm": takm,
                "takm_formatted": format_temps(takm) if takm else None,
                "etatTerrain": c.get("etatTerrain"),
                "corde": c.get("corde"),
                "nomJockey": c.get("nomJockey"),
                "poidsJockey": c.get("poidsJockey"),
                "nbParticipants": c.get("nbParticipants") or 0,
                "allocation": c.get("allocation") or 0,
                "nomPrix": c.get("nomPrix"),
            })
        # Trier par date décroissante
        results.sort(key=lambda x: x["date"] or 0, reverse=True)
        return results

    def compute_weighted_tas(self, tas_history: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
        """
        Retourne (tas_moyen, tas_recent, fiabilite, nombre_effectif).
        tas_moyen = moyenne pondérée par date de toutes les courses
        tas_recent = moyenne pondérée des 5 dernières courses
        """
        if not tas_history:
            return None, None, None, 0

        weights = [temporal_weight(c["date"]) for c in tas_history]
        tasses = [c["tas"] for c in tas_history]

        total_weight = sum(weights)
        if total_weight == 0:
            return None, None, None, 0

        tas_moyen = sum(t * w for t, w in zip(tasses, weights)) / total_weight

        # Recent (5 dernières)
        recent = tas_history[:5]
        w_recent = [temporal_weight(c["date"]) for c in recent]
        t_recent = [c["tas"] for c in recent]
        tw = sum(w_recent)
        tas_recent = sum(t * w for t, w in zip(t_recent, w_recent)) / tw if tw > 0 else tas_moyen

        # Fiabilité (écart-type pondéré)
        if len(tasses) >= 2:
            variance = sum(w * (t - tas_moyen) ** 2 for t, w in zip(tasses, weights)) / total_weight
            fiabilite = math.sqrt(variance)
        else:
            fiabilite = 0.0

        # Nombre effectif (somme des poids)
        nombre_effectif = total_weight

        return round(tas_moyen, 2), round(tas_recent, 2), round(fiabilite, 2), round(nombre_effectif, 1)

    def compute_tendance(self, tas_history: List[Dict[str, Any]]) -> float:
        """Tendance linéaire pondérée : pente du TAS sur les 5 dernières courses."""
        recent = tas_history[:5]
        if len(recent) < 3:
            return 0.0

        xs = list(range(len(recent)))
        ys = [c["tas"] for c in recent]
        ws = [temporal_weight(c["date"]) for c in recent]

        # Régression pondérée
        sw = sum(ws)
        if sw == 0:
            return 0.0
        x_mean = sum(x * w for x, w in zip(xs, ws)) / sw
        y_mean = sum(y * w for y, w in zip(ys, ws)) / sw

        num = sum(w * (x - x_mean) * (y - y_mean) for x, y, w in zip(xs, ys, ws))
        den = sum(w * (x - x_mean) ** 2 for x, w in zip(xs, ws))
        if den == 0:
            return 0.0
        return round(num / den, 3)

    def compute_adaptation(self, tas_history: List[Dict[str, Any]],
                          course_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        TAS moyen sur les courses qui correspondent aux critères de la course du jour.
        """
        corde_jour = self.info.get("placeCorde")
        dist_jour = round_distance(course_context.get("distance")) if course_context else None
        disc_jour = course_context.get("discipline") if course_context else None
        hippo_jour = (course_context.get("hippodrome") or {}).get("libelleCourt") if course_context else None
        jockey_jour = self.info.get("driver")

        adapt = []
        weights = []

        for c in tas_history:
            w = temporal_weight(c["date"])
            scores = []
            if corde_jour is not None and c["corde"] == corde_jour:
                scores.append(1.0)
            if dist_jour is not None and round_distance(c["distance"]) == dist_jour:
                scores.append(1.0)
            if disc_jour and c["discipline"] == disc_jour:
                scores.append(1.0)
            if hippo_jour and c["hippodrome"] == hippo_jour:
                scores.append(1.0)
            if jockey_jour and c["nomJockey"] == jockey_jour:
                scores.append(1.0)
            if scores:
                adapt.append(c["tas"])
                weights.append(w * sum(scores) / len(scores))

        if not adapt:
            return {"tas_adaptation": None, "score": 0, "nb_criteres": 0}

        sw = sum(weights)
        tas_adaptation = sum(t * w for t, w in zip(adapt, weights)) / sw if sw > 0 else None

        # Score d'adaptation (0-100) : combien de critères sont bons
        score = 0
        for c in tas_history[:10]:
            matches = 0
            if corde_jour is not None and c["corde"] == corde_jour:
                matches += 1
            if dist_jour is not None and round_distance(c["distance"]) == dist_jour:
                matches += 1
            if disc_jour and c["discipline"] == disc_jour:
                matches += 1
            if hippo_jour and c["hippodrome"] == hippo_jour:
                matches += 1
            if jockey_jour and c["nomJockey"] == jockey_jour:
                matches += 1
            score += matches * temporal_weight(c["date"])

        return {
            "tas_adaptation": round(tas_adaptation, 2) if tas_adaptation else None,
            "score": round(min(100, score), 1),
            "nb_criteres": len([x for x in [corde_jour, dist_jour, disc_jour, hippo_jour, jockey_jour] if x is not None]),
        }

    def compute_head_to_head(self, concurrents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Si ce cheval a déjà couru contre d'autres concurrents de la course du jour,
        calcule le delta de TAS moyen.
        """
        # Construire un index des courses par (date, hippodrome, distance) -> nomCheval -> place/TAS
        # On utilise self.all_courses qui contient les performances de tous les chevaux
        deltas = []
        weights = []

        my_name = self.info.get("nom")
        if not my_name:
            return {"delta_h2h": None, "nb_affrontements": 0}

        for c in self.history:
            my_place = c.get("place")
            if my_place is None:
                continue
            my_tas = compute_tas(c, self.adjustments)
            if my_tas is None:
                continue

            # Chercher dans all_courses les concurrents sur la même course
            for other in concurrents:
                other_name = other.get("nom")
                if not other_name or other_name == my_name:
                    continue
                # Chercher dans all_courses si other a couru cette course
                for p in self.all_courses:
                    if p.get("nomCheval") == other_name:
                        for oc in p.get("courses", []):
                            if (oc.get("date") == c.get("date") and
                                oc.get("hippodrome") == c.get("hippodrome") and
                                oc.get("distance") == c.get("distance")):
                                other_place = oc.get("place")
                                if other_place is not None:
                                    other_tas = compute_tas(oc, self.adjustments)
                                    if other_tas is not None:
                                        delta = my_tas - other_tas  # négatif = j'étais meilleur
                                        deltas.append(delta)
                                        weights.append(temporal_weight(c.get("date")))

        if not deltas:
            return {"delta_h2h": None, "nb_affrontements": 0}

        sw = sum(weights)
        delta_h2h = sum(d * w for d, w in zip(deltas, weights)) / sw if sw > 0 else 0
        return {
            "delta_h2h": round(delta_h2h, 2),
            "nb_affrontements": len(deltas),
        }

    def compute_contextual_bonus(self, course_context: Dict[str, Any]) -> Dict[str, float]:
        """Bonus/malus contextuels pour la course du jour."""
        bonuses = {}
        att = self.attitude()

        # Jockey change
        if att.get("jockey_change") is True:
            bonuses["jockey_change"] = -2.0
        else:
            bonuses["jockey_change"] = 0.0

        # Jument pleine
        if att.get("jumentPleine") is True:
            bonuses["jument_pleine"] = -3.0
        else:
            bonuses["jument_pleine"] = 0.0

        # Inédit (jamais couru)
        if att.get("indicateurInedit") is True:
            bonuses["inedit"] = -5.0
        else:
            bonuses["inedit"] = 0.0

        # Gains élevés cette année
        gains = att.get("gainsAnneeEnCours", 0) or 0
        if gains > 500000:
            bonuses["gains"] = 1.0
        elif gains > 200000:
            bonuses["gains"] = 0.5
        else:
            bonuses["gains"] = 0.0

        # Âge : 3-5 ans = prime, >8 ans = pénalité
        age = att.get("age")
        if age is not None:
            if age <= 3:
                bonuses["age"] = -1.0  # jeune et potentiellement immature
            elif age >= 8:
                bonuses["age"] = -1.5
            else:
                bonuses["age"] = 0.0

        # Poids : comparer au poids historique moyen
        poids_jour = att.get("poids")
        poids_historique = [c.get("poidsJockey") for c in self.history if c.get("poidsJockey") is not None]
        if poids_jour and poids_historique:
            poids_moyen = mean(poids_historique)
            diff = poids_jour / 10.0 - poids_moyen  # poids en kg
            if diff < -2:
                bonuses["poids"] = -1.0  # moins lourd = bonus
            elif diff > 2:
                bonuses["poids"] = 1.0  # plus lourd = malus
            else:
                bonuses["poids"] = 0.0
        else:
            bonuses["poids"] = 0.0

        return bonuses

    def compute_all(self, course_context: Dict[str, Any], concurrents: List[Dict[str, Any]]) -> Dict[str, Any]:
        tas_history = self.compute_tas_history()
        tas_moyen, tas_recent, fiabilite, nombre_effectif = self.compute_weighted_tas(tas_history)
        tendance = self.compute_tendance(tas_history)
        adaptation = self.compute_adaptation(tas_history, course_context)
        h2h = self.compute_head_to_head(concurrents)
        bonuses = self.compute_contextual_bonus(course_context)

        total_bonus = round(sum(bonuses.values()), 2)

        # Score final = projection du temps probable pour la course du jour
        # Base = TAS moyen pondéré, ajusté par adaptation, tendance, bonus/malus, head-to-head
        if tas_moyen is None:
            score_final = 999.9
        else:
            score = tas_moyen

            # Adaptation : si le cheval est meilleur sur les critères de la course du jour, on ajuste
            if adaptation.get("tas_adaptation") is not None:
                score = score * 0.6 + adaptation["tas_adaptation"] * 0.4

            # Bonus/malus contextuels (en secondes au km)
            score = score + total_bonus * 0.1

            # Tendance : si négative (s'améliore = temps diminuent), c'est un bonus
            if tendance is not None and tendance < 0:
                score = score + tendance * 2.0
            elif tendance is not None and tendance > 0:
                score = score + tendance * 0.5

            # Head-to-head : si on a déjà battu les concurrents, bonus
            if h2h.get("delta_h2h") is not None and h2h["delta_h2h"] < 0:
                score = score + h2h["delta_h2h"] * 0.3

            score_final = round(score, 2)

        # Indice de confiance
        confiance = 0
        if nombre_effectif >= 10:
            confiance += 25
        elif nombre_effectif >= 5:
            confiance += 20
        elif nombre_effectif >= 2:
            confiance += 10
        else:
            confiance += 5

        if fiabilite is not None:
            if fiabilite <= 1.0:
                confiance += 20
            elif fiabilite <= 2.0:
                confiance += 15
            elif fiabilite <= 3.0:
                confiance += 10
            else:
                confiance += 5

        if adaptation.get("tas_adaptation") is not None:
            confiance += 15

        if h2h.get("nb_affrontements", 0) > 0:
            confiance += 10

        if tas_recent is not None:
            confiance += 10

        confiance = min(100, confiance)

        return {
            "attitude": self.attitude(),
            "tas_history": tas_history[:10],
            "tas_moyen": tas_moyen,
            "tas_recent": tas_recent,
            "fiabilite": fiabilite,
            "nombre_effectif": nombre_effectif,
            "tendance": tendance,
            "adaptation": adaptation,
            "head_to_head": h2h,
            "bonuses": bonuses,
            "total_bonus": total_bonus,
            "score_final": score_final,
            "indice_confiance": confiance,
        }


# =============================================================================
# BUILD ANALYSES
# =============================================================================
def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    # Extraire toutes les courses pour les ajustements globaux
    all_perfs = extract_all_performances(performances)
    adjustments = compute_global_adjustments(all_perfs)

    # Indexer performances par cheval
    perf_by_num = {}
    for p in performances or []:
        num = p.get("numPmu")
        if num is not None:
            perf_by_num[num] = p.get("courses", [])

    # Concurrents pour head-to-head
    concurrents = [{"nom": h.get("nom"), "numPmu": h.get("numPmu")} for h in participants]

    analyses = []
    for horse in participants:
        num = horse.get("numPmu")
        hist = perf_by_num.get(num, [])
        analyzer = HorseAnalyzer(horse, hist, performances, adjustments)
        analysis = analyzer.compute_all(course_context or {}, concurrents)
        analyses.append(analysis)

    # Classement par score_final croissant (plus bas = meilleur)
    analyses.sort(key=lambda x: x.get("score_final", 999.9))

    # Écarts en longueurs
    distance = course_context.get("distance", 0) if course_context else 0
    discipline = course_context.get("discipline", "PLAT") if course_context else "PLAT"
    best_score = analyses[0].get("score_final") if analyses else None

    for a in analyses:
        score = a.get("score_final")
        if best_score is not None and score is not None and distance > 0:
            diff = score - best_score  # en secondes au km
            diff_course = diff * (distance / 1000.0)
            spl = seconds_per_length(discipline)
            a["ecart_longueurs"] = round(diff_course / spl, 1)
        else:
            a["ecart_longueurs"] = None

        # Projection du temps probable pour la course du jour
        if score is not None and distance > 0:
            a["temps_projete"] = round(score * (distance / 1000.0), 2)
            a["temps_projete_formatted"] = format_temps(a["temps_projete"])
        else:
            a["temps_projete"] = None
            a["temps_projete_formatted"] = None

    return analyses
