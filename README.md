# ATLAS SENTINEL

Asistente de seguridad para conductores y planificación urbana en Buenos Aires. Cruza delitos geolocalizados con datos de transporte (colectivos, EcoBici, subte), alumbrado público y siniestros viales para estimar riesgo por zona y horario — no solo un heatmap estático, sino un modelo que pesa el último tramo a pie y el efecto de repetición cercana (near-repeat) tras un hecho.

## Estructura

- `pipeline/` — scripts de ingesta y normalización de cada fuente de datos
- `models/` — modelos de riesgo (baseline KDE, near-repeat, incertidumbre por zona)
- `api/` — backend FastAPI que sirve rutas + score de riesgo
- `web/` — frontend (app conductor + dashboard de planificación urbana)
- `notebooks/` — exploración y validación de datos

## Fuentes de datos

| Fuente | Origen | Tamaño real |
|---|---|---|
| Delitos CABA | data.buenosaires.gob.ar/dataset/delitos | ~180MB (2016-2025) |
| Siniestros viales | data.buenosaires.gob.ar/dataset/victimas-siniestros-viales | ~16MB |
| Alumbrado LED | data.buenosaires.gob.ar/dataset/alumbrado-led | 9.4MB |
| Colectivos GTFS | data.buenosaires.gob.ar/dataset/colectivos-gtfs | 209MB |
| EcoBici recorridos | data.buenosaires.gob.ar/dataset/bicicletas-publicas | 2.15GB comprimido / ~8.8GB descomprimido |
| Subte Molinetes | data.buenosaires.gob.ar/dataset/subte-viajes-molinetes | 1.1GB comprimido / ~11.7GB descomprimido |

Los datos crudos no se versionan en git — se descargan localmente con los scripts de `pipeline/`.
