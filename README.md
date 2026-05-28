# CONAF Camping Scraper 🌲

Extrae datos de los **39 parques nacionales de Chile** desde CONAF y OpenStreetMap.
Output: `parks.csv` y `parks.geojson` listos para usar en una web app.

## Instalación

```bash
pip install requests beautifulsoup4 lxml
```

## Uso

```bash
python scraper.py
```

Demora aprox. **5–8 minutos** (delays incluidos para no saturar los servidores).
Guarda progreso cada 5 parques en `output/parks_parcial.csv`.

## Output

### `parks.csv`
| columna | descripción |
|---|---|
| `nombre` | Nombre oficial del parque |
| `region` | Región administrativa de Chile |
| `lat` / `lon` | Coordenadas (desde OpenStreetMap) |
| `superficie_ha` | Hectáreas |
| `tiene_camping` | `True/False` (detección por keywords) |
| `servicios` | Lista separada por `\|`: baños, duchas, senderos, etc. |
| `descripcion` | Primer párrafo de la página CONAF (hasta 500 chars) |
| `url_conaf` | URL fuente |

### `parks.geojson`
Mismo data en formato GeoJSON Point, listo para Leaflet / Mapbox / Kepler.gl.

## Post-procesamiento recomendado

Después de correr el scraper, revisar y completar manualmente:

1. **Parques sin coords** — buscar en Google Maps y agregar lat/lon
2. **Columna `tiene_camping`** — puede dar falsos positivos; validar con ojo
3. **Enriquecer con pasesparques.cl** — tiene precios y disponibilidad

## Próximos pasos sugeridos

- Cruzar con datos de SERNATUR (visitación por año) para priorizar parques
- Agregar columna `reserva_requerida` (algunos parques exigen reserva en pasesparques.cl)
- Incorporar reservas nacionales (45 más) con el mismo approach
- Enriquecer con iOverlander y Park4Night para campings no-CONAF
