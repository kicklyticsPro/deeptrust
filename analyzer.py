from typing import List, Dict, Any, Optional, Tuple
import math
from collections import defaultdict
from datetime import datetime


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_date(date_value: Any) -> Optional[datetime]:
    if not date_value:
        return None
    if isinstance(date_value, datetime):
        return date_value
    text = str(date_value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_name(value: Any) -> str:
    return " ".join(safe_str(value).upper().split())


def bounded_score_from_ratio(ratio: float, center: float = 0.5, slope: float = 5.0) -> float:
    """Transforme un ratio en score 0-100 avec discrimination renforcée."""
    ratio = clamp(ratio, 0.0, 1.0)
    x = 1.0 / (1.0 + math.exp(-slope * (ratio - center)))
    return clamp(x * 100.0, 0.0, 100.0)


def bayesian_rate(successes: float, total: float, prior_mean: float = 0.12, prior_strength: float = 12.0) -> float:
    if total <= 0:
        return prior_mean
    return (successes + prior_mean * prior_strength) / (total + prior_strength)


def weighted_place_score(place: Optional[int], field_size: Optional[int]) -> float:
    """0..1, favorise fortement les bonnes places en tenant compte du peloton."""
    if place is None or place <= 0:
        return 0.0
    if place == 1:
        return 1.0
    if place == 2:
        return 0.72
    if place == 3:
        return 0.56
    if field_size and field_size > 3:
        normalized = 1.0 - ((place - 1) / max(1, field_size - 1))
        return clamp(normalized * 0.45, 0.0, 0.45)
    return 0.15


def build_course_map(performances: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_course = defaultdict(list)
    for perf in performances or []:
        num = perf.get("numPmu")
        horse_name = perf.get("nomCheval")
        for c in perf.get("courses", []):
            key = "|".join([
                safe_str(c.get("date")),
                safe_str(c.get("hippodrome")),
                safe_str(c.get("nomPrix")),
                safe_str(c.get("distance")),
            ])
            by_course[key].append({
                "numPmu": num,
                "nomCheval": horse_name,
                "place": c.get("place"),
                "nbParticipants": c.get("nbParticipants"),
                "date": c.get("date"),
            })
    return by_course


def compute_duel_scores(participants: List[Dict[str, Any]], performances: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Qui domine les derniers affrontements directs entre chevaux engagés.
    On compare les chevaux lorsqu'ils ont couru dans la même course passée.
    Les duels récents pèsent plus lourd.
    """
    nums = {p.get("numPmu") for p in participants}
    duel_points = defaultdict(float)
    duel_events = defaultdict(float)
    duel_wins = defaultdict(float)
    duel_losses = defaultdict(float)
    by_course = build_course_map(performances)

    now = datetime.now()
    for runners in by_course.values():
        involved = [r for r in runners if r.get("numPmu") in nums and isinstance(r.get("place"), int) and r.get("place") > 0]
        if len(involved) < 2:
            continue
        course_date = parse_date(involved[0].get("date"))
        if course_date:
            age_days = max(0, (now - course_date.replace(tzinfo=None) if course_date.tzinfo else now - course_date).days)
        else:
            age_days = 365
        recency = math.exp(-age_days / 240.0)

        for i in range(len(involved)):
            for j in range(i + 1, len(involved)):
                a = involved[i]
                b = involved[j]
                if a["place"] == b["place"]:
                    duel_points[a["numPmu"]] += 0.5 * recency
                    duel_points[b["numPmu"]] += 0.5 * recency
                elif a["place"] < b["place"]:
                    duel_points[a["numPmu"]] += 1.0 * recency
                    duel_wins[a["numPmu"]] += 1.0 * recency
                    duel_losses[b["numPmu"]] += 1.0 * recency
                else:
                    duel_points[b["numPmu"]] += 1.0 * recency
                    duel_wins[b["numPmu"]] += 1.0 * recency
                    duel_losses[a["numPmu"]] += 1.0 * recency
                duel_events[a["numPmu"]] += recency
                duel_events[b["numPmu"]] += recency

    result = {}
    for p in participants:
        num = p.get("numPmu")
        events = duel_events[num]
        raw_rate = bayesian_rate(duel_points[num], events, prior_mean=0.50, prior_strength=4.0)
        score = bounded_score_from_ratio(raw_rate, center=0.5, slope=7.0)
        result[num] = {
            "score": score,
            "fiabilite": int(round(clamp(events * 22, 0, 100))),
            "total": int(round(events)),
            "meta": {
                "duel_wins": round(duel_wins[num], 2),
                "duel_losses": round(duel_losses[num], 2),
                "duel_rate": round(raw_rate, 3),
            },
        }
    return result


def compute_actor_success_scores(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Dict[str, Any],
) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """
    Approximation data-driven à partir de l'historique disponible dans la course.
    - jockey: résultats du jockey dans les historiques observés
    - entraîneur: proxy basé sur la réussite globale du cheval + volume du tandem trainer/cheval disponible

    Limitation: l'API actuelle ne fournit pas un historique global complet jockey/entraîneur externe à la course.
    """
    hippo_jour = safe_str((course_context.get("hippodrome") or {}).get("libelleCourt"))
    current_year = datetime.now().year

    jockey_global = defaultdict(lambda: {"pts": 0.0, "n": 0.0, "pts_hippo": 0.0, "n_hippo": 0.0, "pts_year": 0.0, "n_year": 0.0})
    horse_form = {}

    for perf in performances or []:
        num = perf.get("numPmu")
        courses = perf.get("courses", [])
        total_pts = 0.0
        total_n = 0.0
        for c in courses:
            jockey = normalize_name(c.get("nomJockey"))
            place = c.get("place")
            field = c.get("nbParticipants")
            pts = weighted_place_score(place, field)
            total_pts += pts
            total_n += 1.0
            if jockey:
                row = jockey_global[jockey]
                row["pts"] += pts
                row["n"] += 1.0
                if hippo_jour and normalize_name(c.get("hippodrome")) == hippo_jour:
                    row["pts_hippo"] += pts
                    row["n_hippo"] += 1.0
                cdate = parse_date(c.get("date"))
                if cdate and cdate.year == current_year:
                    row["pts_year"] += pts
                    row["n_year"] += 1.0
        horse_form[num] = bayesian_rate(total_pts, total_n, prior_mean=0.20, prior_strength=5.0)

    jockey_scores = {}
    trainer_scores = {}

    for p in participants:
        num = p.get("numPmu")
        jockey = normalize_name(p.get("driver"))
        trainer = normalize_name(p.get("entraineur"))

        j = jockey_global[jockey] if jockey else {"pts": 0, "n": 0, "pts_hippo": 0, "n_hippo": 0, "pts_year": 0, "n_year": 0}
        global_rate = bayesian_rate(j["pts"], j["n"], prior_mean=0.18, prior_strength=10.0)
        year_rate = bayesian_rate(j["pts_year"], j["n_year"], prior_mean=global_rate, prior_strength=8.0)
        hippo_rate = bayesian_rate(j["pts_hippo"], j["n_hippo"], prior_mean=global_rate, prior_strength=8.0)
        jockey_mix = 0.55 * year_rate + 0.30 * hippo_rate + 0.15 * global_rate
        jockey_scores[num] = {
            "score": bounded_score_from_ratio(jockey_mix, center=0.28, slope=6.0),
            "fiabilite": int(round(clamp((j["n_year"] + j["n_hippo"] + j["n"] * 0.2) * 8, 0, 100))),
            "total": int(j["n_year"] + j["n_hippo"]),
            "meta": {
                "global_rate": round(global_rate, 3),
                "year_rate": round(year_rate, 3),
                "hippo_rate": round(hippo_rate, 3),
            },
        }

        # Proxy entraîneur: moyenne des formes des chevaux de cet entraîneur présents dans les historiques connus.
        trainer_nums = [x.get("numPmu") for x in participants if normalize_name(x.get("entraineur")) == trainer and x.get("numPmu") in horse_form]
        trainer_sample = [horse_form[n] for n in trainer_nums if n in horse_form]
        if trainer_sample:
            trainer_rate = sum(trainer_sample) / len(trainer_sample)
            trainer_volume = len(trainer_sample)
        else:
            trainer_rate = 0.20
            trainer_volume = 0
        trainer_scores[num] = {
            "score": bounded_score_from_ratio(trainer_rate, center=0.25, slope=6.0),
            "fiabilite": int(round(clamp(trainer_volume * 25, 0, 100))),
            "total": trainer_volume,
            "meta": {
                "trainer_rate": round(trainer_rate, 3),
            },
        }

    return jockey_scores, trainer_scores


def compute_value_drop_scores(participants: List[Dict[str, Any]], performances: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Plus grosses chutes de valeurs / bonnes conditions du jour J.
    Avec les données disponibles, on utilise surtout le handicapValeur et le poids.
    On favorise les chevaux dont la valeur actuelle semble basse relativement au lot.
    """
    values = [p.get("handicapValeur") for p in participants if p.get("handicapValeur") is not None]
    weights = [p.get("handicapPoids") for p in participants if p.get("handicapPoids") is not None]

    min_val = min(values) if values else None
    max_val = max(values) if values else None
    min_w = min(weights) if weights else None
    max_w = max(weights) if weights else None

    results = {}
    for p in participants:
        num = p.get("numPmu")
        hv = p.get("handicapValeur")
        hp = p.get("handicapPoids")

        value_adv = 0.5
        if hv is not None and min_val is not None and max_val is not None and max_val > min_val:
            value_adv = 1.0 - ((hv - min_val) / (max_val - min_val))

        weight_adv = 0.5
        if hp is not None and min_w is not None and max_w is not None and max_w > min_w:
            weight_adv = 1.0 - ((hp - min_w) / (max_w - min_w))

        # Petit bonus si le cheval a déjà montré de la compétitivité malgré des charges supérieures.
        perf = next((x for x in performances if x.get("numPmu") == num), None)
        hist = perf.get("courses", []) if perf else []
        form_pts = sum(weighted_place_score(c.get("place"), c.get("nbParticipants")) for c in hist[:5])
        form_rate = bayesian_rate(form_pts, len(hist[:5]), prior_mean=0.18, prior_strength=3.0)

        composite = 0.45 * value_adv + 0.35 * weight_adv + 0.20 * form_rate
        results[num] = {
            "score": bounded_score_from_ratio(composite, center=0.52, slope=6.5),
            "fiabilite": 80 if hv is not None or hp is not None else 20,
            "total": len(hist[:5]),
            "meta": {
                "handicapValeur": hv,
                "handicapPoids": hp,
                "value_adv": round(value_adv, 3),
                "weight_adv": round(weight_adv, 3),
            },
        }
    return results


def compute_entity_success_scores(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    field_name: str,
    prior_mean: float,
    prior_strength: float,
    score_center: float,
) -> Dict[int, Dict[str, Any]]:
    """
    Réussite propriétaire / éleveur / origines à partir des chevaux présents et de leurs historiques.
    C'est une approximation interne au jeu de données chargé.
    """
    entity_stats = defaultdict(lambda: {"pts": 0.0, "n": 0.0})

    for p in participants:
        key = normalize_name(p.get(field_name))
        if not key:
            continue
        perf = next((x for x in performances if x.get("numPmu") == p.get("numPmu")), None)
        hist = perf.get("courses", []) if perf else []
        for c in hist[:10]:
            entity_stats[key]["pts"] += weighted_place_score(c.get("place"), c.get("nbParticipants"))
            entity_stats[key]["n"] += 1.0

    results = {}
    for p in participants:
        key = normalize_name(p.get(field_name))
        stats = entity_stats[key] if key else {"pts": 0.0, "n": 0.0}
        rate = bayesian_rate(stats["pts"], stats["n"], prior_mean=prior_mean, prior_strength=prior_strength)
        results[p.get("numPmu")] = {
            "score": bounded_score_from_ratio(rate, center=score_center, slope=5.8),
            "fiabilite": int(round(clamp(stats["n"] * 10, 0, 100))),
            "total": int(stats["n"]),
            "meta": {
                "entity": key,
                "rate": round(rate, 3),
            },
        }
    return results


def compute_origin_scores(participants: List[Dict[str, Any]], performances: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    origin_stats = defaultdict(lambda: {"pts": 0.0, "n": 0.0})
    horse_origin = {}

    for p in participants:
        sire = normalize_name(p.get("nomPere"))
        dam = normalize_name(p.get("nomMere"))
        damsire = normalize_name(p.get("nomPereMere"))
        key = " / ".join([x for x in [sire, dam, damsire] if x])
        horse_origin[p.get("numPmu")] = key
        if not key:
            continue
        perf = next((x for x in performances if x.get("numPmu") == p.get("numPmu")), None)
        hist = perf.get("courses", []) if perf else []
        for c in hist[:10]:
            origin_stats[key]["pts"] += weighted_place_score(c.get("place"), c.get("nbParticipants"))
            origin_stats[key]["n"] += 1.0

    results = {}
    for p in participants:
        num = p.get("numPmu")
        key = horse_origin.get(num, "")
        stats = origin_stats[key] if key else {"pts": 0.0, "n": 0.0}
        rate = bayesian_rate(stats["pts"], stats["n"], prior_mean=0.17, prior_strength=8.0)
        results[num] = {
            "score": bounded_score_from_ratio(rate, center=0.24, slope=5.8),
            "fiabilite": int(round(clamp(stats["n"] * 10, 0, 100))),
            "total": int(stats["n"]),
            "meta": {
                "origin": key,
                "rate": round(rate, 3),
            },
        }
    return results


def compute_recent_form_scores(performances: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    results = {}
    for perf in performances or []:
        num = perf.get("numPmu")
        hist = perf.get("courses", [])[:5]
        pts = 0.0
        total_weight = 0.0
        for idx, c in enumerate(hist):
            weight = max(0.4, 1.0 - idx * 0.15)
            pts += weighted_place_score(c.get("place"), c.get("nbParticipants")) * weight
            total_weight += weight
        rate = bayesian_rate(pts, total_weight, prior_mean=0.18, prior_strength=2.5)
        results[num] = {
            "score": bounded_score_from_ratio(rate, center=0.26, slope=6.2),
            "fiabilite": int(round(clamp(total_weight * 20, 0, 100))),
            "total": len(hist),
            "meta": {"rate": round(rate, 3)},
        }
    return results


def compute_indicators_for_all(
    courses_list: List[List[Dict[str, Any]]],
    participants: List[Dict[str, Any]],
    course_context: Dict[str, Any],
    performances: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    indicators = {}

    duel_scores = compute_duel_scores(participants, performances)
    jockey_scores, trainer_scores = compute_actor_success_scores(participants, performances, course_context)
    value_scores = compute_value_drop_scores(participants, performances)
    owner_scores = compute_entity_success_scores(participants, performances, "proprietaire", 0.16, 10.0, 0.22)
    breeder_scores = compute_entity_success_scores(participants, performances, "eleveur", 0.16, 10.0, 0.22)
    origin_scores = compute_origin_scores(participants, performances)
    recent_scores = compute_recent_form_scores(performances)

    for i, (horse, courses) in enumerate(zip(participants, courses_list)):
        num = horse.get("numPmu", i)
        indicators[num] = {
            "attitude": {
                "corde": horse.get("placeCorde"),
                "jockey": horse.get("driver"),
                "poids": horse.get("handicapPoids"),
                "gains": (horse.get("gainsParticipant") or {}).get("gainsCarriere", 0),
                "age": horse.get("age"),
            },
            "duels": duel_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "jockey": jockey_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "entraineur": trainer_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "valeur_jour": value_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "proprietaire": owner_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "origines": origin_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "eleveur": breeder_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "forme_recente": recent_scores.get(num, {"score": 50, "fiabilite": 0, "total": 0}),
            "malus": 0,
            "history": courses[:10],
        }
    return indicators


def compute_consensus_ranking(indicators: Dict[int, Dict[str, Any]], participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    nums = [p.get("numPmu") for p in participants]
    if not nums:
        return []

    criteres = [
        ("duels", 0.24),
        ("jockey", 0.17),
        ("entraineur", 0.16),
        ("valeur_jour", 0.16),
        ("forme_recente", 0.12),
        ("proprietaire", 0.06),
        ("origines", 0.05),
        ("eleveur", 0.04),
    ]

    rankings = {num: {} for num in nums}
    for crit_name, crit_weight in criteres:
        scores = [(num, indicators[num].get(crit_name, {}).get("score", -999)) for num in nums]
        scores.sort(key=lambda x: x[1], reverse=True)
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

    consensus = {}
    for num in nums:
        weighted_rank = 0.0
        total_weight = 0.0
        for crit_name, crit_weight in criteres:
            r = rankings[num][crit_name]
            fiab = indicators[num].get(crit_name, {}).get("fiabilite", 0) / 100.0
            adaptive_weight = crit_weight * (0.55 + 0.45 * fiab)
            weighted_rank += r["rank"] * adaptive_weight
            total_weight += adaptive_weight
        consensus[num] = round(weighted_rank / total_weight, 2) if total_weight > 0 else 999.0

    sorted_nums = sorted(nums, key=lambda x: consensus[x])
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
            "proprietaire": next((p.get("proprietaire") for p in participants if p.get("numPmu") == num), None),
            "nomPere": next((p.get("nomPere") for p in participants if p.get("numPmu") == num), None),
            "nomMere": next((p.get("nomMere") for p in participants if p.get("numPmu") == num), None),
            "nomPereMere": next((p.get("nomPereMere") for p in participants if p.get("numPmu") == num), None),
            "eleveur": next((p.get("eleveur") for p in participants if p.get("numPmu") == num), None),
            "handicapValeur": next((p.get("handicapValeur") for p in participants if p.get("numPmu") == num), None),
        }

        crit_details = []
        for crit_name, crit_weight in criteres:
            r = rankings[num][crit_name]
            crit_details.append({
                "nom": crit_name,
                "classement": r["rank"],
                "score": r["score"],
                "poids": crit_weight,
                "total": ind.get(crit_name, {}).get("total", 0),
                "fiabilite": ind.get(crit_name, {}).get("fiabilite", 0),
            })

        fiab_values = [ind.get(c, {}).get("fiabilite", 0) for c, _ in criteres]
        fiab = int(round(sum(fiab_values) / len(fiab_values))) if fiab_values else 0

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

    courses_list = []
    for p in participants:
        num = p.get("numPmu")
        courses_list.append(perf_by_num.get(num, []))

    indicators = compute_indicators_for_all(courses_list, participants, course_context or {}, performances or [])
    results = compute_consensus_ranking(indicators, participants)
    return results
