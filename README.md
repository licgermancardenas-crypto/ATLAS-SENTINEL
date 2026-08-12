# ATLAS SENTINEL

Asistente de seguridad para conductores y planificación urbana en Buenos Aires (nombre de venta: **SIGE-BA**). Cruza delitos geolocalizados con datos de transporte (colectivos, EcoBici, subte), alumbrado público y siniestros viales para estimar riesgo por zona y horario — no solo un heatmap estático, sino un modelo núcleo espacio-temporal (grilla H3) del que se desprenden 3 módulos de decisión operativa (patrullas, cámaras, controles de acceso).

Arquitectura técnica completa del modelo: [`arquitectura-sige-ba.pdf`](arquitectura-sige-ba.pdf).

## Estructura

- `pipeline/` — scripts de ingesta y normalización de cada fuente de datos (Fase 1, completa)
- `data/features/` — tablas intermedias post-cruce espacial (hex_maestra, datasets con hex_id asignado) — no versionado en git, se regenera con `src/etl/`
- `src/etl/` — Capa 0: unificación espacio-temporal (grilla H3-8, asignación de hex_id/turno a cada dataset)
- `src/model_core/` — Capa 1: modelo núcleo de riesgo (XGBoost/LightGBM, objetivo Poisson)
- `src/optimization/` — Capa 2: módulos A/B/C (asignación de patrullas, cámaras nuevas, controles de acceso)
- `src/validation/` — Capa 3: SHAP, backtesting, métricas
- `src/export/` — genera los JSON/GeoJSON livianos que consume el dashboard
- `notebooks/` — exploración y validación de datos
- `models/`, `api/`, `web/` — carpetas del scaffold original; el plan vigente las reemplaza por `src/*` + `dashboard/` (Next.js, separado) — ver el PDF de arquitectura

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
| Socioeconómico por comuna (NBI + hacinamiento) | data.buenosaires.gob.ar (Instituto de Vivienda) | <1KB |
| Barrios (polígonos) | data.buenosaires.gob.ar/dataset/barrios | 651KB |
| Radios censales (Censo 2010) | data.buenosaires.gob.ar/dataset/informacion-censal-por-radio | 2.5MB |
| Población por comuna y por barrio | data.buenosaires.gob.ar/dataset/estructura-demografica y /barrios | <1KB c/u |
| Calles (callejero, con jerarquía vial) | data.buenosaires.gob.ar/dataset/calles | 10.6MB |
| Accesos por autopista (peajes/pórticos) | data.buenosaires.gob.ar/dataset/peajes-porticos-autopistas | <1KB |
| Estadios | data.buenosaires.gob.ar/dataset/estadios | 10KB |
| Eventos masivos (permisos) | data.buenosaires.gob.ar/dataset/permisos-eventos-masivos | ~230KB (5 años) |
| Clima diario | NASA POWER API (power.larc.nasa.gov) | ~130KB |

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
| Socioeconómico por comuna | 15 comunas | % hogares con NBI + % hacinamiento. Sin coordenadas, se cruza por el campo "comuna" que ya existe en delitos/siniestros/alumbrado |
| Barrios | 48 | polígonos con comuna asignada — unidad intermedia entre comuna (15) y radio censal (3.554) para agrupar/mostrar riesgo |
| Radios censales | 3.554 | Censo 2010 — población total, sexo, viviendas, hogares y % NBI por radio (~800 hab. c/u). Es el denominador que faltaba para "delitos per cápita" y la unidad más fina disponible con población real. Único mismatch de nombres detectado: dataset de población usa "BOCA", barrios.csv usa "LA BOCA" (corregido a mano en `pipeline/ingest_poblacion.py`) |
| Población por comuna / por barrio | 15 comunas + 48 barrios | comuna es estimación 2017 (complementa NBI/hacinamiento, que no traía población total); barrio es censo 2010, mismo año que radios censales |
| Calles (callejero) | 31.961 tramos | trae jerarquía vial (troncal/distribuidora/local) y sentido de circulación; 1.729 tramos sin comuna asignada (autopistas/bordes). Columna "long" del origen es largo del tramo en metros, no longitud — ver nota en `pipeline/ingest_calles.py` |
| Accesos por autopista | 11 peajes/pórticos | AU Illia, Perito Moreno, Dellepiane, 25 de Mayo, Paseo del Bajo |
| Estadios | 30 | mismo sistema de coordenadas legacy que escuelas/hospitales |
| Eventos masivos | 2.898 permisos | 2019 + 2023-2026 (2020-2022 no publicados). Esquema distinto en cada archivo — ver notas de calidad abajo |
| Clima diario | 3.866 días (2016-01-01 a hoy) | NASA POWER, punto único (Obelisco) — no diferencia microclima entre barrios |

### Datos que se buscaron y no existen como abiertos

Cantidad de efectivos/oficiales, cantidad de móviles/patrullas disponibles, ubicación de radares móviles de velocidad, y la red completa de cámaras de seguridad urbana (más allá de las 224 de control vehicular) **no están publicados** — es información operativa de seguridad que el gobierno no divulga en detalle, tiene sentido que no exista. "Botones antipánico" sí existe pero es solo un total anual a nivel ciudad, sin geolocalización, no sirve para el modelo.

Nivel de ingreso y tasa de desempleo tampoco existen desglosados por comuna/barrio — solo hay totales a nivel ciudad por año (útiles para contexto, inútiles para diferenciar riesgo entre zonas). Se usan NBI y hacinamiento como proxies de vulnerabilidad socioeconómica en su lugar, que sí tienen ese desglose.

Series históricas diarias del Servicio Meteorológico Nacional **no son automatizables**: su único endpoint público estable solo da tiempo actual + pronóstico a 5 días, y la página de descarga de históricos está detrás de Cloudflare. Se usa NASA POWER como reemplazo (satelital, no estación puntual) — ver `pipeline/ingest_clima.py`.

Segmentación de población por edad/sexo **tampoco existe por zona**: el único dataset de estructura etaria de GCBA (`estructura-demografica/est_pob_sexo...`) es serie histórica 1855-presente a nivel ciudad completa, sin ningún desglose espacial — no sirve para diferenciar riesgo entre zonas y no se ingesta. Censo 2022 por radio tampoco está publicado en este portal (solo 2001 y 2010 a esa granularidad); si hace falta, habría que cruzar con el Portal Geoestadístico de INDEC, que usa otra cartografía/códigos.

### Lecciones de esta fase

Los datasets de transporte (EcoBici, Molinetes) cambiaron de esquema de columnas, delimitador, encoding o estructura de archivo **casi todos los años** — nada de esto está documentado en el portal de datos abiertos, se descubrió a fuerza de que el pipeline fallara con errores concretos. Cosas a tener en cuenta si se vuelve a correr la ingesta desde cero o se agregan años nuevos:

- Los scripts validan integridad de cada descarga (zip corrupto → se borra y re-descarga solo) porque el portal tiene caídas y timeouts de red frecuentes.
- No asumir que un ZIP tiene un solo archivo adentro — desde 2022 Molinetes viene partido en ~24-26 archivos por año.
- No asumir el mismo delimitador o encoding entre años de la misma fuente.
- Los joins por nombre de estación (texto libre) contra datasets de referencia nunca son 100% exactos — documentar el % sin matchear en vez de asumir cobertura total.
- **GCBA usa dos sistemas de coordenadas planas distintos entre datasets, sin documentarlo**: siniestros viales usa GKBA (Gauss-Krüger CABA 2019, oficial desde 2019), pero escuelas y hospitales todavía usan un sistema previo ("0 de Flores"). Aplicar la fórmula de uno al otro tira puntos a 90km de distancia sin ningún error visible en el código — solo se nota si se valida el rango de lat/lon contra los límites reales de la ciudad. Se calibraron ambos cruzando direcciones conocidas contra el geocodificador oficial de GCBA (`ws.usig.buenosaires.gob.ar`) en vez de confiar en el código EPSG que documenta el portal (9497), que ni siquiera existe en las bases de PROJ. Ver `pipeline/geo_utils.py`. Estadios (agregado después) también usa el sistema legacy, no el nuevo.
- El dataset de eventos masivos tiene **tres esquemas distintos en 5 archivos anuales** (2019 vs. 2023 vs. 2024-2026): cambia el delimitador, las columnas disponibles (barrio/aforo/lat-lon no están en todos) y hasta el encoding — el archivo 2023 es cp850 (DOS Latin US), el único de todo el proyecto que no es utf-8. Se detectó porque "Denominación" rompía el parser en utf-8 y en latin-1 daba un carácter distinto al esperado. Ver `pipeline/ingest_eventos_masivos.py`.
- No asumir que un nombre de columna es lo que parece: en el callejero, la columna "long" es el largo del tramo en metros, no longitud geográfica.

## Estado de Capa 0 (unificación espacio-temporal)

