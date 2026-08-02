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
| Cámaras de control vehicular | data.buenosaires.gob.ar/dataset/camaras-fijas-control-vehicular | 15KB |
| Cajeros automáticos | data.buenosaires.gob.ar/dataset/cajeros-automaticos | 214KB |
| Establecimientos educativos | data.buenosaires.gob.ar/dataset/establecimientos-educativos | 1.1MB |
| Hospitales | data.buenosaires.gob.ar/dataset/hospitales | 15.6KB |
| Divisiones comisarías vecinales | data.buenosaires.gob.ar/dataset/divisiones-comisarias-vecinales | 2.5MB |
| Trenes GTFS | data.buenosaires.gob.ar/dataset/trenes-gtfs | 7.5MB descomprimido |
| Comisarías (ubicación puntual) | data.buenosaires.gob.ar/dataset/comisarias-policia-ciudad | 10KB |
| Universidades | data.buenosaires.gob.ar/dataset/universidades | 37KB |
| Espacios verdes públicos | data.buenosaires.gob.ar/dataset/espacios-verdes | 15MB |

Los datos crudos no se versionan en git — se descargan localmente con los scripts de `pipeline/`.

## Estado de la ingesta

Las 6 fuentes previstas para la Fase 1 (riesgo + transporte) están completas, más 6 fuentes de contexto adicionales (POIs, cámaras, trenes).

| Fuente | Filas | Notas |
|---|---|---|
| Delitos | 1.353.136 | 2016-2025 |
| Siniestros viales | 63.081 hechos + 75.197 víctimas | 2019-2025 |
| Alumbrado LED | 102.700 luminarias | cobertura completa 15 comunas |
| Colectivos GTFS | 43.594 paradas, 1.052 ramales | feed sin actualizar desde 2019-09-30 |
| EcoBici | 48.222.663 viajes agregados, 570 estaciones | 2010-2026. Máquina de desarrollo con 3.4GB de RAM — todo se procesa en chunks y se agrega directo a "viajes por estación/hora/día de semana" en vez de guardar cada viaje. 2014 (~2% del histórico) queda afuera por tener un esquema propio sin id de estación ni coordenadas — ver nota en `pipeline/ingest_ecobici.py`. |
| Subte Molinetes | 2.799.213.945 pasajeros agregados, 90 estaciones | 2013-2025. 96.8% geolocalizado (matching por tokens + abreviaturas + alias manuales contra el dataset de estaciones, que usa nombres oficiales distintos a los de molinetes); el 3.2% restante son variantes de corrupción de encoding en nombres con Ñ/Ü — ver nota en `pipeline/ingest_molinetes.py`. |
| Cámaras de control vehicular | 224 | analítica de video + cinemómetros |
| Cajeros automáticos | 1.279 | |
| Establecimientos educativos | 2.767 | reproyectadas desde el sistema plano legacy "0 de Flores" (ver `pipeline/geo_utils.py`), ~100m de margen de error |
| Hospitales | 36 | públicos únicamente; mismo sistema de coordenadas que escuelas |
| Divisiones comisarías vecinales | 45 | son polígonos de zona de patrullaje, no la ubicación puntual de cada comisaría — se guarda el centroide + el polígono original en WKT |
| Comisarías (ubicación puntual) | 75 | complementa lo anterior con la dirección real de cada comisaría, lat/lon directo sin proyección rara |
| Trenes GTFS | 248 paradas, 27 ramales | único dataset que extiende cobertura más allá de CABA hacia el conurbano; feed sin actualizar desde 2020-02-10 |
| Universidades | 153 | lat/lon directo, sin proyección rara esta vez |
| Espacios verdes públicos | 2.176 (plazas, plazoletas, parques) | polígonos — se guarda centroide + WKT original para join espacial futuro |

### Datos que se buscaron y no existen como abiertos

Cantidad de efectivos/oficiales, cantidad de móviles/patrullas disponibles, ubicación de radares móviles de velocidad, y la red completa de cámaras de seguridad urbana (más allá de las 224 de control vehicular) **no están publicados** — es información operativa de seguridad que el gobierno no divulga en detalle, tiene sentido que no exista. "Botones antipánico" sí existe pero es solo un total anual a nivel ciudad, sin geolocalización, no sirve para el modelo.

### Lecciones de esta fase

Los datasets de transporte (EcoBici, Molinetes) cambiaron de esquema de columnas, delimitador, encoding o estructura de archivo **casi todos los años** — nada de esto está documentado en el portal de datos abiertos, se descubrió a fuerza de que el pipeline fallara con errores concretos. Cosas a tener en cuenta si se vuelve a correr la ingesta desde cero o se agregan años nuevos:

- Los scripts validan integridad de cada descarga (zip corrupto → se borra y re-descarga solo) porque el portal tiene caídas y timeouts de red frecuentes.
- No asumir que un ZIP tiene un solo archivo adentro — desde 2022 Molinetes viene partido en ~24-26 archivos por año.
- No asumir el mismo delimitador o encoding entre años de la misma fuente.
- Los joins por nombre de estación (texto libre) contra datasets de referencia nunca son 100% exactos — documentar el % sin matchear en vez de asumir cobertura total.
- **GCBA usa dos sistemas de coordenadas planas distintos entre datasets, sin documentarlo**: siniestros viales usa GKBA (Gauss-Krüger CABA 2019, oficial desde 2019), pero escuelas y hospitales todavía usan un sistema previo ("0 de Flores"). Aplicar la fórmula de uno al otro tira puntos a 90km de distancia sin ningún error visible en el código — solo se nota si se valida el rango de lat/lon contra los límites reales de la ciudad. Se calibraron ambos cruzando direcciones conocidas contra el geocodificador oficial de GCBA (`ws.usig.buenosaires.gob.ar`) en vez de confiar en el código EPSG que documenta el portal (9497), que ni siquiera existe en las bases de PROJ. Ver `pipeline/geo_utils.py`.
