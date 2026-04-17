## ShadowTrack: A Overhead Flight Tracking Dashboard
---

### This version offers the ability to use ADSB.lol instead of requiring a local Raspberry Pi with Dump1090.

### 📡 How it Works
1.  **Radio Reception:** API calls to your local dump1090 or uses ADSB.lol provide data on the closest aircraft to the local coordinates.
2.  **Closest-Plane Logic:** The ShadowTrack server (running on the display client) polls the API/dump1090 JSON output to identify the single closest aircraft based on your home coordinates.
3.  **Data Enrichment:** Using the `FlightRadar24-API`, the system fetches "enriched" metadata—including airline names, logos, origin/destination airports, and aircraft models—that isn't broadcast over the radio.
4.  **Smart Caching:** To respect API limits and handle "Ghost" flights (Military or Private), the system implements a caching layer. Once a hex code is identified as blocked or private, it stops polling the API for that specific aircraft until it leaves the area.

---

### 💻 Hardware & Stack
* **API:** ADSB.lol or your dump1090 & FR24.
* **Backend:** Python / Flask / Gunicorn.
* **Frontend:** HTML5 / CSS3 / JavaScript.

#### Makes use of:
* https://github.com/Jxck-S/airline-logos
* https://github.com/JeanExtreme002/FlightRadarAPI
