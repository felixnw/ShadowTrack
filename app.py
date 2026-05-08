import os
import json
import math
import datetime
from zoneinfo import ZoneInfo
import requests
from flask import Flask, render_template, jsonify
from flask_cors import CORS

# --- IMPORT YOUR PRIVATE CONFIG ---
import config

# --- INITIALIZATION ---
# Forces Flask to find your folders regardless of where you launch the script
template_dir = os.path.abspath('templates')
static_dir = os.path.abspath('static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)

# Coordinates
HOME_LAT = config.HOME_LAT
HOME_LON = config.HOME_LON

# Minimum altitude (feet) for a plane to be considered
MIN_ALTITUDE = getattr(config, 'MIN_ALTITUDE', 200)

# Range in NM to consider when looking for planes from ADSB.lol
RANGE = getattr(config, 'RANGE', 50)

# --- API URLs ---
ADSB_URL = config.ADSB_URL.format(lat=HOME_LAT, lon=HOME_LON, range=RANGE)
SWIM_API_URL = config.SWIM_API_URL if hasattr(config, 'SWIM_API_URL') else None

# ---API Keys ---
SWIM_API_KEY = config.SWIM_API_KEY if hasattr(config, 'SWIM_API_KEY') else None

# --- AIRPORT LOOKUP ---
_airports_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'reference', 'airports.json')
with open(_airports_path, 'r') as _f:
    AIRPORTS = json.load(_f)

# Build reverse index: IATA code -> airport entry
AIRPORTS_BY_IATA = {v['iata']: v for v in AIRPORTS.values() if v.get('iata')}


def lookup_airport(code):
    """Resolve an airport code (3-char IATA or 4-char ICAO) to its entry."""
    if not code:
        return {}
    if len(code) == 4:
        return AIRPORTS.get(code, {})
    if len(code) == 3:
        return AIRPORTS_BY_IATA.get(code, {})
    return {}

# --- AIRCRAFT TYPE LOOKUP ---
_icao_list_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'reference', 'indexedDB', 'types.json')
with open(_icao_list_path, 'r') as _f:
    types_data = json.load(_f)

def lookup_aircraft_name(model_val):
    full_entry = types_data.get(model_val)
    if not full_entry:
        return "Unknown"

    full_string = full_entry[0]
    words = full_string.split(" ")
    formatted_words = []

    for word in words:
        # Check if the word is strictly alphabetical and all uppercase
        # We use .isupper() to catch "BOEING" but ignore "737-800" or "A-10"
        if word.isalpha() and word.isupper():
            formatted_words.append(word.capitalize())
        else:
            # Keep it as is (e.g., "Jetprop", "A-10", "737-800")
            formatted_words.append(word)

    return " ".join(formatted_words)

# --- AIRLINE LOOKUP ---
_airlines_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'reference', 'indexedDB', 'operators.json')
with open(_airlines_path, 'r') as _f:
    AIRLINES = json.load(_f)

# --- REGIONAL MAPPING ---
_regional_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'reference', 'regional.json')
with open(_regional_path, 'r') as _f:
    REGIONALS = json.load(_f)


def lookup_airline(icao_code):
    """Resolve an ICAO airline code to its company name"""
    if not icao_code:
        return None
        
    entry = AIRLINES.get(icao_code.upper()[0])
    if not entry:
        return None
    
    return entry

# --- GLOBAL CACHE ---
# Stores the 'Heavy' metadata from the last successful enrichment to avoid redundant API calls for the same plane on subsequent refreshes.
last_enriched_data = {
    "hex": None,
    "details": None
}

# --- HELPER FUNCTIONS ---


def get_altitude(ac):
    """Returns numeric altitude in feet, or 0 for 'ground' or missing values."""
    alt = ac.get('alt_baro', 0)
    if isinstance(alt, str):
        return 0
    return alt or 0