Grilla H3-8 generada sobre CABA (unión de los 48 barrios, no existe un dataset propio de "límite CABA"): **459 hexágonos** (`data/features/hex_maestra.parquet`), con `barrio_id`/`comuna_id` (point-in-polygon contra `barrios.parquet`) y `radio_censal_id` (contra `radios_censales.parquet`) por centroide. 58 hexágonos de borde/costa no caen dentro de ningún barrio (agua, terraplenes) — quedan sin `barrio_id`/`comuna_id`, es correcto que así sea.

`h3.polygon_to_cells` con el modo por default (`contain="center"`, solo hexágonos cuyo *centro* cae adentro del polígono) dejaba 1-6% de los puntos de delitos/siniestros/alumbrado fuera de la grilla — puntos reales de CABA cerca de la costa caían en hexágonos de borde cuyo centro quedaba just afuera. Se cambió a `polygon_to_cells_experimental(..., contain="overlap")` (cualquier hexágono que toque el polígono, aunque sea parcial) y el problema bajó a <0,5%.

Datasets ya cruzados con hex_id (`src/etl/assign_hex_puntual.py`, `assign_hex_calles.py`): delitos, siniestros_hechos, cámaras, alumbrado, cajeros, comisarías (ubicación puntual), escuelas, hospitales, universidades, estadios, ecobici/molinetes (estaciones), calles (por el punto medio del tramo, ya calculado en `pipeline/ingest_calles.py`), accesos_autopistas (+ tramo de calle troncal más cercano, reproyectado a EPSG:5347 para que la distancia sea en metros reales). Eventos masivos también pasó por el script pero solo 129 de 2.898 filas tienen hex_id (las de 2019, únicas con lat/lon) — el resto (2023-2026) solo tiene barrio, que es un tipo de cruce distinto (join por nombre, no point-in-hex), pendiente.

Pendiente, y son operaciones distintas a point-in-hex (no encajan en `asignar_hex_id`): **espacios_verdes** y **comisarias.parquet** (el de zonas de patrullaje) necesitan overlay de polígono contra la grilla (% de área, no un punto); **población por hex** (denominador per cápita) sale de prorratear `poblacion_comuna`/`poblacion_barrio` por área, aunque ya se puede aproximar sin prorratear porque `hex_maestra` ya tiene `radio_censal_id` — un join directo contra `radios_censales.poblacion_total` alcanza para una primera versión.

## Estado de Capa 1 v1 (modelo núcleo, sin exógenas)

`src/model_core/build_training_table.py` arma `data/features/training_table.parquet`: grano (hex_id, fecha, turno), 401 hexágonos × 3.653 días (2016-2025) × 4 turnos = 5.859.412 filas (907MB en memoria, 28MB en parquet). Target: conteo total de delitos (los 6 tipos juntos — desagregar por tipo multiplicaría la tabla ~6x, se deja para v2). Features: lags 7/30/365 días y rolling 7/30 días por hex×turno, vecindad espacial (anillos H3 k=1/k=2, sobre el `roll_30d` ya rezagado de cada vecino para no filtrar información futura — usar el conteo contemporáneo del vecino sería fuga de datos), NBI por radio censal, hacinamiento por comuna (no hay a nivel radio), población, cámaras y luminarias por hex, y calendario (día de semana, mes, feriado vía API de ArgentinaDatos).

`src/model_core/train_baseline.py` entrena LightGBM con objetivo Poisson, split temporal (train ≤2023, val 2024 para early stopping, test 2025). Resultado en test:

| | MAE | Recall@10% área | Recall@20% área | Recall@30% área |
|---|---|---|---|---|
| Modelo LightGBM | 0.290 | 27.7% | 45.4% | 58.5% |
| Baseline naive (promedio histórico hex×turno) | 0.296 | 27.4% | 44.7% | 58.4% |

**Lectura honesta**: el modelo le gana apenas al baseline naive. `hex_id` y `radio_censal_id` dominan la importancia de features por lejos — la mayor parte del "riesgo" que se captura es la heterogeneidad espacial pura (qué tan peligroso es el lugar en promedio), no la dinámica temporal (rachas, contagio espacial). Con una tasa media de 0,23 delitos por hex×turno y 82,8% de celdas en cero, tiene sentido: a esta resolución el proceso es casi estacionario por celda, así que un promedio histórico ya captura casi todo. Lo bueno: **hay concentración espacial real y se está capturando** (30% del área concentra 58% de los delitos, muy por encima de lo esperable si el riesgo fuera uniforme).

### v2 — exógenas (`src/model_core/agregar_exogenas.py`, `train_v2.py`)

Se sumó clima (join por fecha), flag de evento masivo (point-in-hex para 2019, join por barrio para 2023-2026) y cercanía a estadio (buffer 500m, reproyectado a EPSG:5347). **No mejoró nada** respecto a v1 — MAE 0.2921 idéntico a v1, Recall@K prácticamente igual (45,5% / 58,6%). `evento_en_hex` y `evento_en_barrio` tienen importancia **0** en el modelo (nunca se usaron en ningún split): a esta resolución (hex×día×turno) los eventos son demasiado raros — `evento_en_hex` es positivo en ~0,001% de las filas — para que haya señal aprendible. Clima aporta algo de importancia (`temp_media_c` por encima de varios lags) pero no alcanza a mover el Recall@K.

**Conclusión de v1 vs. v2**: el cuello de botella no son las exógenas, es que el proceso a este grano es casi puramente espacial. Antes de seguir sumando variables, tiene más sentido: (a) construir el Módulo A sobre lo que ya funciona (la concentración espacial), ya que no depende de mejorar la parte temporal, o (b) probar un grano temporal más agregado (semanal en vez de diario) donde la señal dinámica podría distinguirse mejor del ruido.

**Reentreno con los overlays de polígono** (`poblacion_hex`, `pct_espacio_verde`, `comisaria_id` de `src/etl/overlay_poligonos.py`, sumados a `build_training_table.py`): mismo resultado que v2 — MAE y Recall@K **idénticos** al modelo sin estas features (0.2902, 45.4%, 58.5%), y las tres quedan con importancia bajísima. Confirma el patrón: a esta resolución (hex×día×turno) el modelo ya captura "dónde es peligroso" a través de `hex_id`/`radio_censal_id`/historial — variables de contexto estático adicionales no aportan señal medible que esos features no capturen ya indirectamente.

**Grano semanal** (`build_training_table_semanal.py`, `train_semanal.py`): la hipótesis era que el conteo diario, muy disperso (82,8% ceros, media 0,23), enterraba señal dinámica que un grano más agregado podría revelar. Agregar por semana (401 hex × 523 semanas × 4 turnos = 838.892 filas) baja los ceros a 43,8% y sube la media a 1,59. Resultado matizado:

| | MAE vs. baseline naive | Recall@20% | Recall@30% |
|---|---|---|---|
| Diario | 0.2902 vs 0.2961 (mejora relativa 1,99%) | 45,4% | 58,5% |
| Semanal | 0.9255 vs 0.9518 (mejora relativa **2,76%**) | 45,5% | 58,6% |

El grano semanal le gana un poco más al baseline en error (MAE/RMSE), pero el **Recall@K —la métrica que más importa para priorizar zonas— queda prácticamente igual**. Conclusión: agregar por semana no cambia la historia de fondo, solo la afina levemente. La concentración espacial sigue siendo lo que carga el peso del modelo, con o sin más resolución temporal.

### Desagregación por tipo de delito (`build_training_table_tipo.py`, `train_por_tipo.py`)

Pendiente anotado desde v1 ("desagregar por tipo multiplicaría la tabla ~6x, se deja para v2"). El modelo núcleo predice los 6 tipos sumados, y la hipótesis era que mezclarlos diluye señal: un hexágono con mucho hurto diurno y otro con robo nocturno entran al modelo como el mismo número.

**Qué cambia y qué no**: se mantiene la grilla (hex_id, fecha, turno) y solo cambian el target y lo que se deriva de él — conteo, lags 7/30/365, rolling 7/30 y vecindad espacial pasan a ser *del tipo*. El contexto (socioeconómico, infraestructura, calendario) es independiente del tipo, así que `build_training_table_tipo.py` reusa las funciones de `build_training_table.py` en vez de duplicar el pipeline. No se arma una tabla ancha de 6 targets (~35M filas, no entra en 3,4GB): se genera y entrena **un tipo por corrida**.

**Cómo se compara**: cada tipo contra **su propio** baseline naive (promedio histórico hex×turno). Comparar el MAE entre tipos no dice nada — un tipo con tasa 0,0002 tiene MAE bajísimo por ser raro, no por estar bien predicho. Lo comparable es la mejora relativa sobre la propia referencia, y el PAI/PEI, que es adimensional.

