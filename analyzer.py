from collections import defaultdict
from typing import List, Dict, Any, Optional
import math


# =============================================================================
# POINTS PMU CLASSIQUES
# =============================================================================

def points_pmu(place: Optional[int]) -> int:
    """
    Attribution de points classiques selon la place en course.
    1er=25, 2ème=20, 3ème=16, 4ème=13, 5ème=11, 6ème=10,
    7ème=9, 8ème=8, 9ème=7, 10ème=6, 11-15=3, >15=1, non classé=0
    """
    if place is None:
        return 0
    if place == 1:
        return 25
    if place == 2:
        return 20
    if place == 3:
        return 16
    if place == 4:
        return 13
    if place == 5:
        return 11
    if place == 6:
        return 10
    if place == 7:
        return 9
    if place == 8:
        return 8
    if place == 9:
        return 7
    if place == 10:
        return 6
    if place <= 15:
        return 3
    return 1


# =============================================================================
# UTILITAIRES
# =============================================================================

def _extract_historique(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise les courses et les trie par date décroissante (plus récent en premier)."""
    out = []
    for c in courses:
        out.append({
            "date": c.get("date"),
            "hippodrome": c.get("hippodrome"),
            "discipline": c.get("discipline"),
            "distance": c.get("distance"),
            "corde": c.get("corde"),
            "place": c.get("place"),
            "nbParticipants": c.get("nbParticipants") or 0,
            "poidsJockey": c.get("poidsJockey"),
            "nomJockey": c.get("nomJockey"),
            "etatTerrain": c.get("etatTerrain"),
            "statusArrivee": c.get("statusArrivee"),
            "nomPrix": c.get("nomPrix"),
            "allocation": c.get("allocation") or 0,
        })
    out.sort(key=lambda x: x["date"] or 0, reverse=True)
    return out


def _round_distance(d) -> Optional[int]:
    if d is None:
        return None
    try:
        return int(round(int(d) / 50) * 50)
    except Exception:
        return None


# =============================================================================
# MÉTHODE PRINCIPALE : SCORE DE PERFORMANCE PMU
# =============================================================================

def _score_courses(courses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calcule le score moyen PMU sur une liste de courses."""
    if not courses:
        return {"score": 0, "total": 0, "places_valides": 0, "place_moy": None, "nb_victoires": 0, "nb_places": 0}

    total_pts = 0
    places_valides = []
    nb_victoires = 0
    nb_places = 0
    for c in courses:
        place = c.get("place")
        pts = points_pmu(place)
        total_pts += pts
        if place is not None:
            places_valides.append(place)
            if place == 1:
                nb_victoires += 1
            if place <= 3:
                nb_places += 1

    n = len(courses)
    score = round(total_pts / n, 1)
    place_moy = round(sum(places_valides) / len(places_valides), 1) if places_valides else None
    return {
        "score": score,
        "total": n,
        "places_valides": len(places_valides),
        "place_moy": place_moy,
        "nb_victoires": nb_victoires,
        "nb_places": nb_places,
    }


def _score_adaptation(courses_critere: List[Dict[str, Any]], global_score: float) -> Dict[str, Any]:
    """
    Score sur un critère spécifique comparé au score global.
    Retourne un dict avec le score du critère et le delta vs global.
    """
    base = _score_courses(courses_critere)
    delta = round(base["score"] - global_score, 1) if global_score > 0 else 0
    return {**base, "delta": delta}


# =============================================================================
# PARSING MUSIQUE PMU
# =============================================================================

def _parse_musique(musique: Optional[str]) -> List[str]:
    """
    Parse la musique PMU.
    Ex: '1p3p(25)4p6p4p' -> ['1','p','3','p','4','p','6','p','4']
    (25) = corde, on ignore. a=arrêté, t=tombé, d=dérouté, r=retiré.
    """
    if not musique:
        return []
    symbols = []
    skip = False
    for ch in musique:
        if ch == '(':
            skip = True
            continue
        if ch == ')':
            skip = False
            continue
        if skip:
            continue
        if ch.isdigit() or ch in 'patdr':
            symbols.append(ch)
    return symbols


def _musique_score(symbols: List[str]) -> Dict[str, Any]:
    """
    Score sur les 5 derniers symboles de la musique.
    La course la plus récente est le DERNIER symbole de la chaîne.
    On pondère dégressivement : dernier x2, avant-dernier x1.5, etc.
    """
    if not symbols:
        return {"score": 0, "details": []}

    last = symbols[-5:][::-1]  # du plus récent au plus ancien
    weights = [2.0, 1.5, 1.2, 1.0, 0.8]
    total_pts = 0
    max_pts = 0
    details = []

    for i, sym in enumerate(last):
        w = weights[i] if i < len(weights) else 0.6
        if sym.isdigit():
            pts = points_pmu(int(sym))
        elif sym == 'p':
            pts = 3  # placé sans précision
        else:
            pts = 0  # incident
        total_pts += pts * w
        max_pts += 25 * w
        details.append({"sym": sym, "pts": pts, "weight": w, "weighted": round(pts * w, 1)})

    score = round((total_pts / max_pts) * 25, 1) if max_pts > 0 else 0
    return {"score": score, "details": details}


# =============================================================================
# ANALYZER CHEVAL
# =============================================================================

class HorseAnalyzer:
    def __init__(self, horse_info: Dict[str, Any], courses_history: List[Dict[str, Any]]):
        self.info = horse_info
        self.history = _extract_historique(courses_history)

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
            "nombreVictoires": self.info.get("nombreVictoires"),
            "gainsCarriere": (self.info.get("gainsParticipant") or {}).get("gainsCarriere"),
            "gainsAnneeEnCours": (self.info.get("gainsParticipant") or {}).get("gainsAnneeEnCours"),
            "indicateurInedit": self.info.get("indicateurInedit"),
            "allure": self.info.get("allure"),
            "jumentPleine": self.info.get("jumentPleine"),
            "engagement": self.info.get("engagement"),
            "supplement": self.info.get("supplement"),
            "eleveur": self.info.get("eleveur"),
            "paysEntrainement": self.info.get("paysEntrainement"),
        }

    def compute_all(self) -> Dict[str, Any]:
        # --- Scores globaux ---
        global_score = _score_courses(self.history)
        recent_courses = self.history[:5]
        recent_score = _score_courses(recent_courses)

        # --- Musique ---
        musique_symbols = _parse_musique(self.info.get("musique"))
        musique_score = _musique_score(musique_symbols)

        # --- Scores par critère ---
        by_corde = self._by_corde()
        by_distance = self._by_distance()
        by_discipline = self._by_discipline()
        by_jockey = self._by_jockey()
        by_hippodrome = self._by_hippodrome()
        by_terrain = self._by_terrain()

        return {
            "attitude": self.attitude(),
            "global": global_score,
            "recent": recent_score,
            "musique": musique_score,
            "byCorde": by_corde,
            "byDistance": by_distance,
            "byDiscipline": by_discipline,
            "byJockey": by_jockey,
            "byHippodrome": by_hippodrome,
            "byTerrain": by_terrain,
            "history": self.history[:10],
        }

    def _by_corde(self) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = c["corde"] if c["corde"] is not None else "N/A"
            buckets[k].append(c)
        return {str(k): _score_adaptation(v, self._global_score_raw()) for k, v in buckets.items()}

    def _by_distance(self) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = _round_distance(c.get("distance"))
            if k is None:
                k = "N/A"
            buckets[k].append(c)
        return {str(k): _score_adaptation(v, self._global_score_raw()) for k, v in buckets.items()}

    def _by_discipline(self) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = c["discipline"] if c["discipline"] else "N/A"
            buckets[k].append(c)
        return {str(k): _score_adaptation(v, self._global_score_raw()) for k, v in buckets.items()}

    def _by_jockey(self) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = c["nomJockey"] if c["nomJockey"] else "N/A"
            buckets[k].append(c)
        return {str(k): _score_adaptation(v, self._global_score_raw()) for k, v in buckets.items()}

    def _by_hippodrome(self) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = c["hippodrome"] if c["hippodrome"] else "N/A"
            buckets[k].append(c)
        return {str(k): _score_adaptation(v, self._global_score_raw()) for k, v in buckets.items()}

    def _by_terrain(self) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = c["etatTerrain"] if c["etatTerrain"] else "N/A"
            buckets[k].append(c)
        return {str(k): _score_adaptation(v, self._global_score_raw()) for k, v in buckets.items()}

    def _global_score_raw(self) -> float:
        return _score_courses(self.history)["score"]


