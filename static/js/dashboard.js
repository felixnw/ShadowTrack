// Initialize NoSleep to keep the tablet screen on
const noSleep = new NoSleep();
let wakeLockEnabled = false;

// Configuration
const UPDATE_INTERVAL = 5000; // 5 seconds
const API_URL = '/get-closest-plane'; // Relative to the Flask server
const LOGO_PATH = '/static/flightaware_logos/';
const DEFAULT_LOGO = 'DEFAULT.png';

/**
 * Main update function
 */
async function updateDashboard() {
    const container = document.getElementById('app-container');
    
    try {
        const response = await fetch(API_URL);
        
        if (!response.ok) {
            throw new Error('No aircraft in range');
        }

        const data = await response.json();

        // 1. Remove loading state
        container.classList.remove('loading');
        
        // Set the label
        document.getElementById('status-label').innerText = "Closest Flight";

        // 2. Update Identity
        document.getElementById('flight-id').innerText = data.flight || 'N/A';
        document.getElementById('operator').innerText = data.operator || 'Unknown Operator';
        
        // 3. Update Logo (using Airline ICAO)
        const logoImg = document.getElementById('airline-logo');
        if (data.operator_icao && data.operator_icao !== "DEFAULT") {
            logoImg.src = `${LOGO_PATH}${data.operator_icao}.png`;
        } else {
            logoImg.src = `${LOGO_PATH}${DEFAULT_LOGO}`;
        }

        // 4. Update Route
        document.getElementById('origin-icao').innerText = data.origin_icao || '---';
        document.getElementById('origin-city').innerText = data.origin_city || 'Unknown';
        document.getElementById('dest-icao').innerText = data.dest_icao || '---';
        document.getElementById('dest-city').innerText = data.dest_city || 'Unknown';

    // 5. Update Times & Delay Status
        const arrTimeEl = document.getElementById('arr-time');
        const depTimeEl = document.getElementById('dep-time');

        // Update Departure (Standard)
        depTimeEl.innerHTML = `${data.dep_time || '--:--'} <small>Local</small>`;

        // Handle the Arrival Label and Badge
        // This assumes your HTML looks like: <div class="label">ARRIVAL</div><div id="arr-time">...</div>
        const arrivalLabel = arrTimeEl.previousElementSibling; 

        if (arrivalLabel && data.delay_status) {
            // We only want the first word (e.g., "Delayed" instead of "Delayed 14:30")
            const cleanStatus = data.delay_status || "Unknown";
            
            // Set the label text and append the badge
            arrivalLabel.innerHTML = `ARRIVAL <span class="status-badge ${data.delay_status}">${cleanStatus}</span>`;

            arrTimeEl.innerHTML = `${data.arr_time || '--:--'} <small>Local</small>`;
        } else {
            arrTimeEl.innerHTML = `${data.arr_time || '--:--'} <small>Local</small>`;
        }
        // 7. Update Specs
        document.getElementById('aircraft-type').innerHTML = `
            ${data.aircraft_model || 'Unknown Aircraft'}
            <span class="tail-sub">${data.tail ? data.tail.toUpperCase() : '-------'}</span>
        `;
        
        document.getElementById('alt-val').innerHTML = `
            ${(data.alt || 0).toLocaleString()} <small>FT</small>
        `;
        
        document.getElementById('speed-val').innerHTML = `
            ${data.speed || 0} <small>MPH</small>
        `;

    } catch (error) {
        console.warn("ShadowTrack Search:", error.message);
        // Re-enter loading state if no plane is found
        container.classList.add('loading');
        document.getElementById('status-label').innerText = "Scanning Skies...";
    }
}

/**
 * Handle Wake Lock (Screen Stay-On)
 * Browsers require a user gesture (tap) to enable NoSleep
 */
document.addEventListener('click', () => {
    if (!wakeLockEnabled) {
        noSleep.enable();
        wakeLockEnabled = true;
        console.log("ShadowTrack: Wake Lock Enabled");
        
        // Optional: brief visual feedback that wake lock is on
        const label = document.getElementById('status-label');
        const originalText = label.innerText;
        label.innerText = "WAKE LOCK ACTIVE";
        setTimeout(() => label.innerText = originalText, 2000);
    }
}, false);

// Start the loop
setInterval(updateDashboard, UPDATE_INTERVAL);

// Initial hit
updateDashboard();