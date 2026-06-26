from typing import List, Dict, Any, Optional
import math
from collections import defaultdict
from datetime import datetime


def parse_musique(musique: Optional[str]) -> List[str]:
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


def score_musique(symbols: List[str]) -> float:
    """Score de la musique : 0-100. Plus haut = meilleure forme."""
    if not symbols:
        return 0.0
    last5 = symbols[-5:][::-1]
    weights = [3.0, 2.5, 2.0, 1.5, 1.0]
    total = 0
    max_total = 0
    for i, sym in enumerate(last5):
        w = weights[i] if i < len(weights) else 0.8
        if sym.isdigit():
            p = int(sym)
            if p == 1:
                pts = 20
            elif p == 2:
                pts = 16
            elif p == 3:
                pts = 12
            elif p == 4:
                pts = 8
            elif p == 5:
                pts = 4
            else:
                pts = 1
        elif sym == 'p':
            pts = 6
        else:
            pts = 0
        total += pts * w
        max_total += 20 * w
    if max_total == 0:
        return 0.0
    return (total / max_total) * 100


def round_distance(d) -> Optional[int]:
    if d is None:
        return None
    try:
        return int(round(int(d) / 50) * 50)
    except Exception:
        return None


# =============================================================================
# MÉTHODE DU CLASSEMENT PAR CONSENSUS (Borda Count Turfistique)
# =============================================================================

