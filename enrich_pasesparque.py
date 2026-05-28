"""
Enriquecedor de parks.csv con datos de pasesparques.cl
=======================================================
Lee output/parks.csv, cruza con pasesparques.cl y completa:
  - region         (si falta o está vacía)
  - descripcion    (reemplaza si la actual es muy corta)
  - horario        (nuevo campo)
  - slug_pases     (nuevo campo, útil para links directos)
  - tiene_pase_digital (nuevo campo, bool)

Uso:
  pip install requests beautifulsoup4 lxml
  python enrich_pasesparques.py
"""

import requests
import time
import csv
import re
import os
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
}

DELAY = 1.5
INPUT_CSV  = "output/parks.csv"
OUTPUT_CSV = "output/parks_enriched.csv"

# ── Mapa manual de nombre → slug en pasesparques.cl ───────────────────────────
# Construido desde la home de pasesparques.cl
# Parques con múltiples sectores usan el slug del parque principal
SLUG_MAP = {
    "Torres del Paine"            : "torres-del-paine",
    "Vicente Pérez Rosales"       : "v-perez-rosales",
    "Bosque Fray Jorge"           : "bosque-fray-jorge",
    "Radal Siete Tazas"           : "rada-siete-tazas",
    "La Campana"                  : "la-campana-sector-granizo",
    "Queulat"                     : "queulat",
    "Alerce Costero"              : "alerce-costero",
    "Villarrica"                  : "villarrica-norte",
    "Conguillio"                  : "conguillio",
    "Patagonia"                   : "patagonia-chacabuco",
    "Alerce Andino"               : "alerce-andino",
    "Laguna San Rafael"           : "laguna-san-rafael",
    "Laguna del Laja"             : "laguna-del-laja",
    "Pan de Azúcar"               : "pan-de-azucar",
    "Río Clarillo"                : "rio-clarillo",
    "Llanos de Challe"            : "llanos-de-challe",
    "Pali Aike"                   : "pali-aike",
    "Chiloé"                      : "chiloe",
    "Tolhuaca"                    : "tolhuaca",
    "Huerquehue"                  : "huerquehue",
    "Bernardo O'Higgins"          : "bernardo-o-higgins",
    "Nonguén"                     : "nonguen",
    "Nevado de Tres Cruces"       : "nevado-tres-cruces",
    "Archipiélago Juan Fernández" : "archipielago-juan-fernandez",
}


# ── Similitud de strings (para match fuzzy) ───────────────────────────────────

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ── Scraping de página de parque en pasesparques.cl ──────────────────────────

def scrape_pasesparques(slug: str) -> dict:
    url = f"https://www.pasesparques.cl/es/parks/{slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return {}

        soup = BeautifulSoup(r.text, "html.parser")
        texto = soup.get_text(" ", strip=True)
        data  = {"url_pases": url}

        # Región — aparece justo debajo del título h1
        # Patrón: "Región de X" o "Región del X"
        region_match = re.search(
            r"Regi[oó]n\s+(?:de\s+(?:la\s+|las\s+|los\s+|el\s+)?|del\s+)"
            r"([\w\s\,yáéíóúñÁÉÍÓÚÑ]+?)(?:\n|Abierto|Ver las|\|)",
            texto, re.IGNORECASE
        )
        if region_match:
            data["region_pases"] = region_match.group(0).strip().rstrip(",")

        # Horario
        horario_match = re.search(
            r"Abierto\s+(?:de\s+)?([\w\s]+?)\s+de\s+([\d:]+)\s+a\s+([\d:]+)",
            texto, re.IGNORECASE
        )
        if horario_match:
            data["horario"] = horario_match.group(0).strip()

        # Descripción — párrafo más largo y descriptivo
        descripcion_candidatos = []
        for p in soup.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if (
                len(txt) > 80
                and "cookie" not in txt.lower()
                and "javascript" not in txt.lower()
                and "pase" not in txt.lower()[:30]
                and txt[0].isupper()
            ):
                descripcion_candidatos.append(txt)

        if descripcion_candidatos:
            # Preferir el párrafo más largo y descriptivo
            mejor = max(descripcion_candidatos, key=len)
            data["descripcion_pases"] = mejor[:600]

        data["tiene_pase_digital"] = True
        return data

    except Exception as e:
        print(f"    ✗ Error en {slug}: {e}")
        return {}


# ── Pipeline de enriquecimiento ───────────────────────────────────────────────

def enriquecer():
    if not os.path.exists(INPUT_CSV):
        print(f"❌ No se encontró {INPUT_CSV}")
        print("   Primero corre scraper.py para generar el CSV base.")
        return

    with open(INPUT_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"\n🔄 Enriqueciendo {len(rows)} parques con pasesparques.cl\n")
    print("=" * 55)

    enriquecidos = 0
    for i, row in enumerate(rows, 1):
        nombre = row.get("nombre", "")
        slug   = SLUG_MAP.get(nombre)

        if not slug:
            print(f"[{i:02d}] {nombre:<35} → sin slug mapeado, skip")
            row["tiene_pase_digital"] = False
            continue

        print(f"[{i:02d}] {nombre:<35} → /{slug}")
        pases_data = scrape_pasesparques(slug)

        if not pases_data:
            print(f"      ⚠ Sin datos")
            row["tiene_pase_digital"] = False
            time.sleep(DELAY)
            continue

        # Completar región si falta
        region_actual = row.get("region", "").strip()
        if (not region_actual or len(region_actual) < 5) and pases_data.get("region_pases"):
            row["region"] = pases_data["region_pases"]
            print(f"      ✓ región: {row['region'][:40]}")

        # Reemplazar descripción si la actual es muy corta o vacía
        desc_actual = row.get("descripcion", "").strip()
        desc_nueva  = pases_data.get("descripcion_pases", "")
        if desc_nueva and (len(desc_actual) < 100 or len(desc_nueva) > len(desc_actual)):
            row["descripcion"] = desc_nueva
            print(f"      ✓ descripción actualizada ({len(desc_nueva)} chars)")

        # Campos nuevos
        if pases_data.get("horario"):
            row["horario"] = pases_data["horario"]
        row["slug_pases"]        = slug
        row["url_pases"]         = pases_data.get("url_pases", "")
        row["tiene_pase_digital"] = pases_data.get("tiene_pase_digital", False)

        enriquecidos += 1
        time.sleep(DELAY)

    # Guardar
    os.makedirs("output", exist_ok=True)
    campos_originales = list(rows[0].keys()) if rows else []
    campos_nuevos = ["horario", "slug_pases", "url_pases", "tiene_pase_digital"]
    todos_campos = campos_originales + [c for c in campos_nuevos if c not in campos_originales]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=todos_campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 55)
    print(f"✅ Enriquecimiento completo")
    print(f"   Parques enriquecidos: {enriquecidos}/{len(rows)}")
    print(f"   Output: {OUTPUT_CSV}")
    sin_region = [r["nombre"] for r in rows if not r.get("region", "").strip()]
    if sin_region:
        print(f"\n⚠️  Aún sin región ({len(sin_region)}):")
        for n in sin_region:
            print(f"   - {n}")
        print("   → Completar manualmente o agregar al SLUG_MAP")


if __name__ == "__main__":
    enriquecer()