| Tipo | Tasa/celda | % ceros | var/media | MAE | MAE naive | Mejora | PAI@10% | PEI@10% |
|---|---|---|---|---|---|---|---|---|
| Homicidios | 0,0002 | 99,98% | 1,08 | 0,00025 | 0,00033 | +23,9% | 4,36 | **54,0%** |
| Lesiones | 0,0207 | 98,1% | 1,14 | 0,0330 | 0,0363 | **+9,2%** | 3,10 | 97,6% |
| Robo | 0,0992 | 91,4% | 1,21 | 0,1428 | 0,1524 | **+6,4%** | 2,92 | 99,2% |
| Amenazas | 0,0157 | 98,6% | 1,34 | 0,0293 | 0,0304 | +3,7% | 2,69 | 96,0% |
| Vialidad | 0,0140 | 98,6% | 1,04 | 0,0314 | 0,0315 | +0,3% | 2,65 | 95,2% |
| Hurto | 0,0752 | 93,5% | 1,49 | 0,1345 | 0,1319 | **−2,0%** | 3,10 | 99,6% |

**1. Desagregar recupera señal real.** El modelo agregado le gana al baseline apenas 2% (0,2902 vs. 0,2961). Lesiones le gana **9,2%** y Robo **6,4%**. Mezclar seis procesos con dinámicas distintas estaba promediando efectos que se cancelan entre sí — el modelo agregado terminaba prediciendo algo que no le sirve bien a ninguno.

**2. Homicidios encabeza la tabla y hay que descartarlo igual.** El +23,9% es un espejismo: son **78 hechos en todo el año de test** (1.075 en diez años, 99,98% de celdas en cero). La mejora en términos absolutos es de 0,000078 delitos por celda — nula operativamente. La columna que lo delata es el **PEI: 54%** contra 95-99,6% de todos los demás. El PEI mide qué tan cerca está el modelo del techo alcanzable con información perfecta; a este grano no hay patrón que aprender, y el ranking se reordena entero si se mueven tres homicidios de lugar. **Caso de ordenar por la métrica equivocada**: si se mira "mejora", homicidios es el mejor modelo del proyecto; mirando PEI, es el único que no funciona.

**3. Hurto es el único con mejora negativa — y conviene no modelarlo.** El promedio histórico predice mejor que el modelo (MAE 0,1345 vs. 0,1319). No es un bug: significa que el hurto es **más estacionario** que el resto, donde ocurrió históricamente predice mejor que cualquier dinámica temporal aprendible. Y a la vez tiene PEI 99,6% y PAI 3,10, o sea que concentra espacialmente tan bien como el que más. Lectura operativa: para hurto, mapa histórico y nada más.

**4. La sobredispersión que justificó Tweedie era, en buena parte, artefacto de mezclar.** La auditoría midió var/media = 1,59 sobre el agregado y por eso se adoptó Tweedie en vez de Poisson. Por separado los tipos van de **1,04 a 1,49**: ninguno alcanza el 1,59 del agregado. Sumar seis procesos heterogéneos infla la dispersión por encima de la de cada uno. La decisión de usar Tweedie sigue siendo razonable para el modelo agregado, pero el diagnóstico que la motivó describía la mezcla, no el fenómeno.

**5. Vialidad no pertenece a este análisis.** +0,3% es empate estadístico con el naive, y es coherente: son siniestros viales, no delitos de seguridad — su patrón lo manda la infraestructura vial, que es fija. Se deja en la tabla por completitud, pero no debería reportarse junto a los demás.

Nota metodológica: los PEI de 95-99,6% en los cinco tipos que no son homicidios dicen que **a este grano queda poquísimo margen de mejora en concentración espacial**, cualquiera sea el algoritmo. La ganancia de desagregar está en el error de predicción, no en la capacidad de priorizar zonas.

Los seis modelos quedan en `data/features/modelos/modelo_{tipo}.txt` y la comparación en `comparacion_por_tipo.parquet`; cada corrida queda en MLflow como `tipo-{nombre}`.

### Riesgo por tipo en los módulos (`predecir_riesgo_por_tipo.py`, `comparar_modulo_a_por_tipo.py`)

Desagregar mejoró la predicción del **conteo**. Pero los módulos de Capa 2 no optimizan conteos: optimizan una **priorización espacial**. Que el modelo por tipo prediga mejor no implica que cambie ninguna decisión operativa — eso hay que medirlo aparte.

**Qué tipo entra en la superficie de riesgo, y por qué** (las decisiones salen de lo medido, no de criterio a mano):

| Tipo | Fuente | Motivo |
|---|---|---|
| Robo, Lesiones, Amenazas | modelo por tipo | le ganan a su baseline (+6,4%, +9,2%, +3,7%) |
| Hurto | **promedio histórico** | el modelo es *peor* que el naive (−2,0%): usarlo sería ignorar el propio resultado |
| Vialidad | **excluido** | siniestros viales, no delitos de seguridad; empata con el naive |
| Homicidios | **excluido** | 78 hechos en el año de test, PEI 54% |

**La combinación es una decisión de política, no de modelo.** Los módulos consumen *una* superficie, y fundirlas exige decidir cuánto pesa una lesión contra un robo. El default en `PESOS` es peso igual sobre superficies **normalizadas** — lo único defendible sin tomar posición. Ponderar por volumen reproduciría el modelo agregado y anularía el sentido de desagregar; normalizar es necesario porque las tasas difieren ~6x entre tipos.

Las superficies **correlacionan alto entre sí** (Spearman 0,84 a 0,92): en general priorizan los mismos hexágonos. Pero el MCLP no consume la correlación, consume el ranking, así que se resolvió el Módulo A una vez por superficie (K=40, turno Tarde, misma matriz de cobertura de red).

**Superposición de planes** — ubicaciones compartidas sobre 40:

| | robo | hurto | lesiones | amenazas | combinado | agregado |
|---|---|---|---|---|---|---|
| robo | — | 0,70 | 0,73 | 0,75 | 0,80 | 0,83 |
| hurto | 0,70 | — | **0,60** | **0,60** | 0,70 | 0,80 |
| lesiones | 0,73 | 0,60 | — | 0,80 | 0,83 | 0,63 |
| amenazas | 0,75 | 0,60 | 0,80 | — | 0,90 | 0,70 |

**Retención cruzada** — cobertura del riesgo de la fila usando el plan de la columna, sobre su propio óptimo:

| | plan robo | plan hurto | plan lesiones | plan amenazas | plan combinado | plan agregado |
|---|---|---|---|---|---|---|
| riesgo robo | 1,000 | 0,938 | 0,944 | 0,930 | 0,970 | **0,980** |
| riesgo hurto | 0,925 | 1,000 | 0,854 | **0,817** | 0,890 | **0,964** |
| riesgo lesiones | 0,924 | **0,825** | 1,000 | 0,979 | 0,983 | 0,913 |
| riesgo amenazas | 0,903 | **0,811** | 0,964 | 1,000 | 0,982 | 0,896 |

**Sí cambia el plan, y no poco.** Hurto y lesiones comparten solo el **60%** de las ubicaciones: 16 de 40 difieren. Usar el plan de hurto para amenazas retiene apenas el **81,1%** de la cobertura óptima. Es coherente con la naturaleza de cada delito — el hurto se concentra en zonas comerciales del microcentro, lesiones y amenazas se reparten distinto.

**Pero el plan agregado ya es un compromiso razonable.** Retiene 98,0% para robo y 96,4% para hurto (los dos que dominan el volumen), y cae a 91,3% y 89,6% para lesiones y amenazas. **Ningún plan único domina**: el peor caso del agregado (89,6%) es prácticamente igual al del combinado (89,0%). Desagregar rinde si se quiere optimizar *para un tipo específico*; para un despliegue único, el agregado no está lejos del mejor compromiso posible.

**Bug propio, encontrado y corregido — cambiaba la conclusión.** La primera corrida de `comparar_modulo_a_por_tipo.py` daba 85-97,5% de superposición, y con eso la lectura habría sido "desagregar no cambia nada operativamente" — la conclusión contraria a la real. La causa: `demanda` ya traía una columna `score_riesgo` (la agregada), y al renombrar `score_lesiones → score_riesgo` quedaban **dos columnas con el mismo nombre**; `resolver_mclp` terminaba optimizando un DataFrame en vez de una Serie, en silencio. Se detectó porque una celda de retención cruzada daba **1,015** — matemáticamente imposible: ningún plan puede cubrir más riesgo que el plan óptimo para ese riesgo. Se agregó un `assert` que verifica que quede una sola columna de score. La lección: en una matriz de comparación, la diagonal y las cotas conocidas son el control de sanidad.

