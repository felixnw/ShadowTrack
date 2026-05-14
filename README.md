## ShadowTrack: A Overhead Flight Tracking Dashboard
---

### This version offers the ability to use ADSB.lol instead of requiring a local Raspberry Pi with Dump1090, and does not use FR24.

### 📡 How it Works
1.  **Radio Reception:** API calls to your local dump1090 or uses ADSB.lol provide data on the closest aircraft to the local coordinates.
2.  **Closest-Plane Logic:** The ShadowTrack server (running on the display client) polls the API/dump1090 JSON output to identify the single closest aircraft based on your home coordinates.
3.  **Data Enrichment:** Using a custom API relying on FAA SWIM data, the system fetches "enriched" metadata—including airline names, origin/destination airports, and aircraft models—that isn't broadcast over the radio. It combines these with local data files to fill in all the fields.
4.  **Smart Caching:** To respect API limits and handle "Ghost" flights (Military or Private), the system implements a caching layer. Once a hex code is identified as blocked or private, it stops polling the API for that specific aircraft until it leaves the area.

---

### 💻 Hardware & Stack
* **API:** ADSB.lol or your dump1090 & FR24.
* **Backend:** Python / Flask / Gunicorn.
* **Frontend:** HTML5 / CSS3 / JavaScript.

#### Makes use of:
* https://github.com/Jxck-S/airline-logos
* https://www.mictronics.de/aircraft-database/export.php 
Contains information from [Mictronics Aircraft Database](https://www.mictronics.de/aircraft-database/) which is made available
under the [ODC Attribution License](https://opendatacommons.org/licenses/by/1-0/).
* https://github.com/mwgg/Airports which uses the following license:
The MIT License (MIT)

Copyright (c) 2014 mwgg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
