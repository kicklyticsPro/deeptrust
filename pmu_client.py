import requests
from typing import List, Dict, Any, Optional

BASE_OFFLINE = "https://offline.turfinfo.api.pmu.fr/rest/client/7"
BASE_ONLINE = "https://online.turfinfo.api.pmu.fr/rest/client/61"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


class PMUClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str) -> Dict[str, Any]:
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_programme(self, date: str) -> Dict[str, Any]:
        url = f"{BASE_OFFLINE}/programme/{date}"
        return self._get(url)

    def get_participants(self, date: str, reunion: str, course: str) -> Dict[str, Any]:
        url = f"{BASE_OFFLINE}/programme/{date}/{reunion}/C{course}/participants"
        return self._get(url)

    def get_performances_detaillees(self, date: str, reunion: str, course: str) -> Dict[str, Any]:
        url = f"{BASE_ONLINE}/programme/{date}/{reunion}/C{course}/performances-detaillees/pretty"
        return self._get(url)

    def parse_reunions(self, programme: Dict[str, Any]) -> List[Dict[str, Any]]:
        reunions = []
        for r in programme.get("programme", {}).get("reunions", []):
            courses = []
            for c in r.get("courses", []):
                courses.append({
                    "numOrdre": c.get("numOrdre"),
                    "numExterne": c.get("numExterne"),
                    "libelle": c.get("libelle"),
                    "libelleCourt": c.get("libelleCourt"),
                    "heureDepart": c.get("heureDepart"),
                    "distance": c.get("distance"),
                    "distanceUnit": c.get("distanceUnit"),
                    "corde": c.get("corde"),
                    "discipline": c.get("discipline"),
                    "specialite": c.get("specialite"),
                    "categorieParticularite": c.get("categorieParticularite"),
                    "conditionAge": c.get("conditionAge"),
                    "conditionSexe": c.get("conditionSexe"),
                    "nombreDeclaresPartants": c.get("nombreDeclaresPartants"),
                    "typePiste": c.get("typePiste"),
                    "statut": c.get("statut"),
                    "hippodrome": c.get("hippodrome") or {},
                })
            reunions.append({
                "numOfficiel": r.get("numOfficiel"),
                "numExterne": r.get("numExterne"),
                "hippodrome": r.get("hippodrome") or {},
                "nature": r.get("nature"),
                "pays": r.get("pays") or {},
                "courses": courses,
            })
        return reunions

    def parse_participants(self, participants_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        clean = []
        for p in participants_data.get("participants", []):
            clean.append({
                "idCheval": p.get("idCheval"),
                "nom": p.get("nom"),
                "numPmu": p.get("numPmu"),
                "age": p.get("age"),
                "sexe": p.get("sexe"),
                "race": p.get("race"),
                "statut": p.get("statut"),
                "placeCorde": p.get("placeCorde"),
                "oeilleres": p.get("oeilleres"),
                "proprietaire": p.get("proprietaire"),
                "entraineur": p.get("entraineur"),
                "driver": p.get("driver"),
                "driverChange": p.get("driverChange"),
                "robe": p.get("robe"),
                "musique": p.get("musique"),
                "nombreCourses": p.get("nombreCourses"),
                "nombreVictoires": p.get("nombreVictoires"),
                "nombrePlaces": p.get("nombrePlaces"),
                "nombrePlacesSecond": p.get("nombrePlacesSecond"),
                "nombrePlacesTroisieme": p.get("nombrePlacesTroisieme"),
                "gainsParticipant": p.get("gainsParticipant"),
                "handicapValeur": p.get("handicapValeur"),
                "nomPere": p.get("nomPere"),
                "nomMere": p.get("nomMere"),
                "nomPereMere": p.get("nomPereMere"),
                "jumentPleine": p.get("jumentPleine"),
                "engagement": p.get("engagement"),
                "supplement": p.get("supplement"),
                "handicapPoids": p.get("handicapPoids"),
                "eleveur": p.get("eleveur"),
                "paysEntrainement": p.get("paysEntrainement"),
                "allure": p.get("allure"),
                "indicateurInedit": p.get("indicateurInedit"),
            })
        return clean

    def parse_performances(self, perf_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extrait pour chaque cheval son historique de courses avec données temps complètes.
        """
        if not perf_data or not isinstance(perf_data, dict):
            return []

        horses = []
        for p in perf_data.get("participants", []):
            cheval = {
                "numPmu": p.get("numPmu"),
                "nomCheval": p.get("nomCheval"),
                "courses": [],
            }
            for course in p.get("coursesCourues", []):
                # Extraire tous les participants de la course pour calculer les distances cumulées
                participants_raw = course.get("participants", [])

                # Construire un mapping par place
                participants_by_place = {}
                for part in participants_raw:
                    place_info = part.get("place")
                    if place_info:
                        place_num = place_info.get("place")
                        if place_num is not None:
                            participants_by_place[place_num] = {
                                "numPmu": part.get("numPmu"),
                                "nomCheval": part.get("nomCheval"),
                                "nomJockey": part.get("nomJockey"),
                                "poidsJockey": part.get("poidsJockey"),
                                "corde": part.get("corde"),
                                "oeillere": part.get("oeillere"),
                                "distanceAvecPrecedent": part.get("distanceAvecPrecedent"),
                                "itsHim": part.get("itsHim") is True,
                                "place": place_num,
                            }

                # Trouver le cheval actuel
                him = None
                for part in participants_by_place.values():
                    if part["itsHim"]:
                        him = part
                        break

                if him is None:
                    continue

                # Stocker la course avec toutes les données brutes nécessaires
                cheval["courses"].append({
                    "date": course.get("date"),
                    "hippodrome": course.get("hippodrome"),
                    "nomPrix": course.get("nomPrix"),
                    "discipline": course.get("discipline"),
                    "allocation": course.get("allocation"),
                    "distance": course.get("distance"),
                    "nbParticipants": course.get("nbParticipants"),
                    "tempsDuPremier": course.get("tempsDuPremier"),
                    "etatTerrain": course.get("etatTerrain"),
                    "place": him["place"],
                    "corde": him["corde"],
                    "poidsJockey": him["poidsJockey"],
                    "nomJockey": him["nomJockey"],
                    "oeillere": him["oeillere"],
                    "participantsByPlace": participants_by_place,
                })
            horses.append(cheval)
        return horses