def calculate_distance(lat, lon):
    """
    Finds the great-circle distance to a plane using the Haversine formula.
    Returns distance in kilometers.
    """
    # Earth's radius in kilometers (use 3958.8 for miles)
    R = 6371.0

    # Convert decimal degrees to radians
    phi1 = math.radians(HOME_LAT)
    phi2 = math.radians(lat)
    
    delta_phi = math.radians(lat - HOME_LAT)
    delta_lambda = math.radians(lon - HOME_LON)

    # Haversine calculation
    a = (math.sin(delta_phi / 2)**2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2)**2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def filter_valid_planes(aircraft_list, min_altitude):
    """Filters aircraft to those with required fields, fresh signal, and minimum altitude."""
    valid = []
    for ac in aircraft_list:
        if all(k in ac for k in ('lat', 'lon', 'flight')) and ac.get('seen', 99) < 15:
            if get_altitude(ac) < min_altitude:
                continue
            ac['dist'] = calculate_distance(ac['lat'], ac['lon'])
            valid.append(ac)
    return valid


def format_time(ts):
    """Converts API Unix timestamps to HH:MM UTC."""
    if ts:
        try:
            return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%H:%M')
        except Exception:
            return "--:--"
    return "--:--"

# --- ROUTES ---


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/get-closest-plane')
def get_closest_plane():
    global last_enriched_data

    try:
        # 1. Pull closest planes from ADS-B
        response = requests.get(ADSB_URL, timeout=2)
        data = response.json()
        aircraft_list = data.get('ac') or data.get('aircraft') or []

        if not aircraft_list:
            return jsonify({"error": "No aircraft in range"}), 404

        # 2. Identify the closest plane with an active signal
        valid_planes = filter_valid_planes(aircraft_list, MIN_ALTITUDE)

        if not valid_planes:
            # print("No valid planes found (missing data or stale signal).")
            return jsonify({"error": "Scanning skies..."}), 404

        closest_ac = min(valid_planes, key=lambda x: x['dist'])
        current_hex = closest_ac.get('hex', 'N/A').strip().lower()
        callsign = closest_ac['flight'].strip()

