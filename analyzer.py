from collections import defaultdict
from typing import List, Dict, Any, Optional


def _extract_historique(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise les courses historiques et les trie par date décroissante."""
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


def _pct_reussite(courses: List[Dict[str, Any]]) -> float:
    """
    % de réussite sur une liste de courses.
    Victoire = 100%, Place (2-3) = 50%, 4-5 = 25%, Classé = 10%, Non classé = 0%.
    On fait la moyenne des points sur toutes les courses.
    """
    if not courses:
        return 0.0
    total = 0.0
    for c in courses:
        p = c.get("place")
        if p == 1:
            total += 100.0
        elif p == 2:
            total += 50.0
        elif p == 3:
            total += 50.0
        elif p == 4:
            total += 25.0
        elif p == 5:
            total += 25.0
        elif p is not None and p > 5:
            total += 10.0
        else:
            total += 0.0
    return round(total / len(courses), 1)


def _round_distance(d) -> Optional[int]:
    if d is None:
        return None
    try:
        return int(round(int(d) / 50) * 50)
    except Exception:
        return None


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

    def stats_globales(self) -> Dict[str, Any]:
        n = len(self.history)
        if n == 0:
            return {"total": 0, "pct_reussite": 0.0}
        return {
            "total": n,
            "pct_reussite": _pct_reussite(self.history),
            "victoires": sum(1 for c in self.history if c["place"] == 1),
            "places123": sum(1 for c in self.history if c["place"] in (1, 2, 3)),
            "place_moy": round(sum(c["place"] for c in self.history if c["place"] is not None) /
                               len([c for c in self.history if c["place"] is not None]), 1) if any(c["place"] is not None for c in self.history) else None,
        }

    def compute_all(self, course_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Pour chaque critère applicable (corde, distance, discipline, jockey, hippodrome, terrain),
        calcule le % de réussite du cheval sur ce critère.
        Puis fait la MOYENNE de tous ces %.
        """
        att = self.attitude()
        glob = self.stats_globales()

        criteres = []

        if not course_context:
            return {
                "attitude": att,
                "global": glob,
                "criteres": [],
                "moyenne": 0.0,
                "history": self.history[:10],
            }

        # 1. Corde
        corde_jour = att.get("corde")
        if corde_jour is not None:
            courses_corde = [c for c in self.history if c["corde"] == corde_jour]
            if courses_corde:
                criteres.append({
                    "nom": "Corde",
                    "valeur": corde_jour,
                    "total": len(courses_corde),
                    "pct": _pct_reussite(courses_corde),
                })

        # 2. Distance (tranche de 50m)
        dist_jour = course_context.get("distance")
        dist_rounded = _round_distance(dist_jour)
        if dist_rounded is not None:
            courses_dist = [c for c in self.history if _round_distance(c["distance"]) == dist_rounded]
            if courses_dist:
                criteres.append({
                    "nom": "Distance",
                    "valeur": f"~{dist_rounded}m",
                    "total": len(courses_dist),
                    "pct": _pct_reussite(courses_dist),
                })

        # 3. Discipline
        disc_jour = course_context.get("discipline")
        if disc_jour:
            courses_disc = [c for c in self.history if c["discipline"] == disc_jour]
            if courses_disc:
                criteres.append({
                    "nom": "Discipline",
                    "valeur": disc_jour,
                    "total": len(courses_disc),
                    "pct": _pct_reussite(courses_disc),
                })

        # 4. Hippodrome
        hippo_jour = (course_context.get("hippodrome") or {}).get("libelleCourt")
        if hippo_jour:
            courses_hippo = [c for c in self.history if c["hippodrome"] == hippo_jour]
            if courses_hippo:
                criteres.append({
                    "nom": "Hippodrome",
                    "valeur": hippo_jour,
                    "total": len(courses_hippo),
                    "pct": _pct_reussite(courses_hippo),
                })

        # 5. Jockey
        jockey_jour = att.get("jockey")
        if jockey_jour:
            courses_jock = [c for c in self.history if c["nomJockey"] == jockey_jour]
            if courses_jock:
                criteres.append({
                    "nom": "Jockey",
                    "valeur": jockey_jour,
                    "total": len(courses_jock),
                    "pct": _pct_reussite(courses_jock),
                })

        # 6. Terrain
        # On n'a pas l'état terrain du jour dans course_context, donc on skip

        # 7. Forme récente (5 dernières courses)
        recent = self.history[:5]
        if recent:
            criteres.append({
                "nom": "Forme récente",
                "valeur": "5 dernières",
                "total": len(recent),
                "pct": _pct_reussite(recent),
            })

        # 8. Musique (5 derniers résultats)
        musique = self.info.get("musique", "")
        if musique:
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
            last5 = symbols[-5:]
            if last5:
                pts = 0.0
                for sym in last5:
                    if sym.isdigit():
                        p = int(sym)
                        if p == 1:
                            pts += 100
                        elif p == 2:
                            pts += 50
                        elif p == 3:
                            pts += 50
                        elif p == 4:
                            pts += 25
                        elif p == 5:
                            pts += 25
                        else:
                            pts += 10
                    elif sym == 'p':
                        pts += 25
                    else:
                        pts += 0
                criteres.append({
                    "nom": "Musique",
                    "valeur": "".join(last5),
                    "total": len(last5),
                    "pct": round(pts / len(last5), 1),
                })

        # MOYENNE de tous les %
        if criteres:
            moyenne = round(sum(c["pct"] for c in criteres) / len(criteres), 1)
        else:
            moyenne = 0.0

        # Si pas d'historique du tout, on met une moyenne très basse
        if glob["total"] == 0:
            moyenne = 0.0

        return {
            "attitude": att,
            "global": glob,
            "criteres": criteres,
            "moyenne": moyenne,
            "history": self.history[:10],
        }


def build_analyses(
    participants: List[Dict[str, Any]],
    performances: List[Dict[str, Any]],
    course_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Associe participants et performances, calcule les analyses et classe par moyenne décroissante.
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
        analysis = analyzer.compute_all(course_context)
        analyses.append(analysis)

    # Classement : moyenne décroissante
    analyses.sort(key=lambda x: x.get("moyenne", 0), reverse=True)
    return analyses
