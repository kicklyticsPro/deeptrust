from typing import List, Dict, Any, Optional
import math


# =============================================================================
# MAPPING DES DISTANCES TEXTUELLES PMU
# =============================================================================

DISTANCE_TO_LENGTHS = {
    "UN_NEZ": 0.05,
    "UNE_TETE": 0.1,
    "UN_DEMI_COL": 0.25,
    "UN_COL": 0.5,
    "UNE_LONGUEUR": 1.0,
    "UNE_LONGUEUR_ET_DEMIE": 1.5,
    "DEUX_LONGUEURS": 2.0,
    "DEUX_LONGUEURS_ET_DEMIE": 2.5,
    "TROIS_LONGUEURS": 3.0,
    "TROIS_LONGUEURS_ET_DEMIE": 3.5,
    "QUATRE_LONGUEURS": 4.0,
    "QUATRE_LONGUEURS_ET_DEMIE": 4.5,
    "CINQ_LONGUEURS": 5.0,
    "CINQ_LONGUEURS_ET_DEMIE": 5.5,
    "SIX_LONGUEURS": 6.0,
    "SIX_LONGUEURS_ET_DEMIE": 6.5,
    "SEPT_LONGUEURS": 7.0,
    "SEPT_LONGUEURS_ET_DEMIE": 7.5,
    "HUIT_LONGUEURS": 8.0,
    "DIX_LONGUEURS": 10.0,
    "DEMI_LONGUEUR": 0.5,
    "TROIS_QUARTS_DE_LONGUEUR": 0.75,
    "CINQ_QUARTS_DE_LONGUEUR": 1.25,
    "COURT_NEZ": 0.03,
    "ENCENSEUR": 0.05,  # court nez
    "UN_TIERCE_DE_LONGUEUR": 0.33,
    "DEUX_TIERCES_DE_LONGUEUR": 0.67,
    "UN_DIXIEME_DE_LONGUEUR": 0.1,
    "UN_VINGTIEME_DE_LONGUEUR": 0.05,
}


def text_to_lengths(text: Optional[Any]) -> float:
    """Convertit une distance textuelle PMU en nombre de longueurs."""
    if not text:
        return 0.0
    if isinstance(text, dict):
        text = text.get("knownValue", "")
    if not isinstance(text, str):
        return 0.0
    return DISTANCE_TO_LENGTHS.get(text, 0.0)


def seconds_per_length(discipline: Optional[str]) -> float:
    """Secondes par longueur selon la discipline."""
    if discipline == "PLAT":
        return 0.20
    if discipline in ("TROT", "TROT_ATTELE", "TROT_Monte"):
        return 0.35
    if discipline in ("OBSTACLE", "STEEPLE_CHASE", "CROSS", "HURDLES"):
        return 0.25
    return 0.20


# =============================================================================
# CALCUL DES TEMPS DE COURSE
# =============================================================================

def compute_cumulative_distances(participants_by_place: Dict[Any, Any]) -> Dict[int, float]:
    """
    Calcule la distance cumulative (en longueurs) de chaque place avec le 1er.
    """
    # Convertir les clés en int (depuis JSON elles peuvent être des strings)
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
    """
    Calcule le temps au kilomètre approximatif du cheval pour cette course.
    Retourne None si impossible.
    """
    temps_premier_cs = course_data.get("tempsDuPremier")
    if not temps_premier_cs:
        return None

    temps_premier = temps_premier_cs / 100.0  # centièmes -> secondes
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
    temps_au_km = (temps_cheval / distance) * 1000.0

    return round(temps_au_km, 2)


def format_temps(total_seconds: float) -> str:
    """Formate un temps en secondes en MM:SS.CS."""
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    centis = int(round((total_seconds - int(total_seconds)) * 100))
    return f"{minutes:01d}:{seconds:02d}.{centis:02d}"


# =============================================================================
# ANALYZER
# =============================================================================

