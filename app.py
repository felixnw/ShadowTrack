import os
import math
import datetime
import requests
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from FlightRadar24 import FlightRadar24API

# --- IMPORT YOUR PRIVATE CONFIG ---
import config

# --- INITIALIZATION ---
# Forces Flask to find your folders regardless of where you launch the script
template_dir = os.path.abspath('templates')
static_dir = os.path.abspath('static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)
fr_api = FlightRadar24API()

# Coordinates
HOME_LAT = config.HOME_LAT
HOME_LON = config.HOME_LON

# Minimum altitude (feet) for a plane to be considered
MIN_ALTITUDE = getattr(config, 'MIN_ALTITUDE', 200)

# Range in NM to consider when looking for planes from ADSB.lol
RANGE = getattr(config, 'RANGE', 50)

# --- API URLs ---
ADSB_URL = config.ADSB_URL.format(lat=HOME_LAT, lon=HOME_LON, range=RANGE)

# --- GLOBAL CACHE ---
# Stores the 'Heavy' metadata so we don't spam FlightRadar24
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
    """Finds the straight-line distance to a plane."""
    return math.sqrt((lat - HOME_LAT)**2 + (lon - HOME_LON)**2)

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
                # 1. Create a tiny search box around the plane's current Lat/Lon
                # Format: "North, South, West, East"
                buffer = 0.1 
                p_lat, p_lon = closest_ac['lat'], closest_ac['lon']
                bounds = f"{p_lat+buffer},{p_lat-buffer},{p_lon-buffer},{p_lon+buffer}"
                
                # 2. Get all flights in that tiny specific area
                flights_in_area = fr_api.get_flights(bounds=bounds)
                
                # 3. Find our specific flight in that tiny list
                match = next((f for f in flights_in_area if f.icao_24bit.strip().lower() == current_hex), None)
                
                if match:
                    fetched_details = fr_api.get_flight_details(match)
                    # We found a match! Even if it's a private jet with no airline, 
                    # we save whatever details we got.
                    details = fetched_details if fetched_details else {}
                    print(f"CACHE SAVED: Found {callsign} via Spatial Match.")
                else:
                    # We didn't find it on FR24 at all (likely Military/Blocked)
                    # We save an empty dict so the next refresh triggers a CACHE HIT
                    details = {}
                    print(f"CACHE SAVED: {callsign} not found on FR24 (Military/Blocked).")

                # --- THE CRITICAL FIX ---
                # These lines MUST stay outside the 'if match' to ensure 
                # that every hex gets cached exactly once.
                last_enriched_data["hex"] = current_hex
                last_enriched_data["details"] = details
            except Exception as e:
                print(f"Spatial Lookup Error: {e}")

      # 4. CONSTRUCT THE FINAL PAYLOAD
        # Refined check: Ensure details is a dict AND not None
        is_valid = isinstance(details, dict) and details.get('airline') is not None
        
        # Safe helper for nested dictionary lookups (Prevents 'NoneType' errors)
        def safe_get(obj, *keys):
            for key in keys:
                try:
                    obj = obj.get(key)
                except (AttributeError, TypeError):
                    return None
            return obj

        time_data = details.get('time', {}) if is_valid else {}
        
        # --- HELPERS ---
        def get_local_time(utc_ts, airport_key):
            if not utc_ts or not is_valid: return "--:--"
            try:
                # Use safe_get to navigate the nested timezone offset
                offset = safe_get(details, 'airport', airport_key, 'timezone', 'offset') or 0
                local_dt = datetime.datetime.fromtimestamp(utc_ts + offset, datetime.timezone.utc)
                return local_dt.strftime('%I:%M %p').lstrip('0') # lstrip removes leading zero
            except Exception:
                return "--:--"

        def get_airport_code(airport_key):
            if not is_valid: return "---"
            # Try IATA then ICAO
            iata = safe_get(details, 'airport', airport_key, 'code', 'iata')
            icao = safe_get(details, 'airport', airport_key, 'code', 'icao')
            return iata or icao or "---"

        # --- DATA EXTRACTION ---
        dep_ts = safe_get(time_data, 'real', 'departure') or safe_get(time_data, 'scheduled', 'departure')
        arr_ts = safe_get(time_data, 'estimated', 'arrival') or safe_get(time_data, 'scheduled', 'arrival')

        # --- DELAY LOGIC ---
        def get_delay_status():
            if not is_valid: return "Scheduled"
            
            sched_arr = safe_get(time_data, 'scheduled', 'arrival')
            est_arr = safe_get(time_data, 'estimated', 'arrival')
            
            if not sched_arr or not est_arr: return "Scheduled"
            
            # Difference in minutes
            delay_mins = (est_arr - sched_arr) // 60
            
            if delay_mins > 30: return "delayed-major" # Red (30+ mins)
            if delay_mins > 10: return "delayed-minor"    # Yellow (10-30 mins)
            return "ontime"                               # Green

        payload = {
            "flight": callsign,
            "tail": safe_get(details, 'aircraft', 'registration') or current_hex.upper(),
            "alt": closest_ac.get('alt_baro', 0),
            "speed": closest_ac.get('gs', 0),
            "operator": safe_get(details, 'airline', 'name') or "Private/Military",
            "operator_icao": safe_get(details, 'airline', 'code', 'icao') or "DEFAULT",
            "origin_icao": get_airport_code('origin'),
            "origin_city": safe_get(details, 'airport', 'origin', 'name') or "Unknown",
            "dest_icao": get_airport_code('destination'),
            "dest_city": safe_get(details, 'airport', 'destination', 'name') or "Unknown",
            "aircraft_model": safe_get(details, 'aircraft', 'model', 'text') or "Unknown Aircraft",
            "dep_time": get_local_time(dep_ts, 'origin'),
            "arr_time": get_local_time(arr_ts, 'destination'),
            "delay_status": get_delay_status(),
            "status_text": safe_get(details, 'status', 'text') or "Scheduled"
        }

        return jsonify(payload)
    
    except Exception as e:
        print(f"CRITICAL BACKEND ERROR: {e}")
        return jsonify({"error": "Internal Error"}), 500

if __name__ == '__main__':
    # host='0.0.0.0' makes it accessible to your tablet via the Pi's IP
    app.run(host='0.0.0.0', port=5000, debug=True)