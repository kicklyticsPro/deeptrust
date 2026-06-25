from collections import defaultdict
from typing import List, Dict, Any, Optional
from datetime import datetime


def _safe(val):
    return val if val is not None else "N/A"


def _extract_historique_courses(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in courses:
        out.append({
            "date": c.get("date"),
            "hippodrome": c.get("hippodrome"),
            "discipline": c.get("discipline"),
            "distance": c.get("distance"),
            "corde": c.get("corde"),
            "place": c.get("place"),
            "nbParticipants": c.get("nbParticipants"),
            "poidsJockey": c.get("poidsJockey"),
            "nomJockey": c.get("nomJockey"),
            "etatTerrain": c.get("etatTerrain"),
            "statusArrivee": c.get("statusArrivee"),
            "nomPrix": c.get("nomPrix"),
        })
    return out


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _parse_musique(musique: Optional[str]) -> List[int]:
    """Parse les 5 derniers résultats de la musique."""
    if not musique:
        return []
    cleaned = []
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
        cleaned.append(ch)
    results = []
    for ch in cleaned[-5:]:
        if ch.isdigit():
            results.append(int(ch))
        elif ch == 'p':
            results.append(4)
        elif ch in ('a', 't', 'd', 'r'):
            results.append(99)
        else:
            results.append(50)
    return results


def _score_musique(musique: Optional[str], max_pts: float = 15.0) -> float:
    results = _parse_musique(musique)
    if not results:
        return 0.0
    pts = 0
    for r in results:
        if r == 1:
            pts += 5
        elif r == 2:
            pts += 4
        elif r == 3:
            pts += 3
        elif r == 4:
            pts += 1
        elif r == 5:
            pts += 0.5
        elif r >= 90:
            pts -= 2
    max_possible = len(results) * 5
    return max(0.0, (pts / max_possible) * max_pts) if max_possible > 0 else 0.0


def _score_global(glob: Dict[str, Any]) -> float:
    score = 0.0
    total = glob.get('totalCourses', 0)
    if total == 0:
        return 0.0
    score += (glob.get('pctVictoire', 0) / 100) * 10
    score += (glob.get('pctPlace', 0) / 100) * 10
    pm = glob.get('placeMoyenne')
    if pm is not None:
        if pm <= 2.0:
            score += 2
        elif pm <= 3.0:
            score += 1
        elif pm >= 6.0:
            score -= 2
        elif pm >= 5.0:
            score -= 1
    return max(0.0, min(20.0, score))


def _score_recente(glob: Dict[str, Any]) -> float:
    v = glob.get('victoiresLast5', 0)
    p = glob.get('placesLast5', 0)
    score = v * 4 + (p - v) * 2
    return max(0.0, min(20.0, score))


def _score_criterion(stats_dict: Dict[str, Any], current_value, max_pts: float = 8.0) -> float:
    if current_value is None or not stats_dict:
        return 0.0
    key = str(current_value)
    if key not in stats_dict:
        return 0.0
    s = stats_dict[key]
    total = s.get('total', 0)
    if total == 0:
        return 0.0
    score = 0.0
    pm = s.get('placeMoyenne')
    if pm is not None:
        if pm <= 2.0:
            score = max_pts
        elif pm <= 3.0:
            score = max_pts * 0.75
        elif pm <= 4.0:
            score = max_pts * 0.5
        elif pm <= 5.0:
            score = max_pts * 0.25
        else:
            score = max_pts * 0.1
    pv = s.get('pctVictoire', 0)
    if pv >= 30:
        score += 1
    if pv >= 50:
        score += 1
    pp = s.get('pctPlace', 0)
    if pp >= 50:
        score += 1
    return min(max_pts + 2, score)


def compute_score(analysis: Dict[str, Any], course_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcule un score composite 0-100+ pour chaque cheval.
    """
    glob = analysis.get('global', {})
    att = analysis.get('attitude', {})
    scores = {}

    # 1. Forme globale (20 pts max)
    scores['global'] = round(_score_global(glob), 1)

    # 2. Forme récente (20 pts max)
    scores['recente'] = round(_score_recente(glob), 1)

    # 3. Musique (15 pts max)
    scores['musique'] = round(_score_musique(att.get('musique', '')), 1)

    # 4. Adéquation course du jour (40 pts max)
    corde = att.get('corde')
    distance = course_context.get('distance')
    distance_rounded = None
    if distance is not None:
        try:
            distance_rounded = int(round(int(distance) / 50) * 50)
        except Exception:
            distance_rounded = str(distance)

    discipline = course_context.get('discipline')
    hippodrome = course_context.get('hippodrome', {}).get('libelleCourt')
    jockey = att.get('jockey')

    scores['corde'] = round(_score_criterion(analysis.get('byCorde', {}), corde, 8), 1)
    scores['distance'] = round(_score_criterion(analysis.get('byDistance', {}), distance_rounded, 8), 1)
    scores['discipline'] = round(_score_criterion(analysis.get('byDiscipline', {}), discipline, 8), 1)
    scores['hippodrome'] = round(_score_criterion(analysis.get('byHippodrome', {}), hippodrome, 8), 1)
    scores['jockey'] = round(_score_criterion(analysis.get('byJockey', {}), jockey, 8), 1)

    # 5. Présence entraîneur (2 pts)
    scores['entraineur'] = round(2.0 if att.get('entraineur') else 0.0, 1)

    total = sum(scores.values())
    scores['total'] = round(total, 1)
    return scores


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class HorseAnalyzer:
    def __init__(self, horse_info: Dict[str, Any], courses_history: List[Dict[str, Any]]):
        self.info = horse_info
        self.history = _extract_historique_courses(courses_history)

    def attitude_today(self) -> Dict[str, Any]:
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
            "robe": self.info.get("robe", {}).get("libelleLong"),
            "musique": self.info.get("musique"),
            "nombreCourses": self.info.get("nombreCourses"),
            "nombreVictoires": self.info.get("nombreVictoires"),
            "nombrePlaces": self.info.get("nombrePlaces"),
            "nombrePlacesSecond": self.info.get("nombrePlacesSecond"),
            "nombrePlacesTroisieme": self.info.get("nombrePlacesTroisieme"),
            "gainsCarriere": self.info.get("gainsParticipant", {}).get("gainsCarriere"),
            "gainsAnneeEnCours": self.info.get("gainsParticipant", {}).get("gainsAnneeEnCours"),
            "indicateurInedit": self.info.get("indicateurInedit"),
            "allure": self.info.get("allure"),
            "jumentPleine": self.info.get("jumentPleine"),
            "engagement": self.info.get("engagement"),
            "supplement": self.info.get("supplement"),
            "eleveur": self.info.get("eleveur"),
            "paysEntrainement": self.info.get("paysEntrainement"),
        }

    def global_stats(self) -> Dict[str, Any]:
        total = len(self.history)
        if total == 0:
            return {"totalCourses": 0}
        victoires = sum(1 for c in self.history if c["place"] == 1)
        places = sum(1 for c in self.history if c["place"] in (1, 2, 3))
        places2 = sum(1 for c in self.history if c["place"] == 2)
        places3 = sum(1 for c in self.history if c["place"] == 3)
        places_valides = [c["place"] for c in self.history if c["place"] is not None]
        place_moyenne = round(sum(places_valides) / len(places_valides), 2) if places_valides else None
        last5 = self.history[:5]
        victoires_last5 = sum(1 for c in last5 if c["place"] == 1)
        places_last5 = sum(1 for c in last5 if c["place"] in (1, 2, 3))
        return {
            "totalCourses": total,
            "victoires": victoires,
            "places123": places,
            "places2": places2,
            "places3": places3,
            "pctVictoire": round(victoires / total * 100, 1) if total else 0,
            "pctPlace": round(places / total * 100, 1) if total else 0,
            "placeMoyenne": place_moyenne,
            "victoiresLast5": victoires_last5,
            "placesLast5": places_last5,
        }

    def _bucket_stats(self, key_func) -> Dict[str, Any]:
        buckets = defaultdict(list)
        for c in self.history:
            k = key_func(c)
            if k is None:
                k = "N/A"
            buckets[k].append(c)
        result = {}
        for k, courses in buckets.items():
            total = len(courses)
            victoires = sum(1 for c in courses if c["place"] == 1)
            places = sum(1 for c in courses if c["place"] in (1, 2, 3))
            places_valides = [c["place"] for c in courses if c["place"] is not None]
            place_moy = round(sum(places_valides) / len(places_valides), 2) if places_valides else None
            result[str(k)] = {
                "total": total,
                "victoires": victoires,
                "places123": places,
                "pctVictoire": round(victoires / total * 100, 1) if total else 0,
                "pctPlace": round(places / total * 100, 1) if total else 0,
                "placeMoyenne": place_moy,
            }
        return result

    def stats_by_corde(self) -> Dict[str, Any]:
        return self._bucket_stats(lambda c: c["corde"])

    def stats_by_distance(self) -> Dict[str, Any]:
        def _dist(c):
            d = c.get("distance")
            if d is None:
                return None
            try:
                return int(round(int(d) / 50) * 50)
            except Exception:
                return str(d)
        return self._bucket_stats(_dist)

    def stats_by_discipline(self) -> Dict[str, Any]:
        return self._bucket_stats(lambda c: c["discipline"])

    def stats_by_jockey(self) -> Dict[str, Any]:
        return self._bucket_stats(lambda c: c["nomJockey"])

    def stats_by_hippodrome(self) -> Dict[str, Any]:
        return self._bucket_stats(lambda c: c["hippodrome"])

    def stats_by_terrain(self) -> Dict[str, Any]:
        return self._bucket_stats(lambda c: c["etatTerrain"])

    def full_analysis(self) -> Dict[str, Any]:
        return {
            "attitude": self.attitude_today(),
            "global": self.global_stats(),
            "byCorde": self.stats_by_corde(),
            "byDistance": self.stats_by_distance(),
            "byDiscipline": self.stats_by_discipline(),
            "byJockey": self.stats_by_jockey(),
            "byHippodrome": self.stats_by_hippodrome(),
            "byTerrain": self.stats_by_terrain(),
            "history": self.history[:10],
        }


def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    perf_by_num = {p["numPmu"]: p.get("courses", []) for p in performances}
    analyses = []
    for horse in participants:
        num = horse.get("numPmu")
        hist = perf_by_num.get(num, [])
        analyzer = HorseAnalyzer(horse, hist)
        analysis = analyzer.full_analysis()
        if course_context:
            analysis["scores"] = compute_score(analysis, course_context)
        analyses.append(analysis)

    if course_context:
        analyses.sort(key=lambda x: x.get("scores", {}).get("total", 0), reverse=True)
    else:
        analyses.sort(key=lambda x: x["attitude"].get("numPmu", 999))
    return analyses