# 3. SMART ENRICHMENT & CACHING
        details = {}

        if last_enriched_data["hex"] == current_hex and last_enriched_data["details"] is not None:
            details = last_enriched_data["details"]
            print(f"CACHE HIT: Reusing data for {callsign}")
        else:
            print(f"CACHE MISS: Searching bounds for {callsign}...")
            details = {}
            try:

                response = requests.get(f"{SWIM_API_URL}/swim-combined-flights/_search?size=10",
                                        headers={
                                            "Authorization": f"ApiKey {SWIM_API_KEY}", "Content-Type": "application/json"},
                                        json={
                    "sort": [
                        {
                            "last_update": {
                                "order": "desc"
                            }
                        }
                    ],
                    "query": {
                        "bool": {
                            "filter": [
                                {
                                    "term": {
                                        "flight_id": callsign
                                    }
                                },
                                {
                                    "terms": {
                                        "latest_status": ["ACTIVE", "PLANNED", "PROPOSED"]
                                    }
                                },
                                {
                                    "bool": {
                                        "must_not": {
                                            "range": {
                                                "latest_etd": {
                                                    "gte": "now+6h"
                                                }
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                })
                response.raise_for_status()
                if response.status_code == 200:
                    hits = response.json().get('hits', {}).get('hits', [])
                    if hits:
                        # Prefer ACTIVE; fall back to most-recently-updated PLANNED/PROPOSED
                        active_hits = [h for h in hits if h.get('_source', {}).get('latest_status') == 'ACTIVE']
                        best_hit = active_hits[0] if active_hits else hits[0]
                        details = best_hit.get('_source', {})
                        # Backfill missing fields from other hits on the same leg only
                        same_leg_hits = [
                            h for h in hits
                            if h is not best_hit
                            and h.get('_source', {}).get('dep_airport') == details.get('dep_airport')
                            and h.get('_source', {}).get('arr_airport') == details.get('arr_airport')
                        ]
                        for h in same_leg_hits:
                            for key, val in h.get('_source', {}).items():
                                if val is not None and not details.get(key):
                                    details[key] = val
                        print(f"CACHE SAVED: Found {callsign} via SWIM API (status: {details.get('latest_status')}).")
                else:
                    # We didn't find it on FR24 at all (likely Military/Blocked)
                    # We save an empty dict so the next refresh triggers a CACHE HIT
                    details = {}
                    print(
                        f"CACHE SAVED: {callsign} not found on FR24 (Military/Blocked).")

                # --- THE CRITICAL FIX ---
                # These lines MUST stay outside the 'if match' to ensure
                # that every hex gets cached exactly once.
                last_enriched_data["hex"] = current_hex
                last_enriched_data["details"] = details
            except Exception as e:
                print(f"Spatial Lookup Error: {e}")

      # 4. CONSTRUCT THE FINAL PAYLOAD
        is_valid = isinstance(details, dict) and bool(details)

        def get_local_time(timestamp_value, airport_code):
            if not timestamp_value:
                return "--:--"
            try:
                dt = datetime.datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                tz_name = lookup_airport(airport_code).get('tz')
                if tz_name:
                    dt = dt.astimezone(ZoneInfo(tz_name))
                return dt.strftime('%I:%M %p').lstrip('0')
            except Exception:
                return "--:--"

        def get_delay_status():
            if not is_valid:
                return "Scheduled"

            delay_mins = details.get('arrival_delay_minutes')
            if delay_mins is None:
                return "Scheduled"
            if delay_mins > 30:
                return "delayed-major"
            if delay_mins > 10:
                return "delayed-minor"
            return "ontime"

        major_code = details.get('major')
        if major_code and (major_code.upper() == (details.get('operator') or '').upper() or major_code.upper() == 'XXX'):
            major_code = None
        if major_code:
            operator_name = REGIONALS.get(major_code.upper()) or lookup_airline(major_code) or "Private/Military"
            operator_icao = major_code.upper()
            regional_name = lookup_airline(details.get('operator')) or details.get('operator') or None
        else:
            operator_name = lookup_airline(details.get('operator')) or "Private/Military"
            operator_icao = details.get('operator') or "DEFAULT"
            regional_name = None

        # Extract plane type values
        model_val = details.get('aircraft_model') or details.get('aircraft_type') or ''

        payload = {
            "flight": details.get('flight_id') or callsign,
            "tail": details.get('registration') or current_hex.upper(),
            "alt": closest_ac.get('alt_baro', 0),
            "speed": closest_ac.get('gs', 0),
            "operator": operator_name,
            "operator_icao": operator_icao,
            "regional": regional_name,
            "origin_icao": lookup_airport(details.get('dep_airport')).get('iata') or details.get('dep_airport') or "---",
            "origin_city": lookup_airport(details.get('dep_airport')).get('name') or "Unknown",
            "dest_icao": lookup_airport(details.get('arr_airport')).get('iata') or details.get('arr_airport') or "---",
            "dest_city": lookup_airport(details.get('arr_airport')).get('name') or "Unknown",
            "aircraft_model" : lookup_aircraft_name(model_val.upper()) or model_val or "Unknown Aircraft",
            "dep_time": get_local_time(details.get('latest_etd') or details.get('original_etd') or details.get('dep_time_estimated') or details.get('dep_time_actual'), details.get('dep_airport')),
            "arr_time": get_local_time(details.get('latest_eta') or details.get('original_eta') or details.get('arr_time_estimated'), details.get('arr_airport')),
            "delay_status": get_delay_status(),
            "status_text": details.get('latest_status') or "Scheduled"
        }

        return jsonify(payload)

    except Exception as e:
        print(f"CRITICAL BACKEND ERROR: {e}")
        return jsonify({"error": "Internal Error"}), 500


if __name__ == '__main__':
    # host='0.0.0.0' makes it accessible to your tablet via the Pi's IP
    app.run(host='0.0.0.0', port=5000, debug=True)