**No se cambió el pipeline de producción**: `predecir_riesgo.py` y los Módulos A/B/C siguen consumiendo el modelo agregado. La superficie por tipo queda disponible en `riesgo_predicho_por_tipo.parquet` y la comparación en `comparacion_modulo_a_por_tipo.json`. Pasar a producción exige antes una decisión que no es técnica: si se optimiza para un tipo, para una combinación ponderada por política, o se mantiene el agregado asumiendo la pérdida de ~10% en los tipos minoritarios.

## Auditoría técnica externa y remediación P0

Un panel externo (ver artefacto publicado en la conversación) revisó las 16 dimensiones del proyecto contra el estado del arte de crime analytics/urban computing/investigación operativa. Dos hallazgos se marcaron **P0** (antes que cualquier otra mejora) y ya se resolvieron:

### PAI/PEI (`train_baseline.py::pai_pei`) — métricas estándar de la literatura

Recall@K es una métrica ad-hoc; **PAI (Predictive Accuracy Index) y PEI (Predictive Efficiency Index)** (Chainey, Tompson & Uhlig 2008) son el estándar de hotspot policing, lo que hace el resultado comparable contra papers publicados y no solo contra el propio baseline. Sobre test 2025:

| k | PAI (veces mejor que azar) | PEI (vs. techo con hindsight) |
|---|---|---|
| 10% | 2.77 | 99.3% |
| 20% | 2.27 | 99.4% |
| 30% | 1.95 | 99.6% |

PAI ~2-2.8x es un resultado sólido y comparable con literatura de otras ciudades. **PEI ~99% es el hallazgo más fuerte**: el modelo está a centésimas del techo teórico (el mejor mapa de hotspots posible con hindsight total) a esta resolución — no es que el modelo sea débil, es que a grano hex×día×turno casi no queda margen de mejora sin cambiar la resolución o el enfoque de fondo (coherente con todo lo demás: la heterogeneidad espacial ya se captura casi al máximo posible).

### Validación espacial (`src/validation/spatial_holdout.py`)

El documento de arquitectura original pedía "dejar afuera un subconjunto de hexágonos completos" y nunca se había hecho — todo el testing anterior usaba split temporal, que solo prueba interpolación en el tiempo sobre hexágonos ya vistos. Se reentrenó excluyendo 80 de 401 hexágonos (20%) **completamente** de train/val, y se comparó el test 2025 separado en vistos vs. holdout:

| | MAE | PAI@20% | PEI@20% |
|---|---|---|---|
| Hexágonos vistos en entrenamiento (321) | 0.284 | 2.24 | 99.8% |
| **Hexágonos holdout, nunca vistos (80)** | 0.330 | 2.31 | 98.2% |

**Resultado contrario a lo previsto en la auditoría**: dado que `hex_id` domina la importancia de features, se esperaba una degradación fuerte en hexágonos nunca vistos (el modelo "no puede haber memorizado" una categoría que no existía en train). En cambio, PAI/PEI se mantienen prácticamente iguales — el MAE sí empeora (+16% relativo), pero el ranking de riesgo (lo que importa para priorizar) generaliza bien. Lectura: el modelo no depende de memorizar `hex_id` en sí, sino que apoya la predicción de un hexágono nuevo en `radio_censal_id`/`comuna_id` (unidades espaciales más gruesas, parcialmente representadas en train por hexágonos vecinos del mismo radio/comuna) y en las features socioeconómicas/de infraestructura — es decir, sí generaliza a partir de estructura, no solo de identidad. Buena noticia, y una corrección honesta a la hipótesis planteada en la auditoría: no toda crítica plausible se confirma con el dato.

### Auditoría de equidad (`src/validation/auditoria_equidad.py`)

Limitación documentada explícitamente: el modelo aprende de delitos **denunciados**, no de delito real — si el patrullaje histórico ya estuvo sesgado hacia ciertas zonas, el riesgo "aprendido" puede formalizar ese sesgo en vez de medir riesgo genuino (Lum & Isaac 2016; Ensign et al. 2018, *Runaway Feedback Loops in Predictive Policing*). Este proyecto no tiene forma de medir "delito real" independiente del registro policial — no se puede resolver el problema de fondo con los datos disponibles, pero sí se puede chequear una pregunta operacionalizable: ¿el riesgo predicho correlaciona con NBI/hacinamiento **más de lo que el historial delictivo por sí solo explica**?

Correlación simple (15 comunas) entre `score_riesgo` medio y variable socioeconómica, y correlación parcial controlando por historial delictivo de la comuna en train:

| Variable | r simple | r parcial (controlando historial) |
|---|---|---|
| % hogares con NBI | 0.409 | 0.141 |
| % hacinamiento crítico | 0.046 | -0.278 |

La correlación con NBI cae fuerte (0.41→0.14) al controlar por historial — la mayor parte de esa relación es indirecta (comunas con más NBI ya tenían más historial delictivo, no es que el modelo use NBI como proxy de clase social por sí solo). Hacinamiento hace lo contrario (sube en magnitud y cambia de signo) — señal a vigilar, aunque con **n=15 comunas la correlación parcial tiene muy pocos grados de libertad**, no alcanza para una conclusión fuerte en ningún sentido. Esto no es una auditoría de sesgo policial resuelta — es el chequeo honesto de qué tan independiente es el score de la vulnerabilidad socioeconómica, documentado para que quien use el sistema sepa qué mide y qué no mide.

## P1 de la auditoría técnica

### POIs sensibles + flujo peatonal (`src/etl/agregar_poi_y_flujo.py`)

Escuelas, hospitales, universidades y cajeros (buffer 300m del centroide, no "mismo hex" — evita subestimar en los bordes) y flujo EcoBici/Molinetes por hex×turno (a diferencia de cámaras/alumbrado, que son estáticos, el flujo peatonal sí depende del turno). Estaban calculados desde Capa 0 / Módulo B pero nunca llegaban al modelo núcleo — cerraban la mitad de Crime Pattern Theory (nodes/paths) ausente del feature set.

**Cuarta vez que se repite el mismo patrón**: reentrenado con estas 6 features nuevas, MAE/Recall@K/PAI/PEI quedan **idénticos** a la versión anterior (0.2902, 45.4%, PEI 99.3-99.6%). `flujo_molinetes` y `flujo_ecobici` sí entran con más importancia que la mayoría de las socioeconómicas (163 y 157 respectivamente, por encima de `poblacion_hex`, NBI, hacinamiento), pero no mueven el agregado. Con v2 (exógenas), los overlays de polígono, y ahora POIs+flujo, van cuatro rondas de "sumar más contexto estático no mejora el ranking" — el hallazgo ya no es una casualidad de una corrida, es la conclusión estructural del proyecto: a este grano, el modelo está saturado en lo que la heterogeneidad espacial pura puede explicar, y hace falta un cambio de enfoque (no otra feature) para mover la aguja — exactamente lo que señala la auditoría técnica en la sección de simulación/decision intelligence, no en features adicionales.

### Sobredispersión e incertidumbre (`train_incertidumbre.py`)

La auditoría midió sobredispersión real en `conteo_delitos` (varianza/media = 1,59; Poisson asume 1,0) y señaló que el modelo nunca cuantifica incertidumbre — emite un solo número puntual para un sistema que alimenta asignación de recursos públicos.

**Tweedie vs. Poisson**: MAE 0,2921 vs. 0,2902 (post-fix de turno; comparación original pre-fix, Poisson no se reentrena acá porque ya no es el objetivo de producción), PAI/PEI prácticamente iguales al Poisson de referencia (PAI 2,77/2,27/1,95, PEI 99,3-99,6%). Diferencia marginal en las métricas, pero es el objetivo estadísticamente correcto dado el `1,59` medido — **se adoptó como el objetivo de producción** en `train_baseline.py` (ver docstring del módulo), no por ganancia de métrica sino por corrección del supuesto de base.

**Regresión cuantílica (p10/p50/p90)**, misma tabla y split: cero *quantile crossing* (p10 nunca superó a p90, 0 de 585.460 filas), pero la cobertura empírica del intervalo [p10,p90] salió en **95,2%** (post-fix de turno; 95,1% antes) contra un objetivo nominal de ~80% — los tres modelos de cuantiles se entrenan de forma independiente, sin restricción conjunta, y eso los deja sobre-calibrados (intervalos más anchos de lo que deberían). Ancho medio 0,73 delitos esperados, algo más ancho en el cuartil de mayor riesgo predicho (0,88) que en los cuartiles medios — sensato, aunque no estrictamente monótono. La corrección real que señalaba la auditoría (**conformal prediction**) se implementó después — ver sección siguiente — y el resultado es otro hallazgo negativo honesto, no una solución.

Modelos guardados: `modelo_nucleo_tweedie.txt` (el mismo que ahora es `modelo_nucleo_v1.txt` de producción), `modelo_nucleo_p10.txt`, `modelo_nucleo_p50.txt`, `modelo_nucleo_p90.txt` — los cuantiles quedan disponibles para optimización robusta en Módulo A (siguiente P1), no se usan todavía en `predecir_riesgo.py`.

