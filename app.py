from flask import Flask, render_template, jsonify, request
from pmu_client import PMUClient
from analyzer import build_analyses
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
client = PMUClient()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/reunions")
def api_reunions():
    date = request.args.get("date", datetime.now().strftime("%d%m%Y"))
    try:
        prog = client.get_programme(date)
        reunions = client.parse_reunions(prog)
        return jsonify({"success": True, "date": date, "reunions": reunions})
    except Exception as e:
        logger.error(f"Error in reunions: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analyse")
def api_analyse():
    date = request.args.get("date", datetime.now().strftime("%d%m%Y"))
    reunion = request.args.get("reunion", "R1")
    course = request.args.get("course", "1")
    try:
        prog = client.get_programme(date)
        reunions = client.parse_reunions(prog)
        course_info = None
        for r in reunions:
            if f"R{r['numOfficiel']}" == reunion.upper() or f"R{r['numExterne']}" == reunion.upper():
                for c in r["courses"]:
                    if str(c["numOrdre"]) == course:
                        course_info = c
                        break
            if course_info:
                break

        part_data = client.get_participants(date, reunion, course)
        participants = client.parse_participants(part_data)
        logger.info(f"Participants: {len(participants)}")

        perf_data = client.get_performances_detaillees(date, reunion, course)
        if not perf_data or (isinstance(perf_data, dict) and not perf_data.get("participants") and perf_data.get("code")):
            performances = []
        else:
            performances = client.parse_performances(perf_data)
        logger.info(f"Performances: {len(performances)}")

        analyses = build_analyses(participants, performances, course_info)
        return jsonify({
            "success": True,
            "date": date,
            "reunion": reunion,
            "course": course,
            "courseInfo": course_info,
            "analyses": analyses
        })
    except Exception as e:
        logger.error(f"Error in analyse: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
