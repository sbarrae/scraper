"""
CONAF Chile - Scraper de Parques Nacionales
============================================
Ejecutar en tu máquina local:
  pip install requests beautifulsoup4 lxml
  python scraper.py

Estrategia multi-fuente:
  1. OpenStreetMap Nominatim  → coordenadas (lat/lon)
  2. conaf.cl por parque      → región, camping, servicios, descripción
  3. Output: output/parks.csv + output/parks.geojson
"""

import requests
import time
import json
import csv
import re
import os
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────
HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

HEADERS_OSM = {
    "User-Agent": "ConafCampingScraperChile/1.0 (proyecto personal, no comercial)",
    "Accept-Language": "es",
}

DELAY_CONAF = 2.0   # segundos entre requests a conaf.cl
DELAY_OSM   = 1.5   # Nominatim pide max 1 req/seg

# ── Lista de parques ───────────────────────────────────────────────────────────
# (nombre_display, slug_conaf)
PARQUES = [
    ("Alerce Andino",               "parque-nacional-alerce-andino"),
    ("Alerce Costero",              "parque-nacional-alerce-costero"),
    ("Alerce Milenario",            "parque-nacional-alerce-milenario"),
    ("Alto Bio Bio",                "parque-nacional-alto-bio-bio"),
    ("Archipiélago Juan Fernández", "parque-nacional-archipielago-juan-fernandez"),
    ("Bernardo O'Higgins",          "parque-nacional-bernardo-ohiggins"),
    ("Bosque Fray Jorge",           "parque-nacional-bosque-fray-jorge"),
    ("Cabo de Hornos",              "parque-nacional-cabo-de-hornos"),
    ("Cerro Castillo",              "parque-nacional-cerro-castillo"),
    ("Chiloé",                      "parque-nacional-chiloe"),
    ("Conguillio",                  "parque-nacional-conguillio"),
    ("Corcovado",                   "parque-nacional-corcovado"),
    ("Hornopirén",                  "parque-nacional-hornopiren"),
    ("Huasco",                      "parque-nacional-huasco"),
    ("Huerquehue",                  "parque-nacional-huerquehue"),
    ("Isla Magdalena",              "parque-nacional-isla-magdalena"),
    ("Kawésqar",                    "parque-nacional-kawesqar"),
    ("La Campana",                  "parque-nacional-la-campana"),
    ("Laguna del Laja",             "parque-nacional-laguna-del-laja"),
    ("Laguna San Rafael",           "parque-nacional-laguna-san-rafael"),
    ("Lauca",                       "parque-nacional-lauca"),
    ("Llanos de Challe",            "parque-nacional-llanos-de-challe"),
    ("Llullaillaco",                "parque-nacional-llullaillaco"),
    ("Nahuelbuta",                  "parque-nacional-nahuelbuta"),
    ("Nevado de Tres Cruces",       "parque-nacional-nevado-de-tres-cruces"),
    ("Nonguén",                     "parque-nacional-nonguen"),
    ("Patagonia",                   "parque-nacional-patagonia"),
    ("Pumalín Douglas Tompkins",    "parque-nacional-pumalin-douglas-tompkins"),
    ("Puyehue",                     "parque-nacional-puyehue"),
    ("Queulat",                     "parque-nacional-queulat"),
    ("Radal Siete Tazas",           "parque-nacional-radal-siete-tazas"),
    ("Rapa Nui",                    "parque-nacional-rapa-nui"),
    ("Salar de Huasco",             "parque-nacional-salar-de-huasco"),
    ("Tierra del Fuego",            "parque-nacional-tierra-del-fuego"),
    ("Torres del Paine",            "parque-nacional-torres-del-paine"),
    ("Vicente Pérez Rosales",       "parque-nacional-vicente-perez-rosales"),
    ("Villarrica",                  "parque-nacional-villarrica"),
    ("Volcán Isluga",               "parque-nacional-volcan-isluga"),
    ("Yerba Loca",                  "parque-nacional-yerba-loca"),
]

# ── 1. Coordenadas desde OpenStreetMap Nominatim ──────────────────────────────

def get_coords_osm(nombre: str) -> dict:
    """Geocodifica el parque con Nominatim (OSM). Gratis, sin API key."""
    url = "https://nominatim.openstreetmap.org/search"
    # Intentar query específica primero, luego más general
    queries = [
        f"Parque Nacional {nombre}, Chile",
        f"{nombre} national park Chile",
    ]
    for q in queries:
        try:
            r = requests.get(
                url,
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "cl"},
                headers=HEADERS_OSM,
                timeout=10,
            )
            results = r.json()
            if results:
                return {
                    "lat": float(results[0]["lat"]),
                    "lon": float(results[0]["lon"]),
                    "osm_id": results[0].get("osm_id", ""),
                }
            time.sleep(DELAY_OSM)
        except Exception as e:
            print(f"    OSM error '{nombre}': {e}")
    return {}


# ── 2. Scraping de página CONAF ───────────────────────────────────────────────