`riesgo_predicho.parquet` ya se regeneró con el modelo Tweedie de producción (números marginalmente distintos a Poisson, la diferencia es mínima).

### Conformal prediction (`src/model_core/conformal_prediction.py`) — P2/P3 de la auditoría

Implementa Conformalized Quantile Regression (CQR, Romano, Patterson & Candès 2019) para corregir la sobre-calibración de p10/p90 documentada arriba: calibrar la corrección sobre val (2024, nunca visto por p10/p90 salvo en early stopping) y aplicarla sobre test (2025). Dos variantes:

- **Simétrico**: una sola corrección `Q` aplicada a ambos lados, `[p10-Q, p90+Q]`.
- **Asimétrico**: `Q_lo`/`Q_hi` calibrados por separado, cada uno con su propio presupuesto de error (alpha/2), para que el lado que realmente tiene margen (arriba) se pueda corregir sin que el de abajo (que no tiene margen) lo bloquee.

**Resultado: `Q = Q_lo = Q_hi = 0,0000` en ambas variantes — CQR no corrige nada acá, y no es un bug.** `conteo_delitos` es 80,5% cero, y el modelo p10 converge en **1 sola iteración** de boosting (el verdadero percentil 10 de una distribución 80%+ cero es cero en casi cualquier hex×turno — no hay nada más que aprender ahí). Eso hace que el score de no-conformidad tenga una masa densa pegada a cero: sobre val, **58,5% de los scores del lado superior están por debajo de -0,01 (p90 sobra) y otro 36,4% empata dentro de ±0,01 de cero** — solo 5,1% de los casos realmente exceden p90. El nivel de cuantil que pide un intervalo de 80-90% cae *adentro* de ese bloque plano de empates (que va de ~58,5% a ~95% de la distribución acumulada), así que cualquier corrección calculada ahí devuelve 0 — no hay valor intermedio entre "no corregir" y "meterse en la cola negativa real" (percentil 50 de los scores: -0,63) sin cruzar todo ese bloque de empates. La garantía de CQR es de cobertura *mínima* (≥1-alpha), no de eficiencia: si el intervalo crudo ya cubre de sobra y el score tiene un atomo de empates justo en el borde, no hay corrección aditiva de un solo paso que lo angoste sin romper la garantía.

**Lectura honesta**: la sobre-calibración medida (95,2% vs. 80% nominal) es real, pero no es el tipo de problema que un shift aditivo (CQR estándar) puede arreglar en datos tan sesgados a cero — haría falta o (a) resignarse a un target de cobertura mucho más laxo (~60% de un solo lado, ya no vendible como "intervalo del 80%"), o (b) atacar el problema en el objetivo cuantílico mismo (ej. una distribución cero-inflada explícita en vez de pinball loss por cuantil independiente), no en un post-proceso. Documentado como límite real de método aplicado a este dominio, no como corrección pendiente de implementar — ya se implementó, y el hallazgo es que no hay nada que corregir con esta herramienta a este nivel de confianza.

Nota de infraestructura: entrenar los 2-3 modelos cuantílicos sobre las 4,69M filas de train mató el proceso por memoria más de una vez en esta máquina de 3,4GB — dos causas nuevas, además del downcast de `agregar_exogenas.py`: (1) LightGBM convierte categorías a códigos y sube a float64 cualquier columna categórica con al menos un valor faltante (`radio_censal_id` tiene 73.060 NaN) vía `Series.replace({-1: np.nan})`, y como `np.result_type()` combina TODAS las columnas del array final, ese único float64 arrastra a las 27 columnas juntas — se soluciona rellenando esos NaN con una categoría explícita antes de entrenar; (2) las columnas `int64` (conteos de POIs) hacen lo mismo (`np.result_type(int64, float32) = float64`) — se soluciona con downcast a enteros más chicos. Con ambos fixes, y reusando los modelos ya entrenados en vez de reentrenar en cada corrida (verificado: un `Booster` recargado de disco predice idéntico, diff 0.0, al modelo recién entrenado en el mismo proceso), el script corre estable. Al instrumentarlo con MLflow apareció una tercera causa, la del propio *loader* — ver "P2: MLflow" más abajo.

### Grafo vial real (`src/etl/build_grafo_vial.py`) — Módulo A y C

La auditoría señaló dos debilidades con la misma causa: Módulo A medía cobertura en línea recta sobre CRS métrico, Módulo C aproximaba el corredor de cada acceso con un buffer de radio fijo — ninguno de los dos usaba topología vial real. Se descargó el grafo vial real de CABA vía OSM/osmnx (**17.811 nodos, 37.036 tramos dirigidos** — dirigido, respeta sentido único nativamente, sin tener que leer `sentido` de `calles.parquet` a mano) y se cachea en `data/features/grafo_vial.graphml`.

**Módulo A, resultado grande**: cobertura por distancia de red real (Dijkstra de una sola fuente con corte, no línea recta):

| | Euclidiana (anterior) | Red real (actual) |
|---|---|---|
| Actual (75 comisarías) | 61.5% | **35.0%** |
| Optimizado, K=40 | 62.1% | **41.5%** |
| Ganancia | +0.6pp | **+6.5pp** |

Solo el 0,5% de los 190.876 pares (hexágono, candidato) cambia de estado individualmente al pasar de línea recta a calle real — pero alcanza para tumbar la cobertura agregada en más de 20 puntos, porque muchos hexágonos dependían de un único candidato "borderline" cuya distancia real supera los 800m aunque la línea recta no. **La cifra de cobertura actual de la sección de Módulo A más arriba (61,5%) estaba sobreestimada** — la real, con calles de verdad, es 35%. La ganancia relativa de optimizar (+6,5pp en vez de +0,6pp) es ahora más convincente, no menos: hay más margen real para mejorar del que el número euclidiano sugería.

**Módulo C**: el ranking de accesos cambia de forma no trivial al reemplazar el buffer por recorrido real del subgrafo de vías importantes (motorway/trunk/primary/secondary de OSM, análogo a troncal/distribuidora de GCBA). Alberti y Pórtico Independencia se mantienen 1° y 2° en ambas versiones (señal de robustez en los extremos), pero Dellepiane sube del puesto 7-8 al 3-4, Sarmiento sube del último puesto al 5°, y el grupo Illia baja del 3°-5° al 7°-9° — el buffer circular anterior sobre-representaba corredores que en la realidad no son alcanzables por vía importante en 2km reales, y sub-representaba otros conectados por una ruta más indirecta pero real.

Dashboard regenerado y redesplegado con estos números (auto-deploy vía GitHub — el push disparó el build solo, 15s, sin intervención manual).

## Motor de escenarios (`src/scenarios/motor_escenarios.py`)

Último ítem de P1 y la brecha más grande contra la visión del producto (auditoría, sección 8): el brief pedía responder "¿qué recursos deberían moverse?", "¿cuál sería el impacto?" y "¿qué pasaría si cambian las condiciones?" de forma interactiva — antes de esto, cada pregunta era editar una constante a mano en un script y volver a correrlo. No es un gemelo digital con simulación de agentes (fuera de alcance real para una persona en esta máquina) — es la ruta pragmática que señaló la auditoría: reutilizar Capa 1 + Módulo A detrás de una función de escenarios en vez de investigación nueva.

Dos tipos de escenario, porque responden preguntas distintas:

**Escenario de condiciones** (perturbar features estáticas de hexágonos puntuales, re-predecir con el modelo ya entrenado, sin reentrenar). Probado triplicando `n_luminarias` en los 5 hexágonos de mayor riesgo del turno Tarde:

```
Riesgo total ciudad: 157.71 -> 157.71 (+0.00%)
```

**Delta exactamente cero** en los 5 hexágonos. No es un bug del motor — es la confirmación, ahora en términos de "palanca de política concreta" en vez de importancia de feature abstracta, de algo que este proyecto viene midiendo desde v2: el modelo nunca aprendió sensibilidad real a `n_luminarias` (importancia de splits: 1, la más baja de toda la tabla — ver sección de Capa 1). El motor de escenarios funciona correctamente; lo que expone es un límite real del modelo, no un límite del motor.

**Escenario de recursos** (cambiar K_PATRULLAS o el radio de cobertura, re-resolver el MCLP de Módulo A sobre el mismo riesgo, comparar contra la cobertura actual). Curva completa, turno Tarde, radio 800m real:

| K patrullas | Cobertura | vs. actual (35,0%) |
|---|---|---|
| 20 | 26.7% | -8.3pp |
| 40 | 41.5% | +6.5pp |
| 60 | 52.2% | +17.2pp |