# =============================================================================
# RATING FINAL - MÉTHODE DE SYNTHÈSE
# =============================================================================

def compute_rating(analysis: Dict[str, Any], course_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcule le rating final de chaque cheval selon la méthode des Points PMU.
    
    Rating = moyenne pondérée de :
    - Score Global (toutes les courses) : 25%
    - Score Récent (5 dernières) : 30%
    - Musique (5 derniers résultats) : 15%
    - Adaptation course du jour : 30% (moyenne des 5 critères corde/distance/discipline/hippodrome/jockey)
    """
    if not analysis:
        return {"total": 0}

    att = analysis.get("attitude", {})
    glob = analysis.get("global", {})
    recent = analysis.get("recent", {})
    musique = analysis.get("musique", {})

    score_global = glob.get("score", 0)
    score_recent = recent.get("score", 0)
    score_musique = musique.get("score", 0)

    # --- Adaptation course du jour ---
    corde = att.get("corde")
    distance = course_context.get("distance") if course_context else None
    distance_rounded = _round_distance(distance)
    discipline = course_context.get("discipline") if course_context else None
    hippodrome = (course_context.get("hippodrome") or {}).get("libelleCourt") if course_context else None
    jockey = att.get("jockey")

    adaptation_scores = []
    adaptation_details = {}

    # Corde
    if corde is not None and analysis.get("byCorde"):
        key = str(corde)
        if key in analysis["byCorde"]:
            s = analysis["byCorde"][key].get("score", 0)
            adaptation_scores.append(s)
            adaptation_details["corde"] = round(s, 1)

    # Distance
    if distance_rounded is not None and analysis.get("byDistance"):
        key = str(distance_rounded)
        if key in analysis["byDistance"]:
            s = analysis["byDistance"][key].get("score", 0)
            adaptation_scores.append(s)
            adaptation_details["distance"] = round(s, 1)

    # Discipline
    if discipline and analysis.get("byDiscipline"):
        key = str(discipline)
        if key in analysis["byDiscipline"]:
            s = analysis["byDiscipline"][key].get("score", 0)
            adaptation_scores.append(s)
            adaptation_details["discipline"] = round(s, 1)

    # Hippodrome
    if hippodrome and analysis.get("byHippodrome"):
        key = str(hippodrome)
        if key in analysis["byHippodrome"]:
            s = analysis["byHippodrome"][key].get("score", 0)
            adaptation_scores.append(s)
            adaptation_details["hippodrome"] = round(s, 1)

    # Jockey
    if jockey and analysis.get("byJockey"):
        key = str(jockey)
        if key in analysis["byJockey"]:
            s = analysis["byJockey"][key].get("score", 0)
            adaptation_scores.append(s)
            adaptation_details["jockey"] = round(s, 1)

    if adaptation_scores:
        score_adaptation = round(sum(adaptation_scores) / len(adaptation_scores), 1)
    else:
        score_adaptation = score_global * 0.8  # si pas d'adaptation, on prend 80% du global

    # --- Bonus/Malus simples ---
    bonus = 0.0

    # Inédit (jamais couru) = -3
    if glob.get("total", 0) == 0:
        bonus -= 3.0

    # Changement de jockey = -2
    if att.get("jockey_change") is True:
        bonus -= 2.0

    # Dernière course = victoire = +2
    hist = analysis.get("history", [])
    if hist and hist[0].get("place") == 1:
        bonus += 2.0

    # Musique commence par 1 (dernier résultat = victoire)
    if musique_symbols := _parse_musique(att.get("musique", "")):
        if musique_symbols[-1] == '1':
            bonus += 1.5

    # Gains élevés cette année = +1
    gains = att.get("gainsAnneeEnCours", 0) or 0
    if gains > 500000:
        bonus += 1.0

    # --- Rating final ---
    rating = (
        score_global * 0.25 +
        score_recent * 0.30 +
        score_musique * 0.15 +
        score_adaptation * 0.30 +
        bonus
    )

    return {
        "total": round(rating, 1),
        "global": round(score_global, 1),
        "recent": round(score_recent, 1),
        "musique": round(score_musique, 1),
        "adaptation": round(score_adaptation, 1),
        "adaptation_details": adaptation_details,
        "bonus": round(bonus, 1),
    }


# =============================================================================
# BUILD ANALYSES
# =============================================================================

def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Associe participants et performances, calcule les analyses et le rating.
    """
    perf_by_num = {}
    for p in performances or []:
        num = p.get("numPmu")
        if num is not None:
            perf_by_num[num] = p.get("courses", [])

    analyses = []
    for horse in participants:
        num = horse.get("numPmu")
        hist = perf_by_num.get(num, [])
        analyzer = HorseAnalyzer(horse, hist)
        analysis = analyzer.compute_all()
        if course_context:
            analysis["rating"] = compute_rating(analysis, course_context)
        analyses.append(analysis)

    # Classement : rating décroissant
    if course_context:
        analyses.sort(key=lambda x: x.get("rating", {}).get("total", 0), reverse=True)
    else:
        analyses.sort(key=lambda x: x["attitude"].get("numPmu", 999))
    return analyses
