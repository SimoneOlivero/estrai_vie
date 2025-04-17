import gpxpy
import csv
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from geopy.distance import geodesic
import ssl
import re
import time
from tqdm import tqdm  
from datetime import datetime, timedelta

# ==== CONFIGURAZIONE ====
VEL_MEDIE_KMH = [32, 36, 40]
ORARIO_PARTENZA = "9:00"
GPX_FILENAME = "esoridenti_25_aprile.gpx"
CSV_OUTPUT = "campionamenti_vie.csv"
# =========================

ssl._create_default_https_context = ssl._create_unverified_context
geolocator = Nominatim(user_agent="estrai_vie_debug")
cache_geocode = {}

def ottieni_nome_via(lat, lon, retries=3):
    coord_key = (round(lat, 5), round(lon, 5))
    if coord_key in cache_geocode:
        return cache_geocode[coord_key]

    for tentativo in range(retries):
        try:
            location = geolocator.reverse((lat, lon), language="it", timeout=10)
            if location:
                address = location.raw.get("address", {})
                via_raw = address.get("road", "Sconosciuta")
                comune = (
                    address.get("city")
                    or address.get("town")
                    or address.get("village")
                    or address.get("hamlet")
                    or "Sconosciuto"
                )
                frazione = address.get("suburb") or address.get("hamlet") or ""

                classificazione = ""
                # 1. Prova a estrarre la classificazione da "ref"
                if "ref" in address:
                    refs = address["ref"].split(";")
                    for ref in refs:
                        match = re.match(r"\s*(SP|SS|SR|SPP|SPRR)[\.\s]*0*(\d+)", ref.strip(), re.IGNORECASE)
                        if match:
                            classificazione = f"{match.group(1).upper()}{int(match.group(2))}"
                            break

                # 2. Se non trovata, cerca nel nome della via
                if not classificazione and via_raw:
                    match = re.search(r"(SP|SS|SR|SPP|SPRR|S\.P\.|S\.S\.)[\s\.]*0*(\d+)", via_raw, re.IGNORECASE)
                    if match:
                        classificazione = f"{match.group(1).upper().replace('.', '').replace(' ', '')}{int(match.group(2))}"

                # 3. Pulisci il nome della via togliendo SP/SS iniziali
                via = via_raw or "Sconosciuta"
                via = re.sub(r"^(SP|SS|SR|SPP|SPRR|S\.P\.|S\.S\.)[\s\.]*0*\d+\s*[-\u2013:]?\s*", "", via, flags=re.IGNORECASE).strip()

                risultato = (via.strip(), classificazione.strip(), comune, frazione)
                cache_geocode[coord_key] = risultato
                return risultato
            else:
                return "Sconosciuta", "", "Sconosciuto", ""
        except GeocoderTimedOut:
            time.sleep(1)
        except Exception as e:
            print(f"Errore geocoding lat: {lat}, lon: {lon} -> {e}")
            return "Sconosciuta", "", "Sconosciuto", ""

    return "Sconosciuta", "", "Sconosciuto", ""

def campiona_per_distanza(gpx_file):
    gpx = gpxpy.parse(gpx_file)
    blocchi = []
    distanza_totale = 0.0
    ultimo_punto = None
    blocco_corrente = None

    punti_totali = sum(len(seg.points) for trk in gpx.tracks for seg in trk.segments)
    pbar = tqdm(total=punti_totali, desc="Campionamento in corso", unit="punto")

    for track in gpx.tracks:
        for segment in track.segments:
            for punto in segment.points:
                if ultimo_punto:
                    distanza = geodesic(
                        (ultimo_punto.latitude, ultimo_punto.longitude),
                        (punto.latitude, punto.longitude)
                    ).meters
                    distanza_totale += distanza

                via, classificazione, comune, frazione = ottieni_nome_via(punto.latitude, punto.longitude)

                if blocco_corrente and \
                   blocco_corrente["via"] == via and \
                   blocco_corrente["classificazione"] == classificazione and \
                   blocco_corrente["comune"] == comune and \
                   blocco_corrente["frazione"] == frazione:
                    blocco_corrente["fine"] = distanza_totale
                else:
                    if blocco_corrente:
                        lunghezza_blocco = blocco_corrente["fine"] - blocco_corrente["inizio"]
                        if lunghezza_blocco < 50 and len(blocchi) > 1:
                            blocchi.pop()

                    blocco_corrente = {
                        "via": via,
                        "classificazione": classificazione,
                        "comune": comune,
                        "frazione": frazione,
                        "inizio": distanza_totale,
                        "fine": distanza_totale
                    }
                    blocchi.append(blocco_corrente)

                ultimo_punto = punto
                pbar.update(1)

    pbar.close()
    return blocchi

def unisci_blocchi_consecutivi(blocchi):
    blocchi_uniti = []
    for i in range(len(blocchi)):
        if i == 0:
            blocchi_uniti.append(blocchi[i])
        else:
            prev = blocchi_uniti[-1]
            curr = blocchi[i]

            if (prev["via"] == curr["via"] and
                prev["classificazione"] == curr["classificazione"] and
                prev["comune"] == curr["comune"] and
                prev["frazione"] == curr["frazione"]):
                prev["fine"] = curr["fine"]
            else:
                curr["inizio"] = prev["fine"]
                blocchi_uniti.append(curr)

    return blocchi_uniti

def calcola_orario_stimato(distanza_km, velocita_kmh):
    minuti_dopo_partenza = int(round((distanza_km / velocita_kmh) * 60))
    orario_base = datetime.strptime(ORARIO_PARTENZA, "%H:%M")
    orario_arrivo = orario_base + timedelta(minutes=minuti_dopo_partenza)
    return orario_arrivo.strftime("%H:%M")

def è_valida(via, classificazione):
    return via != "Sconosciuta" or classificazione != ""

def main():
    try:
        with open(GPX_FILENAME, "r") as gpx_file:
            blocchi = campiona_per_distanza(gpx_file)
    except Exception as e:
        print(f"Errore nella lettura/parsing del file GPX: {e}")
        return

    if blocchi:
        blocchi_uniti = unisci_blocchi_consecutivi(blocchi)
        blocchi_filtrati = [b for b in blocchi_uniti if è_valida(b["via"], b["classificazione"])]

        with open(CSV_OUTPUT, mode="w", newline="", encoding="utf-8") as file_csv:
            writer = csv.writer(file_csv)
            intestazioni = [
                "Via", "Classificazione", "Comune", "Frazione",
                "Inizio (km)", "Fine (km)"
            ]
            intestazioni += [f"Passaggio @{v} km/h" for v in VEL_MEDIE_KMH]
            writer.writerow(intestazioni)

            for b in blocchi_filtrati:
                inizio_km = round(b["inizio"] / 1000, 2)
                fine_km = round(b["fine"] / 1000, 2)
                orari = [calcola_orario_stimato(inizio_km, v) for v in VEL_MEDIE_KMH]

                writer.writerow([
                    b["via"],
                    b["classificazione"],
                    b["comune"],
                    b["frazione"],
                    inizio_km,
                    fine_km,
                    *orari
                ])

        print(f"✅ Salvati {len(blocchi_filtrati)} blocchi in {CSV_OUTPUT}")
    else:
        print("❌ Nessun blocco trovato. Controlla se il file GPX ha una traccia valida.")

    print("✅ Esecuzione completata.")

if __name__ == "__main__":
    main()
 
 

 