def compute_indicators_for_all(courses_list: List[List[Dict[str, Any]]],
                                  participants: List[Dict[str, Any]],
                                  course_context: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """
    Calcule pour chaque cheval (par numPmu) un dict d'indicateurs numériques.
    """
    indicators = {}
    for i, (horse, courses) in enumerate(zip(participants, courses_list)):
        num = horse.get("numPmu", i)
        att = {
            "corde": horse.get("placeCorde"),
            "jockey": horse.get("driver"),
            "poids": horse.get("handicapPoids"),
            "gains": (horse.get("gainsParticipant") or {}).get("gainsCarriere", 0),
            "musique": score_musique(parse_musique(horse.get("musique", ""))),
            "age": horse.get("age"),
        }

        dist_jour = round_distance(course_context.get("distance"))
        disc_jour = course_context.get("discipline")
        hippo_jour = (course_context.get("hippodrome") or {}).get("libelleCourt")
        corde_jour = att["corde"]
        jockey_jour = att["jockey"]

        # Distance (± 100m)
        if dist_jour is not None:
            courses_dist = [c for c in courses if c.get("distance") and abs(round_distance(c["distance"]) - dist_jour) <= 100]
        else:
            courses_dist = []
        if courses_dist:
            total = len(courses_dist)
            victories = sum(1 for c in courses_dist if c.get("place") == 1)
            places = sum(1 for c in courses_dist if c.get("place") in (1, 2, 3))
            score_dist = (victories * 3 + places * 1.5) / total * 100 / 4.5
            fiab_dist = min(100, total * 20)
        else:
            score_dist = -10
            fiab_dist = 0

        # Discipline
        if disc_jour:
            courses_disc = [c for c in courses if c.get("discipline") == disc_jour]
        else:
            courses_disc = []
        if courses_disc:
            total = len(courses_disc)
            victories = sum(1 for c in courses_disc if c.get("place") == 1)
            places = sum(1 for c in courses_disc if c.get("place") in (1, 2, 3))
            score_disc = (victories * 2 + places * 1) / total * 100 / 3
            fiab_disc = min(100, total * 20)
        else:
            score_disc = -5
            fiab_disc = 0

        # Corde
        if corde_jour is not None:
            courses_corde = [c for c in courses if c.get("corde") == corde_jour]
        else:
            courses_corde = []
        if courses_corde:
            total = len(courses_corde)
            victories = sum(1 for c in courses_corde if c.get("place") == 1)
            places = sum(1 for c in courses_corde if c.get("place") in (1, 2, 3))
            score_corde = (victories * 2 + places * 1) / total * 100 / 3
            fiab_corde = min(100, total * 20)
        else:
            score_corde = -5
            fiab_corde = 0

        # Jockey
        if jockey_jour:
            courses_jock = [c for c in courses if c.get("nomJockey") == jockey_jour]
        else:
            courses_jock = []
        if courses_jock:
            total = len(courses_jock)
            victories = sum(1 for c in courses_jock if c.get("place") == 1)
            places = sum(1 for c in courses_jock if c.get("place") in (1, 2, 3))
            score_jock = (victories * 2 + places * 1) / total * 100 / 3
            fiab_jock = min(100, total * 20)
        else:
            score_jock = -5
            fiab_jock = 0

        # Hippodrome
        if hippo_jour:
            courses_hippo = [c for c in courses if c.get("hippodrome") == hippo_jour]
        else:
            courses_hippo = []
        if courses_hippo:
            total = len(courses_hippo)
            victories = sum(1 for c in courses_hippo if c.get("place") == 1)
            places = sum(1 for c in courses_hippo if c.get("place") in (1, 2, 3))
            score_hippo = (victories * 2 + places * 1) / total * 100 / 3
            fiab_hippo = min(100, total * 20)
        else:
            score_hippo = -5
            fiab_hippo = 0

        # Forme récente (3 dernières courses)
        recent = courses[:3]
        if recent:
            total = len(recent)
            victories = sum(1 for c in recent if c.get("place") == 1)
            places = sum(1 for c in recent if c.get("place") in (1, 2, 3))
            score_recent = (victories * 3 + places * 1.5) / total * 100 / 4.5
            # Bonus si dernière victoire
            if recent[0].get("place") == 1:
                score_recent += 10
            elif recent[0].get("place") in (2, 3):
                score_recent += 5
            fiab_recent = min(100, total * 33)
        else:
            score_recent = -15
            fiab_recent = 0

        # Gains (proxy de niveau, normalisé par max des participants)
        score_gains = att["gains"]

        # Poids (plus léger = mieux, mais handicap = poids imposé donc moins lourd = avantage)
        poids = att["poids"]
        if poids is not None:
            poids_kg = poids / 10.0
            score_poids = max(0, 100 - (poids_kg - 55) * 5)  # 55kg = 100, 60kg = 75, 65kg = 50
        else:
            score_poids = 50

        # Age
        age = att["age"]
        if age is not None:
            if age in (4, 5, 6):
                score_age = 70
            elif age in (3, 7):
                score_age = 50
            else:
                score_age = 30
        else:
            score_age = 50

        # Musique
        score_mus = att["musique"]

        # Malus contextuels
        malus = 0
        if horse.get("jockey_change") is True:
            malus -= 5
        if horse.get("jumentPleine") is True:
            malus -= 3
        if horse.get("indicateurInedit") is True:
            malus -= 8
        if recent and recent[0].get("place") in (None, 0):
            malus -= 3  # non classé dernièrement

        indicators[num] = {
            "attitude": att,
            "distance": {"score": score_dist, "fiabilite": fiab_dist, "total": len(courses_dist)},
            "discipline": {"score": score_disc, "fiabilite": fiab_disc, "total": len(courses_disc)},
            "corde": {"score": score_corde, "fiabilite": fiab_corde, "total": len(courses_corde)},
            "jockey": {"score": score_jock, "fiabilite": fiab_jock, "total": len(courses_jock)},
            "hippodrome": {"score": score_hippo, "fiabilite": fiab_hippo, "total": len(courses_hippo)},
            "forme_recente": {"score": score_recent, "fiabilite": fiab_recent, "total": len(recent)},
            "gains": {"score": score_gains, "fiabilite": 100},
            "poids": {"score": score_poids, "fiabilite": 100},
            "age": {"score": score_age, "fiabilite": 100},
            "musique": {"score": score_mus, "fiabilite": 100},
            "malus": malus,
            "history": courses[:10],
        }
    return indicators


def compute_consensus_ranking(indicators: Dict[int, Dict[str, Any]],
                             participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Pour chaque critère, classe les chevaux par score décroissant.
    Le classement consensus est la moyenne pondérée des classements.
    """
    nums = [p.get("numPmu") for p in participants]
    n = len(nums)
    if n == 0:
        return []

    # Critères avec leurs poids
    criteres = [
        ("distance", 0.25),
        ("forme_recente", 0.20),
        ("musique", 0.15),
        ("jockey", 0.15),
        ("discipline", 0.10),
        ("corde", 0.10),
        ("gains", 0.05),
    ]

    # Calculer le classement pour chaque critère
    rankings = {num: {} for num in nums}
    for crit_name, crit_weight in criteres:
        scores = [(num, indicators[num].get(crit_name, {}).get("score", -999)) for num in nums]
        # Trier par score décroissant
        scores.sort(key=lambda x: x[1], reverse=True)
        # Attribuer les classements (ex-aequo = même rang)
        rank = 1
        prev_score = None
        for i, (num, score) in enumerate(scores):
            if score != prev_score:
                rank = i + 1
            rankings[num][crit_name] = {
                "rank": rank,
                "score": round(score, 1),
                "weight": crit_weight,
            }
            prev_score = score

    # Score consensus pour chaque cheval
    consensus = {}
    for num in nums:
        total_weight = 0
        weighted_rank = 0
        for crit_name, crit_weight in criteres:
            r = rankings[num][crit_name]
            weighted_rank += r["rank"] * crit_weight
            total_weight += crit_weight
        consensus[num] = round(weighted_rank / total_weight, 2) if total_weight > 0 else 999

    # Ajouter les malus
    for num in nums:
        malus = indicators[num].get("malus", 0)
        if malus < 0:
            consensus[num] += abs(malus) * 0.3  # malus pénalise le classement

    # Trier par consensus croissant (1er = meilleur)
    sorted_nums = sorted(nums, key=lambda x: consensus[x])

    # Construire le résultat
    results = []
    for rank, num in enumerate(sorted_nums, 1):
        ind = indicators[num]
        att = {
            "nom": next((p.get("nom") for p in participants if p.get("numPmu") == num), "?"),
            "numPmu": num,
            "age": next((p.get("age") for p in participants if p.get("numPmu") == num), None),
            "sexe": next((p.get("sexe") for p in participants if p.get("numPmu") == num), None),
            "race": next((p.get("race") for p in participants if p.get("numPmu") == num), None),
            "statut": next((p.get("statut") for p in participants if p.get("numPmu") == num), None),
            "corde": next((p.get("placeCorde") for p in participants if p.get("numPmu") == num), None),
            "poids": next((p.get("handicapPoids") for p in participants if p.get("numPmu") == num), None),
            "jockey": next((p.get("driver") for p in participants if p.get("numPmu") == num), None),
            "jockey_change": next((p.get("driverChange") for p in participants if p.get("numPmu") == num), None),
            "entraineur": next((p.get("entraineur") for p in participants if p.get("numPmu") == num), None),
            "oeilleres": next((p.get("oeilleres") for p in participants if p.get("numPmu") == num), None),
            "robe": (next((p.get("robe") for p in participants if p.get("numPmu") == num), {}) or {}).get("libelleLong"),
            "musique": next((p.get("musique") for p in participants if p.get("numPmu") == num), None),
            "gainsCarriere": (next((p.get("gainsParticipant") for p in participants if p.get("numPmu") == num), {}) or {}).get("gainsCarriere"),
            "gainsAnneeEnCours": (next((p.get("gainsParticipant") for p in participants if p.get("numPmu") == num), {}) or {}).get("gainsAnneeEnCours"),
            "jumentPleine": next((p.get("jumentPleine") for p in participants if p.get("numPmu") == num), None),
            "indicateurInedit": next((p.get("indicateurInedit") for p in participants if p.get("numPmu") == num), None),
        }

        # Détail des classements par critère
        crit_details = []
        for crit_name, crit_weight in criteres:
            r = rankings[num][crit_name]
            crit_details.append({
                "nom": crit_name,
                "classement": r["rank"],
                "score": r["score"],
                "poids": crit_weight,
                "total": ind.get(crit_name, {}).get("total", 0),
            })

        # Confiance
        total_courses = ind.get("distance", {}).get("total", 0) + ind.get("discipline", {}).get("total", 0)
        fiab = min(100, total_courses * 8 + 20)

        results.append({
            "attitude": att,
            "rank": rank,
            "consensus": consensus[num],
            "malus": ind.get("malus", 0),
            "criteres": crit_details,
            "indicators": ind,
            "indice_confiance": fiab,
            "history": ind.get("history", []),
        })

    return results


# =============================================================================
# BUILD ANALYSES
# =============================================================================
def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    # Indexer les courses par numPmu
    perf_by_num = {}
    for p in performances or []:
        num = p.get("numPmu")
        if num is not None:
            perf_by_num[num] = p.get("courses", [])

    courses_list = []
    for p in participants:
        num = p.get("numPmu")
        courses_list.append(perf_by_num.get(num, []))

    indicators = compute_indicators_for_all(courses_list, participants, course_context or {})
    results = compute_consensus_ranking(indicators, participants)
    return results