def scrape_conaf(slug: str) -> dict:
    """
    Extrae info de https://www.conaf.cl/parque_nacionales/{slug}/
    Retorna dict con región, superficie, camping, servicios, descripción.
    """
    url = f"https://www.conaf.cl/parque_nacionales/{slug}/"
    try:
        session = requests.Session()
        # Primer request a home para obtener cookies
        session.get("https://www.conaf.cl/", headers=HEADERS_BROWSER, timeout=15)
        time.sleep(0.5)
        r = session.get(url, headers=HEADERS_BROWSER, timeout=20)

        if r.status_code == 404:
            # Algunos parques usan /parques/ en lugar de /parque_nacionales/
            url_alt = f"https://www.conaf.cl/parques/{slug}/"
            r = session.get(url_alt, headers=HEADERS_BROWSER, timeout=20)

        if r.status_code != 200:
            return {"url_conaf": url, "conaf_status": r.status_code}

        soup = BeautifulSoup(r.text, "html.parser")
        texto_completo = soup.get_text(" ", strip=True)
        texto_lower = texto_completo.lower()
        data = {"url_conaf": url, "conaf_status": 200}

        # Región
        region_match = re.search(
            r"[Rr]egi[oó]n\s+de\s+([A-Za-záéíóúñÁÉÍÓÚÑ\s]+?)(?:[\.,]|\s{2,}|\n)",
            texto_completo
        )
        if region_match:
            data["region"] = region_match.group(1).strip()

        # Superficie en hectáreas
        sup_match = re.search(
            r"([\d\.]+)\s*(?:ha\b|hectáreas?)", texto_completo, re.IGNORECASE
        )
        if sup_match:
            data["superficie_ha"] = sup_match.group(1).replace(".", "")

        # ¿Tiene camping? Detección por keywords
        camping_keywords = [
            "camping", "campamento", "área de acampar",
            "zona de acampar", "sitio de camping",
        ]
        data["tiene_camping"] = any(kw in texto_lower for kw in camping_keywords)

        # Servicios disponibles
        mapa_servicios = {
            "baños"          : ["baño", "sanitario", "servicio higiénico"],
            "duchas"         : ["ducha"],
            "agua_potable"   : ["agua potable"],
            "estacionamiento": ["estacionamiento", "parking"],
            "senderos"       : ["sendero", "trekking", "senderismo"],
            "refugio"        : ["refugio"],
            "quincho"        : ["quincho"],
            "picnic"         : ["picnic", "área de picnic"],
            "fogon"          : ["fogón", "fogon"],
        }
        servicios_detectados = [
            srv for srv, kws in mapa_servicios.items()
            if any(kw in texto_lower for kw in kws)
        ]
        data["servicios"] = "|".join(servicios_detectados)

        # Descripción: primer párrafo sustancial
        for tag in soup.find_all(["p", "div"]):
            txt = tag.get_text(" ", strip=True)
            if (
                len(txt) > 120
                and "cookie" not in txt.lower()
                and "javascript" not in txt.lower()
                and txt[0].isupper()
            ):
                data["descripcion"] = txt[:500]
                break

        return data

    except requests.exceptions.RequestException as e:
        return {"url_conaf": url, "conaf_error": str(e)}


# ── 3. Pipeline principal ─────────────────────────────────────────────────────

def run():
    os.makedirs("output", exist_ok=True)
    resultados = []
    total = len(PARQUES)
    print(f"\n🌲 CONAF Scraper — {total} parques nacionales de Chile")
    print("=" * 55)

    for i, (nombre, slug) in enumerate(PARQUES, 1):
        print(f"\n[{i:02d}/{total}] {nombre}")

        parque = {
            "nombre"   : nombre,
            "tipo"     : "Parque Nacional",
            "slug_conaf": slug,
        }

        # Coordenadas OSM
        coords = get_coords_osm(nombre)
        parque.update(coords)
        estado_coords = f"lat={parque.get('lat','N/A')}" if coords else "sin coords"
        print(f"  📍 OSM: {estado_coords}")
        time.sleep(DELAY_OSM)

        # CONAF
        conaf_data = scrape_conaf(slug)
        parque.update(conaf_data)
        print(
            f"  🌐 CONAF HTTP {conaf_data.get('conaf_status','?')} | "
            f"camping={'✓' if parque.get('tiene_camping') else '✗'} | "
            f"región={parque.get('region','N/A')[:25]}"
        )
        time.sleep(DELAY_CONAF)

        resultados.append(parque)

        # Guardar progreso cada 5 parques (por si se corta)
        if i % 5 == 0:
            exportar_csv(resultados, "output/parks_parcial.csv")
            print(f"  💾 Progreso guardado ({i}/{total})")

    return resultados


# ── 4. Export ─────────────────────────────────────────────────────────────────

CAMPOS_CSV = [
    "nombre", "tipo", "region", "lat", "lon",
    "superficie_ha", "tiene_camping", "servicios",
    "descripcion", "url_conaf", "slug_conaf",
]

def exportar_csv(datos: list, path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(datos)

def exportar_geojson(datos: list, path: str):
    features = []
    for p in datos:
        lat, lon = p.get("lat"), p.get("lon")
        if not lat or not lon:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                k: v for k, v in p.items()
                if k not in ("lat", "lon") and v not in (None, "")
            },
        })
    gj = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, indent=2)


# ── 5. Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    datos = run()

    csv_path  = "output/parks.csv"
    json_path = "output/parks.geojson"

    exportar_csv(datos, csv_path)
    exportar_geojson(datos, json_path)

    con_camping = sum(1 for p in datos if p.get("tiene_camping"))
    con_coords  = sum(1 for p in datos if p.get("lat"))
    con_region  = sum(1 for p in datos if p.get("region"))

    print("\n" + "=" * 55)
    print("📊 RESUMEN FINAL")
    print(f"   Parques procesados  : {len(datos)}")
    print(f"   Con coordenadas     : {con_coords}")
    print(f"   Con región          : {con_region}")
    print(f"   Con camping         : {con_camping}")
    print(f"\n   📁 output/parks.csv")
    print(f"   📁 output/parks.geojson")
    print("\n⚠️  Revisión recomendada:")
    sin_coords = [p['nombre'] for p in datos if not p.get('lat')]
    if sin_coords:
        print(f"   Sin coords: {', '.join(sin_coords)}")
