from collections import defaultdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import math


def _safe(val):
    return val if val is not None else "N/A"


def _extract_historique_courses(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise et trie les courses historiques par date décroissante."""
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
    # Tri par date décroissante (timestamp plus grand = plus récent)
    out.sort(key=lambda x: x["date"] or 0, reverse=True)
    return out


# =============================================================================
# PARSING MUSIQUE PMU
# =============================================================================

def _parse_musique(musique: Optional[str]) -> List[str]:
    """
    Parse la musique PMU en liste de symboles.
    Ex: '1p3p(25)4p6p4p' -> ['1', 'p', '3', 'p', '4', 'p', '6', 'p', '4']
    (25) est la corde, on ignore le contenu des parenthèses.
    a=arrêté, t=tombé, d=dérouté, r=retiré
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


def _musique_last_n(symbols: List[str], n: int = 5) -> List[str]:
    """Récupère les n derniers symboles significatifs."""
    return symbols[-n:] if len(symbols) >= n else symbols


# =============================================================================
# SCORING
# =============================================================================

def _score_place_recent(place: Optional[int], nb_part: int = 0) -> float:
    """
    Score d'une place en course (0-10 base).
    1er=10, 2ème=8, 3ème=6, 4ème=4, 5ème=2, 6ème=1, 7ème+=0
    Si >10 partants et place > 7 mais <= nb_part//2 : 0.5
    """
    if place is None:
        return 0.0
    if place == 1:
        return 10.0
    if place == 2:
        return 8.0
    if place == 3:
        return 6.0
    if place == 4:
        return 4.0
    if place == 5:
        return 2.0
    if place == 6:
        return 1.0
    if nb_part > 10 and place <= nb_part // 2:
        return 0.5
    return 0.0


def _score_forme_recente(history: List[Dict[str, Any]]) -> float:
    """
    Forme récente sur les 5 dernières courses, pondérées dégressivement.
    Course -1: x2.0, -2: x1.5, -3: x1.2, -4: x1.0, -5: x0.8
    """
    if not history:
        return 0.0
    weights = [2.0, 1.5, 1.2, 1.0, 0.8]
    total = 0.0
    max_total = 0.0
    for i, c in enumerate(history[:5]):
        w = weights[i] if i < len(weights) else 0.5
        base = _score_place_recent(c.get("place"), c.get("nbParticipants") or 0)
        # Si incident (place=None mais status non-PLACE), base reste 0
        total += base * w
        max_total += 10.0 * w
    if max_total == 0:
        return 0.0
    # Normaliser sur 25 pts max
    return (total / max_total) * 25.0


def _score_musique(symbols: List[str]) -> float:
    """
    Score basé sur la musique (15 pts max).
    5 derniers symboles pondérés dégressivement.
    """
    last = _musique_last_n(symbols, 5)
    if not last:
        return 0.0
    weights = [2.0, 1.6, 1.3, 1.1, 1.0]  # du plus récent au plus ancien
    total = 0.0
    max_total = 0.0
    for i, sym in enumerate(last):
        w = weights[i] if i < len(weights) else 0.8
        if sym.isdigit():
            p = int(sym)
            if p == 1:
                pts = 10
            elif p == 2:
                pts = 7
            elif p == 3:
                pts = 5
            elif p == 4:
                pts = 3
            elif p == 5:
                pts = 1
            else:
                pts = 0
        elif sym == 'p':
            pts = 3  # placé sans rang précis
        else:
            pts = -3  # incident (a, t, d, r)
        total += pts * w
        max_total += 10 * w
    if max_total <= 0:
        return 0.0
    raw = (total / max_total) * 15.0
    return max(0.0, min(15.0, raw))


def _score_experience_regul(history: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Expérience + régularité (20 pts max).
    - Nombre de courses: 0-10 pts (courbe de saturation)
    - Régularité (écart-type des places): 0-10 pts
    """
    n = len(history)
    if n == 0:
        return {"experience": 0.0, "regularite": 0.0, "total": 0.0}

    # Expérience: 1 course=2pts, 3=5pts, 5=7pts, 8=9pts, 10+=10pts
    if n >= 15:
        exp = 10.0
    elif n >= 10:
        exp = 9.0
    elif n >= 8:
        exp = 8.0
    elif n >= 5:
        exp = 7.0
    elif n >= 3:
        exp = 5.0
    elif n >= 2:
        exp = 3.0
    else:
        exp = 2.0

    # Régularité: écart-type des places valides (1er = meilleur = faible écart)
    places = [c["place"] for c in history if c["place"] is not None]
    if len(places) >= 2:
        moy = sum(places) / len(places)
        variance = sum((p - moy) ** 2 for p in places) / len(places)
        ecart = math.sqrt(variance)
        # Écart-type < 1.5 = très régulier (10 pts), > 5 = irrégulier (0 pts)
        if ecart <= 1.5:
            reg = 10.0
        elif ecart >= 5.0:
            reg = 0.0
        else:
            reg = 10.0 - ((ecart - 1.5) / (5.0 - 1.5)) * 10.0
    else:
        reg = 2.0  # pas assez de données

    return {"experience": round(exp, 1), "regularite": round(reg, 1), "total": round(exp + reg, 1)}


def _score_criterion_adaptation(
    stats_dict: Dict[str, Any],
    current_value,
    min_races_for_significance: int = 2
) -> float:
    """
    Score d'adaptation à un critère (0-6 pts).
    - Si 0 course sur ce critère: 1 pt (neutre, pas de référence)
    - Si >= min_races et place moyenne <= 3.0: 6 pts
    - Si place moyenne <= 4.0: 4 pts
    - Si place moyenne <= 5.0: 2 pts
    - Sinon: 0-1 pt
    Bonus si % victoire > 20% ou % place > 50%
    """
    if current_value is None or not stats_dict:
        return 1.0
    key = str(current_value)
    if key not in stats_dict:
        return 1.0  # pas d'expérience = neutre
    s = stats_dict[key]
    total = s.get("total", 0)
    if total == 0:
        return 1.0

    pm = s.get("placeMoyenne")
    pv = s.get("pctVictoire", 0)
    pp = s.get("pctPlace", 0)

    score = 0.0
    if total >= min_races_for_significance:
        if pm is not None:
            if pm <= 2.0:
                score = 6.0
            elif pm <= 3.0:
                score = 5.0
            elif pm <= 4.0:
                score = 4.0
            elif pm <= 5.0:
                score = 2.5
            elif pm <= 6.0:
                score = 1.5
            else:
                score = 0.5
        else:
            score = 1.0
    else:
        # Trop peu de courses, on atténue
        if pm is not None:
            if pm <= 3.0:
                score = 3.0
            elif pm <= 5.0:
                score = 1.5
            else:
                score = 0.5
        else:
            score = 1.0

    # Bonus victoire/place
    if pv >= 30:
        score += 1.0
    if pp >= 60:
        score += 0.5

    return min(6.0, score)


def _score_bonus_malus(analysis: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, float]:
    """Bonus et malus divers (de -10 à +10)."""
    att = analysis.get("attitude", {})
    glob = analysis.get("global", {})
    bonus = 0.0
    details = {}

    # Inédit (jamais couru)
    total = glob.get("totalCourses", 0)
    if total == 0:
        bonus -= 5.0
        details["inedit"] = -5.0
    else:
        details["inedit"] = 0.0

    # Changement de jockey
    if att.get("jockey_change") is True:
        bonus -= 2.0
        details["jockey_change"] = -2.0
    else:
        details["jockey_change"] = 0.0

    # Gains année en cours (indicateur de forme/montée en puissance)
    gains = att.get("gainsAnneeEnCours", 0) or 0
    if gains > 500000:
        bonus += 2.0
        details["gains"] = 2.0
    elif gains > 200000:
        bonus += 1.0
        details["gains"] = 1.0
    else:
        details["gains"] = 0.0

    # Place moyenne globale excellente ou mauvaise
    pm = glob.get("placeMoyenne")
    if pm is not None:
        if pm <= 2.5:
            bonus += 3.0
            details["place_moyenne"] = 3.0
        elif pm <= 3.5:
            bonus += 1.5
            details["place_moyenne"] = 1.5
        elif pm >= 7.0:
            bonus -= 3.0
            details["place_moyenne"] = -3.0
        elif pm >= 6.0:
            bonus -= 1.5
            details["place_moyenne"] = -1.5
        else:
            details["place_moyenne"] = 0.0
    else:
        details["place_moyenne"] = 0.0

    # Dernière course = victoire (si historique disponible)
    if history and history[0].get("place") == 1:
        bonus += 2.0
        details["derniere_victoire"] = 2.0
    else:
        details["derniere_victoire"] = 0.0

    # Musique commence par '1' (victoire la plus récente)
    musique = att.get("musique", "")
    symbols = _parse_musique(musique)
    if symbols and symbols[-1] == '1':
        bonus += 1.5
        details["musique_recente_1"] = 1.5
    else:
        details["musique_recente_1"] = 0.0

    return {"bonus": round(bonus, 1), "details": details}


def compute_score(analysis: Dict[str, Any], course_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcule un score composite 0-100+ pour chaque cheval.
    """
    if not analysis:
        return {"total": 0}

    att = analysis.get("attitude", {})
    glob = analysis.get("global", {})
    history = analysis.get("history", [])
    scores = {}

    # 1. EXPÉRIENCE & RÉGULARITÉ (20 pts)
    exp_reg = _score_experience_regul(history)
    scores["experience"] = exp_reg["experience"]
    scores["regularite"] = exp_reg["regularite"]
    scores["experience_total"] = exp_reg["total"]

    # 2. FORME RÉCENTE (25 pts)
    scores["recente"] = round(_score_forme_recente(history), 1)

    # 3. MUSIQUE (15 pts)
    musique = att.get("musique", "")
    symbols = _parse_musique(musique)
    scores["musique"] = round(_score_musique(symbols), 1)

    # 4. ADÉQUATION COURSE DU JOUR (30 pts max)
    corde = att.get("corde")
    distance = course_context.get("distance") if course_context else None
    distance_rounded = None
    if distance is not None:
        try:
            distance_rounded = int(round(int(distance) / 50) * 50)
        except Exception:
            distance_rounded = str(distance)

    discipline = course_context.get("discipline") if course_context else None
    hippodrome = (course_context.get("hippodrome") or {}).get("libelleCourt") if course_context else None
    jockey = att.get("jockey")

    scores["corde"] = round(_score_criterion_adaptation(analysis.get("byCorde", {}), corde), 1)
    scores["distance"] = round(_score_criterion_adaptation(analysis.get("byDistance", {}), distance_rounded), 1)
    scores["discipline"] = round(_score_criterion_adaptation(analysis.get("byDiscipline", {}), discipline), 1)
    scores["hippodrome"] = round(_score_criterion_adaptation(analysis.get("byHippodrome", {}), hippodrome), 1)
    scores["jockey"] = round(_score_criterion_adaptation(analysis.get("byJockey", {}), jockey), 1)
    scores["adaptation"] = round(scores["corde"] + scores["distance"] + scores["discipline"] + scores["hippodrome"] + scores["jockey"], 1)

    # 5. BONUS/MALUS (10 pts max, peut être négatif)
    bm = _score_bonus_malus(analysis, history)
    scores["bonus_malus"] = bm["bonus"]
    scores["bonus_details"] = bm["details"]

    total = (
        scores["experience_total"] +
        scores["recente"] +
        scores["musique"] +
        scores["adaptation"] +
        scores["bonus_malus"]
    )
    scores["total"] = round(total, 1)
    return scores


# =============================================================================
# Analyzer class
# =============================================================================

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
        analysis = analyzer.full_analysis()
        if course_context:
            analysis["scores"] = compute_score(analysis, course_context)
        analyses.append(analysis)

    if course_context:
        analyses.sort(key=lambda x: x.get("scores", {}).get("total", 0), reverse=True)
    else:
        analyses.sort(key=lambda x: x["attitude"].get("numPmu", 999))
    return analyses
