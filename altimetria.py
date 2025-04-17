import gpxpy
import gpxpy.gpx
import matplotlib.pyplot as plt
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from tqdm import tqdm
import numpy as np
import time
import matplotlib.patches as mpatches

# --- CONFIG ---
gpx_path = "Amatori 25 aprile.gpx"
nominatim_delay = 1
municipio_cache = {}

# --- LOAD GPX ---
with open(gpx_path, 'r') as gpx_file:
    gpx = gpxpy.parse(gpx_file)

points = []
for track in gpx.tracks:
    for segment in track.segments:
        for point in segment.points:
            points.append((point.latitude, point.longitude, point.elevation))

# --- DISTANCES ---
distances = [0.0]
for i in range(1, len(points)):
    d = geodesic((points[i - 1][0], points[i - 1][1]), (points[i][0], points[i][1])).meters
    distances.append(distances[-1] + d)

elevations = [p[2] for p in points]
x_vals = np.array(distances) / 1000
y_vals = np.array(elevations)
min_elev = min(elevations) - 50

# --- COMUNI NEI PRESSI DEL MUNICIPIO ---
geolocator = Nominatim(user_agent="altimetria-gpx")
comune_labels = {}
location_cache = {}
seen_comuni = set()  # Set per mantenere traccia dei comuni già visualizzati

print("\n📍 Geolocalizzazione comuni (via municipio)...")
for idx in tqdm(range(0, len(points), 20), desc="Comuni", ncols=80):
    lat, lon, _ = points[idx]
    key = (round(lat, 4), round(lon, 4))
    if key not in location_cache:
        try:
            location = geolocator.reverse((lat, lon), language='it', exactly_one=True, timeout=10)
            time.sleep(nominatim_delay)
            location_cache[key] = location
        except:
            continue
    else:
        location = location_cache[key]

    if location and 'address' in location.raw:
        addr = location.raw['address']
        comune = addr.get('town') or addr.get('city') or addr.get('village') or addr.get('municipality')
        if comune:
            # Aggiungi il comune solo se non è stato già visualizzato
            if comune not in seen_comuni:
                seen_comuni.add(comune)
                # Aggiungi il comune alla lista per la visualizzazione
                km = distances[idx] / 1000  # Calcola la distanza dal punto di partenza
                comune_labels[idx] = f"{comune} ({km:.1f} km)"

# --- GPM FILTRATI + LOCALITÀ ---
max_indices = sorted(range(len(elevations)), key=lambda i: elevations[i], reverse=True)
gpm_indices = []
gpm_positions = []
gpm_labels = []

# Rimuoviamo il filtro dei 7 km e visualizziamo i GPM con la logica dei punti di minimo
for i in max_indices:
    if i == 0 or i == len(elevations) - 1:  # Skip the first and last point
        continue
    prev_idx = i - 1
    next_idx = i + 1
    # Verifica se il punto corrente è massimo e se c'è un minimo tra due massimi
    if elevations[prev_idx] < elevations[i] and elevations[next_idx] < elevations[i]:
        gpm_indices.append(i)
        try:
            location = geolocator.reverse((points[i][0], points[i][1]), language='it', exactly_one=True, timeout=10)
            time.sleep(nominatim_delay)
            if location and 'address' in location.raw:
                addr = location.raw['address']
                localita = addr.get('hamlet') or addr.get('suburb') or addr.get('village') or addr.get('town') or addr.get('city')
                if localita:
                    gpm_labels.append(localita)
                else:
                    gpm_labels.append("GPM")
            else:
                gpm_labels.append("GPM")
        except:
            gpm_labels.append("GPM")
    if len(gpm_indices) >= 3:
        break

# --- GRAFICO ---
plt.figure(figsize=(14, 6))
plt.plot(x_vals, y_vals, color='red', lw=1.6)
plt.fill_between(x_vals, y_vals, min_elev, color='lightgreen', alpha=0.4)

plt.xlabel('Distanza (km)')
plt.ylabel('Altitudine (m)')
plt.title('Altimetria - Amatori 25 aprile')
plt.ylim(bottom=min_elev)
plt.grid(True, linestyle='--', alpha=0.4)

# Etichette Comuni (ora visualizzati una sola volta per ogni attraversamento)
for idx, label in comune_labels.items():
    x = distances[idx] / 1000
    y = elevations[idx] + 10
    plt.text(x, y, label, fontsize=8, rotation=90, va='bottom', ha='center')

# Partenza / Arrivo
plt.scatter(x_vals[0], y_vals[0], color='blue')
plt.text(x_vals[0], y_vals[0] + 20, 'Partenza', color='blue', fontsize=9, ha='right')
plt.scatter(x_vals[-1], y_vals[-1], color='blue')
plt.text(x_vals[-1], y_vals[-1] + 20, 'Arrivo', color='blue', fontsize=9, ha='left')

# GPM con etichetta località
for i, idx in enumerate(gpm_indices):
    x = distances[idx] / 1000
    y = elevations[idx]
    plt.scatter(x, y, marker='^', color='orange')
    plt.text(x, y + 10, gpm_labels[i], fontsize=9, color='darkorange', ha='center', rotation=90)

plt.legend(handles=[mpatches.Patch(color='orange', label='GPM')], loc='upper right')
plt.tight_layout()
plt.savefig("altimetria_amatori_25_aprile.png", dpi=300)
plt.show()