A diferencia de las condiciones estáticas, **esto sí responde con una señal clara y útil** — reasignar recursos (dónde están las patrullas) mueve la cobertura mucho más que cualquier intervención de infraestructura que el modelo haya aprendido a valorar. Es, en sí mismo, un hallazgo de producto: el apalancamiento real de este sistema está en la asignación de recursos (Módulo A/B), no en recomendar mejoras de infraestructura basadas en el modelo núcleo tal como está entrenado hoy.

**Limitación explícita, no resuelta**: el motor no responde "¿cómo evolucionará en las próximas horas?" — el modelo predice un patrón histórico promedio (2025), no una proyección desde "ahora"; eso requeriría infraestructura de forecasting en tiempo real (ingesta continua, ventana móvil), fuera de alcance de este P1.

## P2: tests de propiedad (`tests/`) — encontraron un bug real

Primer ítem de P2 (auditoría, sección 11): 18 tests con `pytest`, corren sobre los parquet ya generados (invariantes, no recomputan geopandas) más tests puros de lógica (`turno_desde_hora`, `pai_pei`). El test que la auditoría pidió textualmente — *"la suma de población por hex dentro de un barrio debe igualar la población del barrio"* — ya pasa (regresión del bug de `overlay_poligonos.py` ya corregido).

**Los tests de `turno_desde_hora` encontraron un bug nuevo, real, no relacionado con lo que motivó escribirlos**: `hex_utils.py` usaba `pd.cut(..., right=True)` (el default), que deja cada límite exacto de turno en el bucket ANTERIOR — hora 6 caía en "Madrugada" en vez de "Mañana", hora 14 en "Mañana" en vez de "Tarde", hora 22 en "Tarde" en vez de "Noche". Se corrigió con `right=False`.

**Impacto real medido**: `delitos.parquet` tiene franja en {6, 14, 22} en **167.901 de 1.353.136 filas (12,4%)** — todas mal clasificadas de turno hasta ahora. Esto es anterior a P0/P1, viene desde Capa 0 (`assign_hex_puntual.py`) y se propaga a `training_table.parquet`, el modelo, y `riesgo_predicho.parquet` por turno.

**Recascade completo ejecutado** (`assign_hex_puntual.py` → `agregar_poi_y_flujo.py` → `build_training_table.py` → reentrenar → `predecir_riesgo.py` → Módulo A/B/C → export dashboard → redeploy automático vía GitHub). El impacto agregado terminó siendo chico — consistente con todo lo demás en este proyecto, donde la heterogeneidad espacial domina por sobre el resto:

| | Antes del fix | Después |
|---|---|---|
| MAE modelo | 0.2900 | 0.2923 |
| Recall@30% | 58.6% | 58.6% |
| PEI@20% | 99.6% | 99.7% |
| Módulo A, actual (75 comisarías) | 35.0% | 35.1% |
| Módulo A, K=40 optimizado | 41.5% | 41.8% |
| Módulo B, cobertura | 24.9% | 25.0% |
| Módulo C, ranking de accesos | — | idéntico en orden |

**Nota de honestidad**: al momento del recascade, los cinco scripts de diagnóstico que no forman parte de la cadena de producción (`train_v2.py`, `train_semanal.py`, `train_incertidumbre.py`, `spatial_holdout.py`, `auditoria_equidad.py`) no se habían re-corrido con los datos corregidos. Después se re-corrieron **los cinco** con los datos post-fix, y todas las conclusiones cualitativas se sostuvieron con números casi idénticos:
- Tweedie ≈ Poisson: MAE 0,2921.
- El modelo generaliza a hexágonos nuevos: PAI@20 holdout 2,31 vs. visto 2,24.
- NBI mayormente explicado por historial: r 0,41→0,14 al controlar.
- Exógenas (v2) no mueven el Recall@K: MAE 0,2921 idéntico a v1, Recall@20/30 45,5%/58,6%, `evento_en_hex`/`evento_en_barrio` con importancia 0.
- Grano semanal solo afina levemente: modelo 0,9255 vs. naive 0,9518 (mejora relativa 2,76%), Recall@K prácticamente igual al diario (45,5%/58,6%).

No quedó ningún número de diagnóstico desactualizado: el impacto agregado del fix fue chico (tabla de arriba) y ninguna conclusión dependía de los decimales.

## P2: MLflow (`train_baseline.py`, `train_v2.py`, `train_semanal.py`, `train_incertidumbre.py`)

Segundo ítem de P2 (auditoría, sección 10): cada corrida de entrenamiento ahora se registra en MLflow local (`mlflow.db`, backend SQLite — "cero infraestructura nueva" como pedía la auditoría, un solo archivo, sin server). `metricas()`, `recall_at_k()` y `reportar_pai_pei()` en `train_baseline.py` ahora devuelven valores además de imprimir, así se pueden loguear sin recalcular. `mlflow ui --backend-store-uri sqlite:///mlflow.db` levanta el dashboard de comparación de corridas.

Verificado funcionando de punta a punta en `train_baseline.py` (el modelo de producción — params, métricas modelo/naive, y el `.txt` del modelo como artifact, todo quedó en la corrida `v1-tweedie`).

**Límite real encontrado, resuelto en sesión nueva**: al intentar refrescar `train_v2.py`/`train_semanal.py` con los datos post-fix de turno, `agregar_exogenas.py` tiró `numpy._core._exceptions._ArrayMemoryError` reconstruyendo `training_table_v2.parquet` — la máquina de 3,4GB de RAM se quedó sin memoria real después de una sesión larga con muchos procesos pesados encadenados (la restricción que la auditoría técnica nombra en su sección 13). No era un bug de código, sino que `training_table.parquet` (5,86M filas) pesaba 1,28GB en memoria antes de mergear nada, sobre todo porque `hex_id` (401 valores únicos) y `turno` (4 valores) quedaban como string en vez de categoría. Se agregó `optimizar_dtypes()` a `agregar_exogenas.py` (category para hex_id/turno, float32 en vez de float64, downcast de enteros) — baja la tabla a 504MB antes del merge, y con eso la reconstrucción corrió sin problema en una sesión nueva.

`training_table_v2.parquet` y `training_table_semanal.parquet` ya están reconstruidas con datos post-fix de turno, y `train_v2.py`/`train_semanal.py` corrieron de punta a punta (corridas `v2-exogenas` y `semanal` en MLflow). Resultado: **v2 (con exógenas) MAE=0,2921** vs. v1 MAE=0,2923 — clima/eventos/estadios no mueven la aguja, consistente con que la heterogeneidad espacial domina (importancia de features: `hex_id` y `radio_censal_id` arriba de todo, `temp_media_c` recién en el puesto 9, `evento_en_hex`/`evento_en_barrio`/`cerca_estadio` en 0). **Semanal**: modelo MAE=0,9253 vs. baseline naive MAE=0,9518 — mejora consistente pero chica, confirma la hipótesis original de la auditoría más que refutarla: agregar por semana reduce dispersión pero no revela señal dinámica adicional que el grano diario ya no capturara.

`train_incertidumbre.py` fue el último script de entrenamiento que quedaba fuera de MLflow, y cerrarlo requirió resolver primero un OOM propio. Ahora deja la corrida `incertidumbre-tweedie-cuantiles` con params (`tweedie_variance_power`, `mejor_iteracion_tweedie=134`, tamaño de los splits) y métricas del Tweedie (MAE, RMSE, PAI/PEI a k=10/20/30%) más las tres métricas de incertidumbre que antes solo se imprimían: `quantile_crossing`, `cobertura_p10_p90` y `ancho_medio_intervalo`. Los números reproducen exactamente los ya documentados abajo (MAE 0,2921, PAI 2,77/2,27/1,95, PEI 99,3-99,6%, crossing 0, cobertura 95,2%, ancho medio 0,727) — la corrida confirma los resultados post-fix, no los mueve. Con esto las cuatro variantes del modelo núcleo (v1, v2, semanal, incertidumbre) son comparables en `mlflow ui` sin volver a leer prosa del README.

**El OOM y el loader columna por columna**: `train_baseline.cargar_splits()` lee el parquet entero a pandas con los dtypes del archivo (float64/int64/object: ~1,4GB para 5,86M × 29) y recién ahí achica. Ese pico ya no entra en esta máquina de 3,4GB cuando quedan <600MB libres — la corrida murió con `ArrayMemoryError` pidiendo **45MB** dentro de `achicar_floats()`, con la tabla cruda ya en memoria (dos corridas quedaron como FAILED en `mlflow.db`, sin un solo param logueado: morían antes de la primera línea). El arreglo es invertir el orden: `leer_columna_achicada()` lee **una columna por vez** con `pyarrow`, la achica en el momento y la parte en los tres splits antes de leer la siguiente. Las categóricas se codifican con `dictionary_encode()` de arrow en vez de leerlas a `object` y hacer `.astype("category")` en pandas — `hex_id` son 5,86M strings de 15 caracteres, que como array de objetos pesa ~350MB antes de que pandas pueda tocarlo, mientras que en arrow el diccionario se arma durante la lectura y a pandas llega directo como `Categorical` (401 categorías + códigos int16, ~12MB). El pico baja de la tabla cruda entera a (splits acumulados ~550MB) + (una columna, ~95MB). Detalle que importa: las categorías se arman sobre la columna **completa** y se cortan después — si cada split armara las suyas, LightGBM codificaría distinto train y test.

