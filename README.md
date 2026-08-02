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
| EcoBici recorridos | data.buenosaires.gob.ar/dataset/bicicletas-publicas | 2.0GB comprimido (crudo, no se guarda descomprimido) |
| Subte Molinetes | data.buenosaires.gob.ar/dataset/subte-viajes-molinetes | 1.1GB comprimido (crudo, no se guarda descomprimido) |

Los datos crudos no se versionan en git — se descargan localmente con los scripts de `pipeline/`.

## Estado de la ingesta

Las 6 fuentes de datos previstas para la Fase 1 están completas.

| Fuente | Filas | Notas |
|---|---|---|
| Delitos | 1.353.136 | 2016-2025 |
| Siniestros viales | 63.081 hechos + 75.197 víctimas | 2019-2025 |
| Alumbrado LED | 102.700 luminarias | cobertura completa 15 comunas |
| Colectivos GTFS | 43.594 paradas, 1.052 ramales | feed sin actualizar desde 2019-09-30 |
| EcoBici | 48.222.663 viajes agregados, 570 estaciones | 2010-2026. Máquina de desarrollo con 3.4GB de RAM — todo se procesa en chunks y se agrega directo a "viajes por estación/hora/día de semana" en vez de guardar cada viaje. 2014 (~2% del histórico) queda afuera por tener un esquema propio sin id de estación ni coordenadas — ver nota en `pipeline/ingest_ecobici.py`. |
| Subte Molinetes | 2.799.213.945 pasajeros agregados, 90 estaciones | 2013-2025. 96.8% geolocalizado (matching por tokens + abreviaturas + alias manuales contra el dataset de estaciones, que usa nombres oficiales distintos a los de molinetes); el 3.2% restante son variantes de corrupción de encoding en nombres con Ñ/Ü — ver nota en `pipeline/ingest_molinetes.py`. |

### Lecciones de esta fase

Los datasets de transporte (EcoBici, Molinetes) cambiaron de esquema de columnas, delimitador, encoding o estructura de archivo **casi todos los años** — nada de esto está documentado en el portal de datos abiertos, se descubrió a fuerza de que el pipeline fallara con errores concretos. Cosas a tener en cuenta si se vuelve a correr la ingesta desde cero o se agregan años nuevos:

- Los scripts validan integridad de cada descarga (zip corrupto → se borra y re-descarga solo) porque el portal tiene caídas y timeouts de red frecuentes.
- No asumir que un ZIP tiene un solo archivo adentro — desde 2022 Molinetes viene partido en ~24-26 archivos por año.
- No asumir el mismo delimitador o encoding entre años de la misma fuente.
- Los joins por nombre de estación (texto libre) contra datasets de referencia nunca son 100% exactos — documentar el % sin matchear en vez de asumir cobertura total.