class HorseAnalyzer:
    def __init__(self, horse_info: Dict[str, Any], courses_history: List[Dict[str, Any]]):
        self.info = horse_info
        self.history = courses_history

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
            "nombreCourses": self.info.get("nombreCourses"),
            "gainsCarriere": (self.info.get("gainsParticipant") or {}).get("gainsCarriere"),
            "gainsAnneeEnCours": (self.info.get("gainsParticipant") or {}).get("gainsAnneeEnCours"),
        }

    def compute_temps(self, target_distance: Optional[int] = None) -> Dict[str, Any]:
        """
        Calcule les temps au km pour chaque course historique et produit des stats.
        """
        course_temps = []
        for c in self.history:
            place = c.get("place")
            if place is None:
                continue
            takm = compute_temps_au_km(c, place)
            if takm is None:
                continue

            course_temps.append({
                "date": c.get("date"),
                "hippodrome": c.get("hippodrome"),
                "distance": c.get("distance"),
                "discipline": c.get("discipline"),
                "place": place,
                "temps_au_km": takm,
                "temps_formatted": format_temps(takm),
                "allocation": c.get("allocation"),
                "etatTerrain": c.get("etatTerrain"),
                "corde": c.get("corde"),
                "nomJockey": c.get("nomJockey"),
                "poidsJockey": c.get("poidsJockey"),
                "nbParticipants": c.get("nbParticipants"),
            })

        if not course_temps:
            return {
                "total_courses": 0,
                "temps_moyen": None,
                "temps_mediane": None,
                "temps_min": None,
                "temps_max": None,
                "temps_formatted": None,
                "courses_meme_distance": [],
                "temps_meme_distance": None,
                "temps_formatted_meme_distance": None,
                "temps_3_dernieres": None,
                "temps_formatted_3_dernieres": None,
                "ecart_type": None,
                "details": [],
            }

        # Temps global
        all_temps = [c["temps_au_km"] for c in course_temps]
        temps_moyen = sum(all_temps) / len(all_temps)
        temps_mediane = sorted(all_temps)[len(all_temps) // 2]
        temps_min = min(all_temps)
        temps_max = max(all_temps)
        ecart_type = math.sqrt(sum((t - temps_moyen) ** 2 for t in all_temps) / len(all_temps)) if len(all_temps) > 1 else 0.0

        # Temps sur même distance (± 100m de tolérance)
        courses_meme_distance = []
        if target_distance:
            for c in course_temps:
                dist = c.get("distance")
                if dist and abs(dist - target_distance) <= 100:
                    courses_meme_distance.append(c)

        temps_meme_distance = None
        if courses_meme_distance:
            temps = [c["temps_au_km"] for c in courses_meme_distance]
            temps_meme_distance = sum(temps) / len(temps)

        # Temps sur 3 dernières courses
        temps_3_dernieres = None
        if len(course_temps) >= 3:
            temps = [c["temps_au_km"] for c in course_temps[:3]]
            temps_3_dernieres = sum(temps) / len(temps)
        elif course_temps:
            temps = [c["temps_au_km"] for c in course_temps]
            temps_3_dernieres = sum(temps) / len(temps)

        # Temps estimé pour la course du jour
        # Pondération : 50% même distance, 30% global, 20% récent
        poids = []
        valeurs = []
        if temps_meme_distance is not None:
            poids.append(0.50)
            valeurs.append(temps_meme_distance)
        if temps_moyen is not None:
            poids.append(0.30)
            valeurs.append(temps_moyen)
        if temps_3_dernieres is not None:
            poids.append(0.20)
            valeurs.append(temps_3_dernieres)

        if poids:
            total_weight = sum(poids)
            temps_estime = sum(v * w for v, w in zip(valeurs, poids)) / total_weight
        else:
            temps_estime = None

        return {
            "total_courses": len(course_temps),
            "temps_moyen": round(temps_moyen, 2) if temps_moyen is not None else None,
            "temps_mediane": round(temps_mediane, 2) if temps_mediane is not None else None,
            "temps_min": round(temps_min, 2) if temps_min is not None else None,
            "temps_max": round(temps_max, 2) if temps_max is not None else None,
            "temps_formatted": format_temps(temps_moyen) if temps_moyen is not None else None,
            "courses_meme_distance": len(courses_meme_distance),
            "temps_meme_distance": round(temps_meme_distance, 2) if temps_meme_distance is not None else None,
            "temps_formatted_meme_distance": format_temps(temps_meme_distance) if temps_meme_distance is not None else None,
            "temps_3_dernieres": round(temps_3_dernieres, 2) if temps_3_dernieres is not None else None,
            "temps_formatted_3_dernieres": format_temps(temps_3_dernieres) if temps_3_dernieres is not None else None,
            "ecart_type": round(ecart_type, 2) if ecart_type is not None else None,
            "temps_estime": round(temps_estime, 2) if temps_estime is not None else None,
            "temps_estime_formatted": format_temps(temps_estime) if temps_estime is not None else None,
            "details": course_temps,
        }

    def compute_all(self, target_distance: Optional[int] = None) -> Dict[str, Any]:
        return {
            "attitude": self.attitude(),
            "temps": self.compute_temps(target_distance),
        }


def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Associe participants et performances, calcule les temps au km et classe.
    """
    perf_by_num = {}
    for p in performances or []:
        num = p.get("numPmu")
        if num is not None:
            perf_by_num[num] = p.get("courses", [])

    target_distance = course_context.get("distance") if course_context else None

    analyses = []
    for horse in participants:
        num = horse.get("numPmu")
        hist = perf_by_num.get(num, [])
        analyzer = HorseAnalyzer(horse, hist)
        analysis = analyzer.compute_all(target_distance)
        analyses.append(analysis)

    # Classement : temps estimé croissant (plus rapide = meilleur)
    analyses.sort(key=lambda x: x.get("temps", {}).get("temps_estime") or float('inf'))
    return analyses