## Módulo A — Asignación de patrullas (`src/optimization/modulo_a_patrullas.py`)

Maximal Covering Location Problem resuelto con `pulp` (programación lineal entera, no ML) sobre `riesgo_predicho.parquet` (score de riesgo por hex×turno del modelo v1, generado por `predecir_riesgo.py`, promediado sobre 2025). Candidatos: las 75 comisarías reales + los 401 centroides de hexágonos. Radio de cobertura 800m. Restricción: ninguna comuna queda con cobertura cero.

Turno Tarde (el de mayor riesgo promedio). **Números por distancia de calle real** (Dijkstra sobre el grafo dirigido de OSM, P1 de la auditoría) — la versión euclidiana anterior sobreestimaba fuerte la cobertura (daba 61,5% para el escenario actual y 84,4% para K=75) porque 800m en línea recta son bastante más que 800m de calle en una ciudad con autopistas y sentidos únicos:

| Escenario | Riesgo cubierto |
|---|---|
| Actual — 75 comisarías reales, tal como están | 35.1% |
| Optimizado, K=20 patrullas | 27.0% |
| **Optimizado, K=30 patrullas** | **35.6%** |
| Optimizado, K=40 patrullas | 41.8% |
| Optimizado, K=60 patrullas | 52.4% |
| **Optimizado, K=75** (mismo presupuesto que hoy) | **58.7%** |
| Optimizado, K=110 patrullas | 70.8% |

Dos datos para el pitch, ambos sobre distancia de calle real:

- **Con 30 unidades bien ubicadas se cubre más riesgo (35,6%) que con las 75 comisarías actuales (35,1%)** — el 40% del despliegue, misma cobertura.
- **A igual presupuesto (75), solo cambiando dónde se ubican, la cobertura pasa de 35,1% a 58,7%**: 67% más riesgo cubierto sin sumar una sola unidad.

La lectura de fondo no cambió al pasar a distancia de red, solo se volvió más exigente: la infraestructura fija de comisarías no está donde el riesgo se concentra hoy.

**La caída es de la métrica, no de los datos** (medido con las dos matrices sobre la misma demanda y los mismos candidatos): escenario actual 61,7% euclidiano vs. 35,1% de red; K=75, 84,5% vs. 58,7%. Unos 26 puntos de sobreestimación en ambos, y reproduce casi exacto los 61,5%/84,4% que reportaba la tabla euclidiana anterior — o sea que el cambio de números es enteramente atribuible a medir por calle. Detalle contraintuitivo: solo el **0,48%** de los pares (demanda, candidato) cambia de estado (836 de 190.876, casi todos porque el euclidiano cubría de más). La matriz de cobertura es rala — cada hexágono está al alcance de pocos candidatos — así que perder esas 836 conexiones alcanza para descubrir muchos hexágonos.

**La restricción de equidad es dura, y se nota**: con K=5 el solver devuelve `Infeasible` — no existe forma de ubicar 5 patrullas que deje a las 15 comunas con al menos un hexágono cubierto. Por debajo de ~10 unidades el problema directamente no tiene solución. Es el comportamiento correcto: el modelo no puede "resolver" el trade-off entre eficiencia y cobertura territorial abandonando comunas enteras.

`K_PATRULLAS` y `TURNO` son parámetros al inicio del script (pensados como los sliders de un dashboard futuro). La curva completa de cobertura vs. K se puede regenerar reusando la matriz de cobertura una sola vez — lo caro es el Dijkstra desde los 476 candidatos (~6s), no resolver el MCLP (<1s por valor de K).

## Módulo B — Ubicación de cámaras nuevas (`src/optimization/modulo_b_camaras.py`)

Weighted Max Coverage resuelto greedy (no MILP — el documento pide un ranking por ganancia marginal, que es justo lo que da el algoritmo greedy clásico). Peso por hexágono = riesgo (promedio de turnos) × boost por baja densidad de alumbrado × boost por alto flujo peatonal (ecobici + molinetes, combinados por percentil porque las escalas no son comparables) × descuento si ya está cubierto por una cámara existente. Candidatos: hexágonos a más de 100m de una cámara actual (224 cámaras reales).

Con `N_CAMARAS_NUEVAS=30` y radio de cobertura 150m: las 30 zonas elegidas concentran el **25,0% del riesgo ponderado total**. Solo 18 de 401 hexágonos caían dentro del radio de una cámara existente antes de correr esto — la cobertura actual de cámaras es baja en términos relativos al área de la ciudad. Ninguna de las 30 zonas priorizadas tiene hoy una cámara a menos de 150m.

**Límite medido: a esta resolución el "max coverage" degenera en un ranking, y hay que decirlo así.** Los centroides de los hexágonos H3-8 están a **700m** unos de otros (mediana 701m), y el radio de cámara es de 150m — o sea que cada candidato cubre únicamente su propio hexágono y ningún otro: la matriz de cobertura es la identidad. Verificado barriendo el radio: 150m, 300m y 500m dan **0,00 vecinos cubiertos** además de sí mismo; recién a 800m aparecen 1,88. Consecuencias:

- El greedy corre bien pero no tiene nada que optimizar — la ganancia marginal de cada candidato es exactamente su propio peso, por eso el ranking sale monótonamente decreciente (2,283 · 2,117 · 2,023 …). Es equivalente a ordenar por peso y cortar en 30.
- El 25,0% **no es "riesgo cubierto por las cámaras"**: es la fracción del riesgo ponderado que vive en los 30 hexágonos más pesados. Distinto de lo que sugiere la palabra "cobertura".
- Medir los 150m por distancia de calle en vez de línea recta **no cambia absolutamente nada** (0,00% de pares distintos, 30 de 30 ubicaciones idénticas, mismo 25,01%) — justamente porque no se cubre nada más que el propio hexágono. Por eso Módulo B no se migró al grafo vial junto con A y C: no habría cambiado un solo número.

Lo que el módulo sí aporta, y no es trivial: la **ponderación** (riesgo × oscuridad × flujo peatonal, con descuento por cámara cercana) es una priorización legítima de zonas. Se reencuadra como eso — un ranking de zonas donde una cámara agrega más — y no como una optimización de cobertura. La ubicación puntual dentro de cada zona es una decisión de campo: el hexágono mide ~700m de centro a centro, mucho más que el alcance de una cámara. Hacerlo bien como problema de cobertura exigiría una grilla mucho más fina (H3-10, centroides a ~100m), pero el modelo de riesgo es H3-8 — habría que desagregar riesgo a una resolución que el modelo no tiene, o sea inventar detalle. Queda como límite conocido, no como bug pendiente.

## Módulo C — Controles de acceso (`src/optimization/modulo_c_controles.py`)

A diferencia de A y B, no trabaja sobre hexágonos sueltos sino sobre el grafo vial. El corredor de cada acceso se recorre con Dijkstra sobre el subgrafo de vías importantes de OSM (`motorway/trunk/primary/secondary`, 5.658 nodos de 17.811) con corte a `RADIO_CORREDOR_M=2000` — el corredor real por donde se circula, no un buffer circular. (La versión pre-P1 sí usaba un buffer de radio fijo, documentado entonces como simplificación por falta de topología navegable en `calles.parquet`; el grafo vial de OSM la volvió innecesaria.)

**Dos correcciones encontradas al preparar el material de presentación** — la tabla anterior de este README (11 accesos, Alberti con 9.164 siniestros) venía de la versión con buffer y además arrastraba los dos problemas:

1. **Accesos duplicados.** La fuente trae 11 accesos, pero `Illia`, `Pórtico Illia al Sur` (a **8 metros** del anterior) y `Pórtico Illia al Norte` (a ~130m) son el mismo intercambiador: caían en el mismo nodo del grafo, producían corredores idénticos (381 siniestros, 5 hexágonos, 33 nodos) y ocupaban **tres de los once puestos** del ranking, además de correr los percentiles de todos los demás. Se colapsan los accesos que comparten nodo de entrada → **9 corredores únicos**.
2. **Suma contra promedio.** La accidentalidad se sumaba sobre los hexágonos del corredor mientras el riesgo se promediaba. Como los corredores varían **7,3x en tamaño** (3 a 22 hexágonos, según cuánto propague el subgrafo desde cada acceso), la suma premiaba al corredor grande por ser grande. Ahora las dos componentes son intensivas: siniestros **por hexágono** contra riesgo promedio por hexágono. Como los H3 tienen área casi idéntica, "por hexágono" es "por unidad de área". El total crudo se conserva en `accidentalidad_corredor` para auditar.

Ranking corregido (9 corredores, percentil de siniestros/hex + percentil de riesgo del corredor):

| # | Acceso | Autopista | Siniestros/hex | Riesgo | Hex | Score |
|---|---|---|---|---|---|---|
| 1 | Alberti | AU 1 – 25 de Mayo | 423 | 0,574 | 4 | 1,00 |
| 2 | Pórtico Independencia | Au Paseo del Bajo | 228 | 0,356 | 22 | 0,89 |
| 3 | Dellepiane II | AU Dellepiane | 148 | 0,187 | 3 | 0,78 |
| 4 | Dellepiane I | AU Dellepiane | 98 | 0,181 | 5 | 0,56 |
| 5 | Avellaneda | AU6 – Perito Moreno | 123 | 0,131 | 3 | 0,50 |
| 6 | Sarmiento | AU Illia | 113 | 0,110 | 10 | 0,39 |
| 7 | Retiro II | AU Illia | 50 | 0,163 | 3 | 0,33 |
| 8 | Illia (3 accesos agrupados) | AU Illia / Paseo del Bajo | 76 | 0,134 | 5 | 0,33 |
| 9 | Salguero | AU Illia | 79 | 0,075 | 8 | 0,22 |

**La cabeza del ranking es robusta**: Alberti y Pórtico Independencia quedan 1º y 2º tanto con la suma cruda como con la normalización por hexágono — verificado corriendo las dos variantes. Lo que se reordena es el medio (Avellaneda sube del 9º al 5º, Salguero baja del 6º al 9º), justamente los corredores chicos que la suma penalizaba. Con 9 casos cada escalón de percentil vale 11 puntos, así que el orden del 3º al 9º no debería tomarse literal.

Límites que quedan abiertos: el tamaño del corredor depende en parte de cómo OSM clasificó cada tramo (Alberti alcanza 9 nodos, Pórtico Independencia 257 — casi 30x); y la accidentalidad cuenta *todos* los siniestros del hexágono, no sólo los ocurridos sobre la traza del corredor. Filtrar por vía es la mejora que más movería los números.

## Capa 3 — Validación y explicabilidad (`src/validation/`)

**SHAP** (`shap_explicabilidad.py`) matiza la lectura de Capa 1: la importancia por cantidad de *splits* de LightGBM decía que casi todo era `hex_id`. SHAP (que mide aporte real a la magnitud de la predicción, no cuántas veces se usa una feature) da otra foto:

| Feature | Aporte SHAP |
|---|---|
| roll_30d_sum (historial 30 días, mismo hex) | 30.1% |
| hex_id (ubicación) | 28.2% |
| vecino_k1_roll30 + vecino_k2_roll30 (contagio espacial) | 24.6% |
| turno + radio_censal_id + resto | ~17% |

Historial reciente + vecindad espacial suman **~55%**, más que la ubicación sola — la dinámica temporal sí aporta, solo que no se notaba contando splits. Explicaciones locales (top 5 hex×turno de mayor riesgo del test) siguen el mismo patrón: 50% del riesgo de cada predicción se explica por `roll_30d_sum`. (Recorrido con el modelo/tabla post-fix de turno — números casi idénticos a la corrida pre-fix, consistente con el impacto agregado chico que ya midió el recascade.)

**Backtesting narrado + evolución mensual + calibración** (`backtesting_narrado.py`), sobre test 2025:

- Junio 2025: 9.783 delitos reales vs. 10.042 predichos por el modelo (suma sobre todos los hex×turno) — muy cerca. El top 20% de hexágonos marcados como más riesgosos concentró el 46.2% de los delitos reales del mes.
- **Recall@20% estable los 12 meses**: entre 43.9% y 47.4%, media 45.8%, desvío de 1.2 puntos — no es una racha de un mes.
- **Calibración muy buena en los deciles que importan**: en el decil de mayor riesgo, predicho=0.805 vs. real=0.801 (0,6% de diferencia), y en los deciles 3 a 9 el error relativo nunca pasa de 2,6%. En los tres deciles más bajos el modelo **subestima** en términos relativos (decil 0: predicho 0.0065 vs. real 0.0098, un 33,5% abajo; decil 1: 16,9%; decil 2: 4,7%), aunque el error absoluto ahí es de 0,003-0,006 delitos por hex×turno — irrelevante para operaciones, porque son las celdas que ningún esquema de asignación va a priorizar. El score es confiable en términos absolutos donde se lo usa para decidir; en la cola de riesgo casi nulo, apenas conservador.

Esto es más vendible que el resultado de Capa 1 solo: aunque el modelo apenas le gana al baseline naive en MAE, **está bien calibrado y es estable en el tiempo** — dos propiedades necesarias para que un organismo de gobierno confíe en el score.

## Export + Dashboard (`src/export/`, `dashboard/`)

Última etapa del roadmap. `src/export/generar_export.py` convierte los parquet de Capa 0-3 en JSON/GeoJSON livianos (~290KB en total) en `dashboard/public/data/`: `hex_riesgo.geojson` (459 hexágonos con riesgo por turno), `modulo_a/b/c.json`, `comisarias.geojson`, `camaras.geojson`, `metricas.json`. El dashboard nunca lee los parquet directo — todo pasa por este export para no acoplar el frontend al esquema de Python.

`dashboard/` es un proyecto Next.js 16 + React 19 + TypeScript + Tailwind v4, en el mismo repo (no separado — ver decisión más arriba). Mapa con **MapLibre GL** (sin API key, basemap oscuro de CARTO) coloreado por una rampa secuencial azul validada con la skill de dataviz (cuantiles, no escala lineal — el riesgo está muy sesgado). Panel lateral con toggles de capas (Módulo A/B/C, comisarías/cámaras reales) y panel de métricas (calibración, evolución mensual, cobertura de Módulo A) con gráficos SVG hechos a mano siguiendo los mark specs de la skill (líneas finas, tooltips on-hover, un eje por gráfico).

**Gotchas de esta etapa**:
- MapLibre GL v6 cambió a exports nombrados únicamente (`import { Map, NavigationControl, Popup } from "maplibre-gl"`) — el patrón viejo `import maplibregl from "maplibre-gl"` con default export ya no existe.
- `create-next-app` no scaffoldea sobre un directorio con archivos (el `public/data/` ya generado por el export) — hubo que crear en un directorio temporal y mergear.
- No se pudo verificar visualmente con la herramienta de automatización de navegador (el Chrome que controla la extensión no llega a `localhost:3000` aunque el servidor responde bien por `curl`/PowerShell en esta misma máquina — aislamiento de red entre la extensión y este entorno). Se verificó con `npm run build` + `npm run lint` (ambos limpios) y **a ojo por el usuario en su propio navegador — confirmado, el mapa renderiza bien**.

Gotchas encontrados: `siniestros_hechos` guarda lat/lon como texto, no float (se castea en `hex_utils.asignar_hex_id`); `hora_siniestro` viene como "HH:MM:SS" mientras que `franja` de delitos ya es un número 0-23 (se resuelve en `hex_utils.turno_desde_hora`, detecta el formato).

### Overlay de polígono (`src/etl/overlay_poligonos.py`)

Cierra los 3 cruces de la tabla que no son point-in-hex: `espacios_verdes` (% de área verde por hex — overlay real, 372 de 401 hex tienen algo de verde, media 7,1%), `comisarias` (qué comisaría de patrullaje cubre la mayor parte de cada hex — por área de intersección, no por centroide; los 401 hex quedaron cubiertos) y **población por hex**, prorrateada por área dentro del barrio ya asignado (no hace falta overlay hex-contra-barrio real: como los hexágonos H3-8 tienen área casi idéntica entre sí, prorratear por área da resultados casi uniformes dentro de cada barrio — verificado, la suma total coincide exacto con `poblacion_barrio` real: 2.890.151).

**Bug real encontrado y corregido**: la primera versión calculaba el denominador de la proporción (`area_total_por_barrio`, vía `groupby().transform("sum")`) *antes* de un `.merge()`, y lo reusaba después. `merge()` devuelve un DataFrame con índice nuevo (0..n-1) que no respeta el orden de filas original — pandas alinea operaciones aritméticas por índice, no por posición, así que la división terminó emparejando cada hex con el denominador de OTRO hex, silenciosamente (sin error, sin warning). El síntoma: la población total sumaba 3.478.949 en vez de 2.890.151, un 20% de más, y decenas de miles de más/de menos por barrio sin patrón obvio. Se corrigió haciendo todo el cálculo — merge y transform — sobre el mismo dataframe sin cortes en el medio. Regla general: nunca guardar el resultado de un `groupby().transform()` para usarlo después de un `merge()`/`sort`/cualquier operación que pueda reindexar.
