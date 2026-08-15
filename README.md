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
- `notebooks/` — `01_eda_delitos.ipynb`, el análisis exploratorio con sus figuras ya ejecutadas
- `presentacion/` — las páginas que se publican (una por módulo + la del EDA) y los scripts que les generan las figuras. HTML autocontenido, sin una sola request externa: el visor corre bajo una CSP que bloquea cualquier host, así que mapas y gráficos se dibujan como SVG inline calculado desde los datos del repo. `paginas/` es la fuente con los marcadores vacíos, `build/` el resultado (no versionado, son ~1,5MB de SVG derivado por página) — ver `presentacion/README.md`
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

## EDA retroactivo (`src/validation/eda_delitos.py`)

Se hizo tarde y conviene decirlo: el proyecto entró directo a construir la grilla y entrenar. La calidad de datos se auditó a fondo, y hay estadística descriptiva desperdigada, pero siempre como justificación de una decisión ya tomada (82,8% de ceros → Tweedie). Nunca se miró el fenómeno por sí mismo. Cinco preguntas, y tres de las respuestas explican resultados que hasta ahora estaban solo observados.

**1. La pandemia no dejó cicatriz de nivel.** 2016-2019 promedia 145.556 delitos/año; 2022-2025, 144.163 (**−1,0%**). El pozo de 2020 (83.609, −42%) y 2021 (106.830, −25%) es profundo pero transitorio. No hay quiebre estructural que invalide entrenar con la serie completa.

**2. Todo el ciclo temporal está en el turno, y el turno ya es una dimensión de la grilla.** Índices sobre 2022-2025 (1,00 = promedio):

| Ciclo | Amplitud (max−min) | Detalle |
|---|---|---|
| **Turno** | **1,35** | Tarde 1,66 · Mañana 1,45 · Noche 0,59 · Madrugada 0,31 |
| Día de semana | 0,21 | viernes 1,07 · domingo 0,86 (el único día que se despega) |
| Mes | 0,13 | diciembre/marzo 1,06 · febrero 0,93 |

La Tarde tiene **5,4x** los delitos de la Madrugada, mientras que entre el mes más y el menos delictivo hay un 13%. Como el turno es una dimensión del grano, no algo que el modelo tenga que descubrir, **al calendario le queda casi nada por explicar**. Es la razón estructural de que `dia_semana` y `mes` aporten tan poco, y de que sumar clima no moviera nada.

**3. La mezcla de tipos cambió mucho, y el año de test es el más raro.** Hurto pasó del 29,9% del total en 2016 al 40,4% en 2024; Lesiones cayó de 11,7% a 4,9%. Pero lo fuerte está en 2025:

| Tipo | 2024 | 2025 | |
|---|---|---|---|
| Robo | 68.304 | 49.938 | **−26,9%** |
| Hurto | 62.655 | 49.507 | **−21,0%** |
| Vialidad | 9.597 | 11.346 | +18,2% |
| Lesiones | 7.614 | 10.134 | **+33,1%** |
| Amenazas | 6.681 | 9.418 | **+41,0%** |
| Homicidios | 78 | 78 | 0,0% |

No es una caída pareja: **los delitos contra la propiedad bajan ~25% y los interpersonales suben ~35%**, en un solo año. Si es un cambio real de patrón o un cambio de criterio de registro/clasificación no se puede determinar con estos datos, pero importa: **el año de test tiene una composición distinta a la de los años de train**, y Módulo A y B optimizan sobre superficies dominadas justamente por robo y hurto.

Y conecta con el hallazgo de la desagregación por tipo: **Hurto es el único tipo donde el modelo pierde contra el promedio histórico** (−2,0%) y a la vez es el 38-40% del agregado. El modelo agregado está cada vez más dominado por el tipo que mejor predice un mapa histórico — parte de por qué le gana tan poco al baseline.

**4. La concentración espacial es real, fuerte y estable — ahora medida.** Moran's I sobre la vecindad H3 de contigüidad (k=1), con test de permutación de 999 réplicas:

| | Valor |
|---|---|
| I promedio 2016-2025 | **+0,671** |
| Rango anual | +0,643 (2020) a +0,706 (2018) |
| Valor esperado bajo azar | −0,0025 |
| p-valor | <0,001 los diez años |

El proyecto entero se apoya en que el riesgo se concentra espacialmente y esto nunca se había medido con el estadístico que lo cuantifica. **I ≈ 0,67 es alto**, y llamativamente **no se movió durante la pandemia** (2020: +0,643): cayó el volumen a la mitad y la estructura espacial quedó intacta. Se calcula a mano en `morans_i()` en vez de traer pysal — son 401 hexágonos y no justifica la dependencia.

**5. El ranking espacial es casi perfectamente estable, y ese es el techo del proyecto.** Correlación de Spearman entre el ranking de hexágonos de cada año y el del siguiente:

| | Promedio | Mínimo |
|---|---|---|
| Spearman año contra año | **0,983** | 0,970 (2017→2018) |
| Solape del top-20% | **91,0%** | 87,8% (2016→2017) |

Incluso 2019→2020, con la cuarentena en el medio, da 0,989. **Esto explica el resultado central del proyecto.** Si el mapa de riesgo de un año predice el del siguiente con Spearman 0,98, entonces un promedio histórico ya es casi óptimo para rankear, y cualquier modelo solo puede ganar en los márgenes. El "el modelo apenas le gana al baseline" deja de ser un resultado decepcionante y pasa a ser el resultado *esperable*: no es que el modelo sea flojo, es que el problema de priorización espacial está casi saturado a esta resolución. Coincide con los PEI de 95-99,6% medidos por tipo.

**Moran's I local (LISA, Anselin 1995).** El I global dice que hay clusters pero no dónde. Descomponerlo por hexágono, con permutación condicional (se fija el valor del hexágono y se remuestrean sus vecinos), da sobre 2025: **58 hexágonos de núcleo caliente, 24 de zona fría, 2 islas frías y ninguna isla caliente**; los 317 restantes no se distinguen del azar. Dos lecturas operativas: el núcleo caliente es **contiguo**, no un archipiélago —que es lo que hace que asignar patrullas por cobertura de radio tenga sentido geométrico—, y **no hay puntos calientes aislados** que un esquema de cobertura por zonas se esté perdiendo.

Salidas en `data/features/eda/`. El notebook `notebooks/01_eda_delitos.ipynb` tiene las seis figuras ya ejecutadas; importa el cálculo pesado de `eda_delitos.py` en vez de duplicarlo, así no se desincroniza del script.

### ¿La ventaja del modelo es priorización o es nivel? (`src/validation/test_nivel_baseline.py`)

Sospecha razonable, y falsa. El modelo le gana al naive 2,0% en MAE pero solo 0,8 puntos en Recall@20%; como el Recall@K es invariante a la escala y el MAE no, la asimetría sugería que parte de la ventaja fuera "el modelo notó que el nivel bajó" y no mejor priorización. 2025 cerró 16% abajo de 2024, así que había de dónde agarrarse.

Se comparó el modelo contra cinco variantes del promedio histórico, todas evaluadas sobre 2025:

| Variante | MAE | Sesgo de nivel | Recall@20% |
|---|---|---|---|
| **Modelo** | **0,2923** | 0,997 | **45,5%** |
| naive_full (el actual) | 0,2983 | **1,026** | 44,7% |
| naive sin pandemia | 0,3075 | 1,121 | 44,8% |
| naive últimos 2 años | 0,3067 | 1,120 | 44,9% |
| naive último año | 0,3119 | 1,174 | 45,0% |
| naive recalibrado con 2024 | 0,3135 | 1,187 | 44,7% |

**El baseline actual casi no tiene sesgo de nivel (1,026)**, así que el 2% del modelo es ventaja real, no escala. La sospecha estaba mal.

Pero el motivo por el que estaba mal es lo interesante: el promedio de los 8 años de train da ~131.800 delitos/año y 2025 cerró en 128.429. **Las dos distorsiones se cancelan** — la pandemia tira el promedio histórico hacia abajo justo lo suficiente como para coincidir con un 2025 que también está por debajo del nivel reciente. Sacar los años de pandemia *empeora* el baseline (0,2983 → 0,3075), y recalibrarlo con 2024 —un año alto, justo antes de la caída— lo empeora todavía más.

Dos consecuencias prácticas. Primero, **la comparación del README no está inflada**: el baseline contra el que se mide todo resulta ser, para este año de test, el mejor de las cinco variantes. Segundo, **es frágil por casualidad**: si 2026 vuelve al nivel de ~150.000, `naive_full` va a subpredecir ~15% y el modelo va a parecer mucho mejor sin haber mejorado en nada. Al reentrenar hay que mirar esta tabla antes de leer el MAE.

Nota sobre un bug que no era: `leer_columna_achicada` codifica categorías con `dictionary_encode` de arrow, en orden de aparición, mientras que `train_baseline` usó `astype("category")`, que ordena. En `dia_semana` los dos órdenes difieren en el 100% de los códigos (la tabla arranca el 2016-01-01, viernes) y es la 6ª feature por ganancia. Resulta que el `.txt` del modelo guarda un bloque `pandas_categorical` y LightGBM realinea por **valor**, no por código: reordenar cambia todos los códigos y deja las predicciones bit a bit idénticas. Solo sería un problema pasándole un array de códigos crudo en vez de un DataFrame.

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

### El modelo como pronóstico: validación con origen deslizante (`backtest_pronostico.py`)

El proyecto se presenta como predictivo, pero hasta acá se evaluaba con un **split fijo** (train ≤2023, test 2025). Eso mide "qué tan bien describe el riesgo típico", no "qué tan bien anticipa la semana que viene" — son preguntas distintas y la segunda es la operativa.

**No hizo falta un modelo nuevo.** Todas las features dinámicas de la tabla semanal están shifteadas al menos una semana (`shift(1)` antes del rolling, `lag_1sem` incluido), así que para la fila de la semana *t* el modelo solo usa información hasta *t−1*: **no hay fuga temporal y ya era un pronóstico válido a un paso**. Lo que faltaba era el protocolo: entrenar hasta la semana *t*, predecir *t+1*, avanzar y reentrenar. 26 orígenes semanales, julio a diciembre de 2025.

**Las dos referencias**, una de ellas nunca antes medida en el proyecto:
- **Promedio histórico** por hex×turno — la de siempre. Mide si el modelo aporta sobre "este lugar es así".
- **Persistencia** (repetir lo observado la semana pasada) — la referencia dura en series de tiempo. Si el modelo no le gana, no hay señal dinámica aprovechable.

| Referencia | MAE | Recall@20% | Semanas que el modelo le gana |
|---|---|---|---|
| **Modelo** | **0,9195** | **46,4%** | — |
| Persistencia | 1,1677 | 43,8% | **26 de 26** |
| Promedio histórico | 0,9432 | 45,7% | 21 de 26 |

Modelo vs. persistencia: **+21,3%** de MAE. Modelo vs. histórico: **+2,5%** (mediana +2,2%, peor semana −1,4%, mejor +11,5%).

**1. Contra la persistencia gana cómodo, pero es una referencia débil acá.** 26 de 26 semanas. Con 43,8% de celdas hex×turno en cero a grano semanal, repetir la última observación es muy ruidoso: ganarle era esperable y no dice mucho.

**2. Contra el promedio histórico el margen es de 2,5% — el mismo orden que ya sabíamos.** El split fijo daba 2% en el agregado y 2,76% en el semanal. El origen deslizante, que era el protocolo correcto y el que faltaba, **confirma el patrón en vez de revelar señal escondida**. Y pierde en 5 de 26 semanas.

**3. En priorización espacial, empatan.** Recall@20% de 46,4% contra 45,7%: menos de un punto. Para la decisión que de verdad toman los módulos —qué hexágonos priorizar— el modelo y "este lugar es así" son equivalentes.

**Conclusión: hay señal dinámica aprovechable, pero es marginal y no cambia a quién se prioriza.** Es un resultado negativo útil: cierra la pregunta de si convenía seguir invirtiendo por el lado temporal. La concentración espacial sigue siendo lo que carga el peso del sistema, ahora medido con el protocolo correcto y contra la referencia más exigente.

**Error de lectura propio, vale documentarlo.** La prueba inicial con 3 orígenes daba +6,8% contra el histórico y se interpretó como que el pronóstico sí aportaba señal. Eran las tres últimas semanas de diciembre — justo donde el promedio histórico falla más: el 29/12 tuvo 900 delitos contra los ~2.400 habituales y el modelo le ganó 11,5%. **Extrapolar desde la ventana menos representativa del año invirtió la conclusión.** Con los 26 orígenes la mejora media cae a 2,4%. La lección: en series con estacionalidad fuerte, una prueba corta al final del año no es una muestra, es un caso especial.

Nota de configuración: el backtest corre con 200 árboles × 31 hojas en vez de los 500 × 63 de producción — son 26 reentrenamientos en una máquina de 3,4GB y la serialización con `hex_id` categórico (401 niveles) tiraba `MemoryError`. Se aplica igual en todos los orígenes, así que la comparación es consistente, y juega **en contra** del modelo: el +2,5% es un piso, no un techo.

Resultados por semana en `backtest_pronostico.parquet`; la corrida queda en MLflow como `backtest-pronostico-1sem`.

### Proceso auto-excitante: el near-repeat, probado (`hawkes_autoexcitante.py`)

La única familia de modelos que el proyecto nunca había tocado. Los catorce modelos entrenados son LightGBM — un solo algoritmo. La ausencia que pesaba no era "no probamos random forest", que daría lo mismo, sino los **procesos de punto auto-excitantes** (Hawkes/ETAS), canónicos en pronóstico de delito desde Mohler et al. 2011 y base de PredPol. La diferencia es conceptual: LightGBM ve lags y rollings y tiene que aprender la forma del efecto desde features elegidas a mano; un Hawkes **impone** la estructura de contagio y estima su decaimiento. Es la hipótesis near-repeat, y es la única que el modelo actual no puede representar.

Formulación en tiempo discreto sobre hexágono × día, con núcleo geométrico normalizado:

```
λ_i(t) = μ_i + θ0·A_i(t) + θ1·Σ_{anillo1} A_j(t) + θ2·Σ_{anillo2} A_j(t)
A_i(t) = φ·A_i(t-1) + (1-φ)·N_i(t-1),   φ = exp(-1/τ)
```

Como el peso temporal total por delito pasado es 1, θ_k se lee directo como "delitos hijos por delito, en cada hexágono a distancia k", y el cociente de ramificación **n = θ0 + 6·θ1 + 12·θ2** es la fracción atribuida a contagio. λ es lineal en (μ, θ) dado τ y la verosimilitud de Poisson es cóncava ahí, así que los 404 parámetros se ajustan por optimización convexa (L-BFGS-B con gradiente analítico); τ se recorre por grilla y se elige en validación.

**1. El decaimiento óptimo es de 60 días, y eso no es near-repeat.** La verosimilitud en validación mejora monótonamente de medio día hasta 60 y recién ahí da vuelta:

| τ | 0,5 d | 2 d | 7 d | 30 d | **60 d** | 90 d | 365 d |
|---|---|---|---|---|---|---|---|
| NLL(val) | 0,70813 | 0,70545 | 0,70017 | 0,69497 | **0,69480** | 0,69563 | 0,71076 |
| n | 0,355 | 0,511 | 0,658 | 0,741 | 0,688 | 0,626 | 0,135 |

τ=60 días es una constante de tiempo (semivida ≈ 42 días), un orden de magnitud más larga que el near-repeat de la literatura, que decae en días. **El término "auto-excitante" no está capturando contagio: está funcionando como un estimador adaptativo del nivel local**, un promedio móvil con otro nombre. Leer el n=0,688 como "el 69% de los delitos de CABA son contagio" sería exactamente el error que este barrido detecta.

**2. Pero sí hay señal near-repeat, y es espacial y corta.** La columna que lo delata es θ1, el derrame al anillo de vecinos inmediatos: vale 0,025 a medio día, **llega a 0,045 a los 5 días** y se apaga a exactamente 0 a partir de los 90. θ2 (segundo anillo) es 0 desde los 5 días. O sea: hay contagio al hexágono de al lado en la escala de días, no más lejos y no más tarde. Es la firma del near-repeat, medida por primera vez en estos datos.

**3. Separar contagio de deriva no mejora nada.** Con un término lento fijo de 180 días absorbiendo la deriva del nivel, el término rápido **no se apaga** (n_rápido=0,359 contra n_lento=0,315 con τ_rápido=1 día), o sea que la estructura de contagio es real y no un artefacto de la deriva. Pero el modelo de dos escalas ajusta **peor** en validación (0,69800) que una sola escala de 60 días (0,69480): los datos prefieren una única memoria intermedia antes que una descomposición en contagio + fondo.

**4. En test, no le gana a nada.** Todo sobre 2025, mismo grano, mismas celdas:

| Modelo | MAE | RMSE | Sesgo de nivel | Recall@20% | PEI@10% |
|---|---|---|---|---|---|
| Hawkes, 1 escala | 0,7346 | 1,0933 | 1,045 | **0,4552** | **0,9959** |
| Hawkes, 2 escalas | 0,7400 | 1,0944 | 1,055 | 0,4530 | 0,9935 |
| Hawkes, solo lento | 0,7422 | 1,1015 | 1,080 | 0,4526 | 0,9938 |
| Promedio histórico | 0,7359 | 1,1067 | 1,027 | 0,4467 | 0,9854 |
| **LightGBM (producción)** | **0,7200** | **1,0825** | 0,996 | 0,4547 | 0,9950 |

El Hawkes le gana al promedio histórico por 0,85 puntos de Recall@20% y **pierde contra LightGBM en MAE y RMSE**. En Recall@20% le saca 0,05 puntos, que es ruido. Los tres PEI están arriba de 0,985: todos contra el techo.

Vale reconocer lo que sí muestra la tabla: **404 parámetros y ninguna variable exógena empatan en ranking a un LightGBM con 27 features** (socioeconómicas, POIs, flujo peatonal, calendario, clima) y cientos de árboles. No es que el Hawkes sea malo — es que a esta resolución no queda nada que ganar, que es justo lo que había predicho el EDA con el Spearman de 0,983 entre años.

**Error propio, atrapado a tiempo.** La primera versión evaluaba el modelo "sin término rápido" poniendo θ_rápido=0 sobre el ajuste ya hecho, sin reajustar μ. Eso deja el fondo compensando una excitación que ya no está: el modelo subpredecía el nivel un 29% y, como a grano hexágono×día el 82% de las celdas es cero, **subpredecir baja el MAE**. Aparecía con MAE 0,7149 — el mejor de toda la tabla, mejor que LightGBM — mientras su RMSE era el peor de todos. Reajustando μ da 0,7422, el peor. Es la cuarta vez en el proyecto que una métrica mal leída dice lo contrario de lo que pasa, y la primera que se detecta antes de escribirla en el README: el chequeo que lo cazó fue mirar la columna `sesgo_nivel`, que estaba en 0,71.

Salida en `hawkes_resultados.parquet`.

### El quiebre de 2025, resuelto (`src/validation/quiebre_2025.py`)

El EDA dejó abierta la salvedad más incómoda del proyecto: en 2025 —el año de test— los delitos contra la propiedad caen ~25% y los interpersonales suben ~35%. Como los tres módulos de Capa 2 optimizan sobre superficies dominadas por robo y hurto, había que saber si el salto es del delito o del registro.

**Hay dos fenómenos distintos, no uno.** La forma en el tiempo los separa: se mira el cociente contra el mismo mes del año anterior, que es plano si hubo un escalón y tiene deriva si hubo tendencia.

| Tipo | Cociente medio 2025/2024 | Pendiente por mes | Control 2024/2023 | Forma |
|---|---|---|---|---|
| Robo | 0,73 | **−0,0012** | −0,0372 | escalón |
| Hurto | 0,79 | **−0,0023** | −0,0089 | escalón |
| Lesiones | 1,31 | **+0,0458** | +0,0017 | rampa |
| Amenazas | 1,40 | **+0,0501** | +0,0068 | rampa |
| Vialidad | 1,20 | −0,0198 | +0,0204 | caída progresiva |

Robo y hurto caen de golpe y se quedan ahí los doce meses, con una planitud que ni siquiera tienen los años normales (el control 2024/2023 deriva 30 veces más). Lesiones y amenazas hacen lo contrario: **suben en rampa monótona todo el año**, de 1,09 en enero a 1,69 en diciembre, sin nada parecido en el control.

**Cuatro firmas internas más, todas en la misma dirección:**

1. **Uniformidad espacial.** Las 15 comunas se mueven en la misma dirección, con dispersión de 2,6 a 3,2 veces el ruido de muestreo. Hay algo de textura geográfica, pero está dominado por un componente común a toda la ciudad.
2. **El hurto automotor no se movió: 0,976, contra 0,775 del hurto total.** Es el subtipo más resistente a un cambio de registro, porque la denuncia policial es requisito del seguro y se hace igual. Que sea justo el único que aguanta es difícil de explicar con una caída genuina del hurto.
3. **La composición interna del robo casi no cambió**: `uso_arma` va de 12,3% a 11,1%. No parece un cambio de definición.
4. **`uso_moto` sube de 8,4% a 11,2%.** Si el total de robos cae 27% y los robos en moto casi no bajan, la proporción tiene que subir — y sube exactamente lo que corresponde.

**Evidencia externa** (consultada el 2026-08-14). La caída del 27% es la **cifra oficial**: el GCBA presentó el Mapa del Delito 2025 con 50.069 robos contra 68.392, el nivel más bajo en 25 años sin contar la pandemia, y coincide con este parquet (−26,9%) — o sea que estos datos son los oficiales, no una versión parcial. Pero las [encuestas de victimización de la UTDT](https://www.iciudad.org.ar/12092-delitos-y-violencia-una-lectura-critica-de-los-datos-preliminares-de-seguridad-en-caba/) se mantienen estables en el mismo período (promedio 24,3% entre 2022 y 2025; 23% declara haber sufrido un delito entre enero de 2025 y enero de 2026), y son independientes del registro policial. El [informe nacional](https://www.infobae.com/sociedad/policiales/2026/02/24/bajaron-todos-los-delitos-en-caba-y-es-la-segunda-ciudad-con-menor-tasa-de-homicidios-en-america/) advierte que parte del movimiento se explica por "mejoras en los sistemas de registro" y pide cautela. También hay reportes de dificultades para radicar denuncias por problemas técnicos del sistema interno en algunas dependencias. El mismo análisis independiente señala que los robos en moto bajaron apenas 3% y los homicidios en ocasión de robo subieron 13% — dos cosas que no acompañan una caída general del 27%.

**Qué se puede afirmar y qué no.** No se puede probar desde estos datos que el cambio sea de registro, y la posición oficial es que la baja es real. Lo que sí está medido es que **las firmas internas no son las que produciría una caída puramente genuina**, y que ninguna fuente independiente del registro policial la acompaña. La lectura prudente es tratar el **nivel** de 2025 como no confiable.

**Y ahora lo que decide si hay que cambiar algo.** Los módulos no consumen el nivel de delito, consumen el **orden** de los hexágonos. Se reponderaron los tipos de 2025 para devolverles la mezcla de 2024 (pesos: robo ×1,151, hurto ×1,065, lesiones ×0,632, amenazas ×0,597, vialidad ×0,712) y se comparó el mapa resultante:

| Comparación | Spearman | Top-20% en común |
|---|---|---|
| 2024 contra 2025 crudo | 0,9747 | 90,0% |
| 2024 contra 2025 reponderado | 0,9744 | 91,2% |
| **2025 crudo contra reponderado** | **0,9989** | **98,8%** |

La última fila aísla el efecto del quiebre de composición del simple paso del tiempo. **El mapa no se mueve**: 0,9989 de correlación y 98,8% del top-20% idéntico. Los seis tipos tienen patrones espaciales muy correlacionados entre sí (Spearman 0,84 a 0,92, ya medido al desagregar), así que reponderarlos entre ellos no reordena nada.

**Consecuencia operativa, en tres líneas:**

- **Los módulos A, B y C no hay que rehacerlos.** Optimizan sobre el orden, y el orden aguanta.
- **Las métricas de ranking del modelo siguen siendo válidas** — Recall@K, PAI, PEI son invariantes a la escala y casi invariantes a esta reponderación.
- **Cualquier afirmación sobre niveles queda inhabilitada**: no se puede decir "el riesgo bajó 16%" ni proyectar delitos evitados contra la base de 2025. Y al reentrenar con 2026 hay que volver a mirar esto antes de leer el MAE.

Salidas en `quiebre_2025.parquet` y sus dos archivos hermanos.

### ¿El techo es del fenómeno o de la resolución? (`src/validation/escala_cuadra.py`)

El EDA midió que el ranking de hexágonos de 700m es casi inmóvil entre años (Spearman 0,983) y de ahí salió que el problema está saturado. Pero eso se midió a **una** resolución. La ley de concentración del delito (Weisburd 2015) dice que el delito se concentra en **segmentos de calle**, no en barrios, y que esas cuadras sí se prenden y apagan. Si valiera acá, la grilla de 700m estaría promediando dinámica real y el techo sería de la unidad de análisis, no del fenómeno. Es lo único que quedaba por probar del lado del modelado, y no es cambiar de algoritmo: es cambiar de unidad.

Se asignó cada uno de los 1.352.985 delitos georreferenciados a su tramo más cercano de los 37.036 del grafo de OSM (largo mediano 103 m, que es la cuadra porteña típica).

**1. La ley de Weisburd no replica en su forma fuerte.**

| Unidad | % de unidades que acumula el 50% | Top 1% de unidades | Top 5% | Sin ningún delito en 10 años |
|---|---|---|---|---|
| Cuadra | **12,0%** | 13,1% | 31,7% | 6,7% |
| Cuadra, sin puntos sospechosos | 13,9% | 9,1% | 26,9% | 6,7% |
| Hexágono (700m) | 18,8% | 5,9% | 19,7% | 0% |

Weisburd reporta alrededor del **5%** de segmentos para el 50% de los delitos en varias ciudades de Estados Unidos. Acá hace falta **12-14%**, dos a tres veces más. Y solo el 6,7% de las cuadras no tuvo ni un delito en diez años. **El delito en CABA es bastante más difuso de lo que predice el benchmark.** Bajar de escala concentra —12% contra 19% del hexágono— pero mucho menos de lo que la hipótesis anticipaba.

**2. Sí hay más dinámica real a escala de cuadra, y hace falta un control para verlo.** Comparar la estabilidad de cuadras contra la de hexágonos sin más sería una trampa: una cuadra tiene 3,65 delitos por año contra 273 de un hexágono, y con conteos así de chicos el ranking se desordena solo por ruido de muestreo. Por eso lo observado se compara contra una **nula de Poisson**: dos años simulados con la tasa de cada unidad fija, para medir cuánto Spearman destruye el azar por sí solo.

| Unidad | Spearman observado | Nula de Poisson | **Brecha** | Delitos/unidad/año |
|---|---|---|---|---|
| Cuadra | 0,6919 | 0,7531 | **0,0612** | 3,65 |
| Hexágono | 0,9839 | 0,9941 | **0,0102** | 272,8 |

La brecha es **seis veces mayor** a escala de cuadra. O sea que **el techo de 0,983 que midió el EDA era en parte un artefacto de la resolución**: a 700m casi todo el movimiento posible ya está promediado, y a escala de cuadra queda movimiento real por encima del ruido.

Pero hay que leer la magnitud con cuidado. De toda la inestabilidad observada a nivel cuadra (1 − 0,69 = 0,31), solo **0,061 —un quinto— es cambio real**; el resto es ruido de muestreo. Y el número está sesgado **a favor** de la hipótesis: asignar por cercanía reparte el error de geocodificación entre cuadras vecinas, y ese error actúa como ruido extra en los dos años, empujando el Spearman observado por debajo de la nula. **0,061 es una cota superior de la dinámica real**, no una estimación.

**3. Adentro de un hexágono caliente el delito no está concentrado.** Es la pregunta operativa, y la respuesta cierra el tema:

| En los 40 hexágonos más calientes | Mediana |
|---|---|
| Cuadras con al menos un delito | **96** |
| Delito en las 3 peores cuadras | 15,6% |
| Delito en las 5 peores cuadras | 22,2% |

La hipótesis era que dentro de una zona peligrosa habría dos o tres cuadras cargando todo. **No es así**: hay 96 cuadras con delito y las tres peores juntan el 15,6%. Está repartido.

**Veredicto: no vale la pena construirlo.** El hallazgo científico es real y corrige al EDA —parte del techo era de la resolución, no del fenómeno—, pero las tres piezas juntas dicen que no se puede capitalizar: la concentración es dos a tres veces menor que el benchmark que motivaba la idea, la dinámica extra es una cota superior de 0,061 sobre un piso de ruido enorme (3,65 delitos por cuadra y año), y adentro de las zonas calientes el delito está lo bastante repartido como para que **desplegar por zona siga siendo lo correcto** — que es exactamente lo que hace el Módulo A.

El resultado 3 es, de hecho, una **validación del Módulo A** que no teníamos: patrullar por radio de cobertura no está regando de más, porque no existe el puñado de cuadras que concentre el delito de la zona.

Salidas en `escala_cuadra.parquet` y sus dos archivos hermanos.

**Conclusión de la fase de modelado.** Con esto se cierra la pregunta abierta: se probaron gradient boosting agregado, desagregado por tipo, a grano semanal, con exógenas, como pronóstico con origen deslizante, y ahora un proceso auto-excitante. Ninguno le saca al promedio histórico más de unos pocos puntos de Recall. La razón está medida y es estructural, no algorítmica: el mapa de riesgo de un año predice el del siguiente con Spearman 0,983.

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

**Sensibilidad al radio de cobertura (`sensibilidad_radio_patrullas.py`) — el número aguanta, el plan no.** Los 800m salieron del documento de arquitectura, no de estos datos, y todo el titular del Módulo A se apoya en ellos. El precedente del Módulo C —donde barrer el buffer de 30m dio vuelta el primer puesto— obligaba a hacer la prueba equivalente. Barrido de 300 a 1500m, recalculando la matriz de cobertura en cada uno:

| Radio | Actual (75 comisarías) | Óptimo K=75 | Ganancia | Ganancia relativa | Cruce | Plan igual al de 800m |
|---|---|---|---|---|---|---|
| 300 m | 5,4% | 45,3% | +39,9 pp | +744% | K=15 | 53% |
| 500 m | 11,5% | 45,3% | +33,7 pp | +293% | K=20 | 53% |
| 650 m | 24,6% | 49,5% | +24,9 pp | +101% | K=30 | 68% |
| **800 m** | **35,1%** | **58,7%** | **+23,6 pp** | **+67%** | **K=30** | — |
| 1000 m | 53,7% | 83,1% | +29,4 pp | +55% | K=35 | 28% |
| 1200 m | 66,5% | 97,7% | +31,2 pp | +47% | K=30 | 19% |
| 1500 m | 79,1% | 100,0% | +20,9 pp | +26% | K=30 | 17% |

**1. La ganancia en puntos es robusta; la ganancia relativa no.** En puntos va de 20,9 a 39,9 sobre un rango de radio de 5x, y en la franja operativamente plausible (650-1200m) queda entre **23,6 y 31,2 puntos**. La relativa va de +26% a +744%, pero eso es un artefacto del denominador: la cobertura actual se derrumba a 5,4% con radio chico y el cociente explota sin que pase nada interesante.

Tiene una consecuencia sobre cómo se comunica el resultado. **El titular robusto es "+23,6 puntos de cobertura", no "67% más riesgo cubierto".** El segundo suena mejor y es el que estaba en el material de presentación, pero es el que depende del supuesto.

**2. El punto de cruce aguanta, y del lado conservador.** "Treinta patrullas rinden más que setenta y cinco comisarías" se sostiene con cualquier radio de 650m para arriba (K=30, salvo 35 a 1000m), y con radios más chicos es todavía mejor (K=15 a 20). Nunca hace falta más de 35.

**3. El plan sí se mueve, y bastante.** A 650m comparte el 68% de las ubicaciones con el plan de 800m; a 1000m, solo el **28%**. Los radios grandes hay que descartarlos del análisis —a 1200m la cobertura óptima ya es 97,7% y a 1500m es 100%, así que el problema se vuelve degenerado y hay muchos conjuntos de 75 que empatan—, pero **1000m todavía no satura (83,1%) y aun así comparte apenas el 28%**. Eso es informativo: mover el radio un 25% cambia cerca de tres cuartos de las ubicaciones propuestas.

**Lectura conjunta**: el tamaño de la oportunidad es sólido y no depende del parámetro; **las 75 ubicaciones concretas sí**. El mapa del Módulo A hay que leerlo como "el plan para un radio de 800m", no como "el plan". Antes de comprometer un despliegue, el radio efectivo es exactamente el tipo de dato que hay que pedirle a quien conoce la operación — y es lo que la página de presentación ya listaba como paso 2, ahora con una medición atrás.

Salida en `sensibilidad_radio_patrullas.json`.

`TURNO` es un parámetro al inicio del script y `K` se pasa por línea de comandos (`--k 75`), pensados como los sliders de un dashboard futuro. El plan de K=40 conserva el nombre de archivo histórico (`modulo_a_patrullas_Tarde.parquet`) porque es el que citan las tablas de arriba; cualquier otro K va a `modulo_a_patrullas_Tarde_k{K}.parquet` para que un escenario no pise al otro. La curva completa de cobertura vs. K se puede regenerar reusando la matriz de cobertura una sola vez — lo caro es el Dijkstra desde los 476 candidatos (~6s), no resolver el MCLP (<1s por valor de K).

## Módulo B — Ubicación de cámaras nuevas (`src/optimization/modulo_b_camaras.py`)

Weighted Max Coverage resuelto greedy (no MILP — el documento pide un ranking por ganancia marginal, que es justo lo que da el algoritmo greedy clásico). Peso por hexágono = riesgo (promedio de turnos) × boost por baja densidad de alumbrado × boost por alto flujo peatonal (ecobici + molinetes, combinados por percentil porque las escalas no son comparables) × descuento si ya está cubierto por una cámara existente. Candidatos: hexágonos a más de 100m de una cámara actual (224 cámaras reales).

Con `N_CAMARAS_NUEVAS=30` y radio de cobertura 150m: las 30 zonas elegidas concentran el **25,0% del riesgo ponderado total**. Solo 18 de 401 hexágonos caían dentro del radio de una cámara existente antes de correr esto — la cobertura actual de cámaras es baja en términos relativos al área de la ciudad. Ninguna de las 30 zonas priorizadas tiene hoy una cámara a menos de 150m.

**Límite medido: a esta resolución el "max coverage" degenera en un ranking, y hay que decirlo así.** Los centroides de los hexágonos H3-8 están a **700m** unos de otros (mediana 701m), y el radio de cámara es de 150m — o sea que cada candidato cubre únicamente su propio hexágono y ningún otro: la matriz de cobertura es la identidad. Verificado barriendo el radio: 150m, 300m y 500m dan **0,00 vecinos cubiertos** además de sí mismo; recién a 800m aparecen 1,88. Consecuencias:

- El greedy corre bien pero no tiene nada que optimizar — la ganancia marginal de cada candidato es exactamente su propio peso, por eso el ranking sale monótonamente decreciente (2,283 · 2,117 · 2,023 …). Es equivalente a ordenar por peso y cortar en 30.
- El 25,0% **no es "riesgo cubierto por las cámaras"**: es la fracción del riesgo ponderado que vive en los 30 hexágonos más pesados. Distinto de lo que sugiere la palabra "cobertura".
- Medir los 150m por distancia de calle en vez de línea recta **no cambia absolutamente nada** (0,00% de pares distintos, 30 de 30 ubicaciones idénticas, mismo 25,01%) — justamente porque no se cubre nada más que el propio hexágono. Por eso Módulo B no se migró al grafo vial junto con A y C: no habría cambiado un solo número.

Lo que el módulo sí aporta, y no es trivial: la **ponderación** (riesgo × oscuridad × flujo peatonal, con descuento por cámara cercana) es una priorización legítima de zonas. Se reencuadra como eso — un ranking de zonas donde una cámara agrega más — y no como una optimización de cobertura. La ubicación puntual dentro de cada zona es una decisión de campo: el hexágono mide ~700m de centro a centro, mucho más que el alcance de una cámara. Hacerlo bien como problema de cobertura exigiría una grilla mucho más fina (H3-10, centroides a ~100m), pero el modelo de riesgo es H3-8 — habría que desagregar riesgo a una resolución que el modelo no tiene, o sea inventar detalle. Queda como límite conocido, no como bug pendiente.

### Módulo B sobre la red vial (`modulo_b_camaras_red.py`) — el límite anterior, resuelto

El diagnóstico era que el problema mezclaba dos resoluciones: el riesgo se modela a H3-8 y la decisión se toma a escala de esquina. La salida **no** fue forzar el riesgo a una grilla más fina —eso sería inventar detalle que el modelo no tiene— sino **mantener el riesgo donde está y cambiar el universo de candidatos**. Mismo movimiento conceptual que en el Módulo C al pasar del hexágono a la traza, y por la misma razón: la infraestructura vial es la unidad natural, no el área.

| | Versión hexágonos | Versión red vial |
|---|---|---|
| Demanda | 401 centroides H3-8 | **37.036 tramos de calle**, pesados por largo × peso del hexágono |
| Candidatos | 401 centroides | **17.811 intersecciones** (donde se monta una cámara) |
| Cobertura | euclidiana desde el centroide | **≤150 m de distancia de calle** |
| Tramos que cubre un candidato | 1 (sólo el propio hexágono) | **mediana 18, máximo 93** |

**El número clave**: la mediana de tramo es **103 m** contra un radio de 150 m. A escala de tramo los 150 m sí discriminan entre vecinos, que es exactamente lo que la versión anterior no lograba — ahí los centroides estaban a 700 m y ningún candidato alcanzaba a otro.

**Resultado**: 30 cámaras cubren el **7,0% del riesgo ponderado** sobre **86,4 km** de calle. Son el 2,2% de los 3.927 km de la red capturando el 7,0% del riesgo — una concentración de **3,2x**. (No es comparable con el "25%" de la versión anterior: aquel era la fracción del peso que vive en 30 hexágonos de 0,74 km² cada uno, no cobertura.)

**Tres cosas que la formulación anterior no podía hacer, y ésta sí:**

1. **Poner más de una cámara en la misma zona.** Las 30 cámaras caen en 21 hexágonos distintos: siete zonas reciben dos o tres. Con un candidato por hexágono eso era estructuralmente imposible, y es una respuesta obvia cuando una zona concentra mucho riesgo sobre varias calles.
2. **Ganancia marginal de verdad marginal.** El 4º candidato cubre 80 tramos pero rinde menos que el 3º, que cubre 16, porque se solapa con lo ya cubierto. Antes la "ganancia" era el peso del hexágono y no había interacción posible entre candidatos.
3. **Ubicaciones accionables.** El resultado son intersecciones con coordenadas, no zonas de 700 m dentro de las cuales había que decidir a ojo.

Sólo **13 de las 30 ubicaciones** caen en hexágonos que la versión anterior también elegía: más de la mitad del plan cambia.

Se conserva del módulo original la **ponderación** —riesgo × boost por baja iluminación × boost por flujo peatonal, con descuento del 30% si ya hay cámara a menos de 150 m y exclusión de candidatos a menos de 100 m— porque era la parte defendible. Lo que se reemplazó es el problema de cobertura, que era la parte que no se sostenía.

`modulo_b_camaras.py` (versión hexágonos) se conserva para poder comparar; `modulo_b_camaras_red.py` es la que corresponde usar.

## Módulo C — Controles de acceso (`src/optimization/modulo_c_controles.py`)

A diferencia de A y B, no trabaja sobre hexágonos sueltos sino sobre el grafo vial. El corredor de cada acceso se recorre con Dijkstra sobre el subgrafo de vías importantes de OSM (`motorway/trunk/primary/secondary`, 5.658 nodos de 17.811) con corte a `RADIO_CORREDOR_M=2000` — el corredor real por donde se circula, no un buffer circular. (La versión pre-P1 sí usaba un buffer de radio fijo, documentado entonces como simplificación por falta de topología navegable en `calles.parquet`; el grafo vial de OSM la volvió innecesaria.)

**Dos correcciones encontradas al preparar el material de presentación** — la tabla anterior de este README (11 accesos, Alberti con 9.164 siniestros) venía de la versión con buffer y además arrastraba los dos problemas:

1. **Accesos duplicados.** La fuente trae 11 accesos, pero `Illia`, `Pórtico Illia al Sur` (a **8 metros** del anterior) y `Pórtico Illia al Norte` (a ~130m) son el mismo intercambiador: caían en el mismo nodo del grafo, producían corredores idénticos (381 siniestros, 5 hexágonos, 33 nodos) y ocupaban **tres de los once puestos** del ranking, además de correr los percentiles de todos los demás. Se colapsan los accesos que comparten nodo de entrada → **9 corredores únicos**.
2. **Suma contra promedio.** La accidentalidad se sumaba sobre los hexágonos del corredor mientras el riesgo se promediaba. Como los corredores varían **7,3x en tamaño** (3 a 22 hexágonos, según cuánto propague el subgrafo desde cada acceso), la suma premiaba al corredor grande por ser grande. Ahora las dos componentes son intensivas: siniestros **por hexágono** contra riesgo promedio por hexágono. Como los H3 tienen área casi idéntica, "por hexágono" es "por unidad de área". El total crudo se conserva en `accidentalidad_corredor` para auditar.

Ranking corregido (9 corredores, percentil de siniestros/hex + percentil de riesgo del corredor):

| # | Acceso | Autopista | Siniestros en traza | km | **Sin./km** | Riesgo | Score |
|---|---|---|---|---|---|---|---|
| 1 | Pórtico Independencia | Au Paseo del Bajo | 1.721 | 32,0 | **53,7** | 0,356 | 0,94 |
| 2 | Alberti | AU 1 – 25 de Mayo | 73 | 2,2 | 33,0 | 0,574 | 0,89 |
| 3 | Dellepiane II | AU Dellepiane | 44 | 2,0 | 22,1 | 0,187 | 0,67 |
| 4 | Dellepiane I | AU Dellepiane | 53 | 2,1 | 25,0 | 0,181 | 0,67 |
| 5 | Sarmiento | AU Illia | 519 | 15,7 | 33,2 | 0,110 | 0,56 |
| 6 | Retiro II | AU Illia | 55 | 5,2 | 10,6 | 0,163 | 0,33 |
| 7 | Avellaneda | AU6 – Perito Moreno | 39 | 2,2 | 17,9 | 0,131 | 0,33 |
| 8 | Illia (3 accesos agrupados) | AU Illia / Paseo del Bajo | 102 | 6,7 | 15,3 | 0,134 | 0,33 |
| 9 | Salguero | AU Illia | 266 | 13,7 | 19,4 | 0,075 | 0,28 |

**Tercera corrección: siniestros sobre la TRAZA, no sobre el hexágono.** Estaba anotado como el límite que más movería los números, y así fue. La accidentalidad contaba todos los siniestros de los hexágonos que toca el corredor — incluidos los de calles comunes sin relación con el acceso. Ahora se cuentan solo los que caen sobre la traza real del corredor (buffer de 30m sobre la geometría de los tramos, que cubre el ancho de calzada más el error de geocodificación) y se normalizan por **kilómetro de corredor**, que es la unidad natural del problema: un control se pone sobre una vía, no sobre un área.

Cuánto sobraba, medido: de lo que el conteo por hexágono le atribuía a cada corredor, **solo el 4% al 46% está realmente sobre la traza** (mediana 27%).

| Acceso | Siniestros del hexágono | Sobre la traza | % real |
|---|---|---|---|
| **Alberti** | 1.693 | 73 | **4,3%** |
| Dellepiane II | 443 | 44 | 9,9% |
| Avellaneda | 370 | 39 | 10,5% |
| Dellepiane I | 489 | 53 | 10,8% |
| Illia (3) | 381 | 102 | 26,8% |
| Pórtico Independencia | 5.020 | 1.721 | 34,3% |
| Retiro II | 150 | 55 | 36,7% |
| Salguero | 633 | 266 | 42,0% |
| Sarmiento | 1.130 | 519 | 45,9% |

**Y cambió el primer puesto.** Alberti era 1º con una accidentalidad que era **96% ruido**: 73 de sus 1.693 siniestros ocurrían sobre su corredor. Es un corredor corto (2,2 km) en pleno microcentro, así que sus hexágonos capturaban una enorme cantidad de choques de calles vecinas. Corregido, pasa a 2º y **Pórtico Independencia queda 1º** con 53,7 siniestros/km, la densidad más alta por lejos.

El sesgo tenía una dirección sistemática: castigaba a los corredores largos sobre autopista —donde la traza domina el hexágono— y premiaba a los cortos en zona densa. Es exactamente el error que un ranking de este tipo no puede permitirse, porque los accesos de autopista en el centro son justamente los cortos.

Nota sobre el medio de la tabla: Sarmiento tiene la segunda densidad más alta (33,2/km) pero queda 5º porque su riesgo delictivo es bajo (0,110) y el score promedia ambos percentiles. Con 9 casos cada escalón de percentil vale 11 puntos, así que el orden del 3º al 9º sigue sin poder tomarse literal.

Límite que queda abierto: el tamaño del corredor depende en parte de cómo OSM clasificó cada tramo (Alberti alcanza 2,2 km de traza, Pórtico Independencia 32 — casi 15x). Normalizar por km corrige el sesgo de tamaño en el puntaje, no la variabilidad de origen.

**Sensibilidad al ancho del buffer (`sensibilidad_buffer_traza.py`) — y el primer puesto no aguanta.** Contar los siniestros "del corredor" exige decidir a qué distancia de la calzada deja de contar uno. Los 30 m se eligieron por primeros principios (ancho de vía + error de geocodificación), pero es una elección, así que se recorrió de 10 a 75 m:

| Buffer | 1º | 2º | Siniestros en traza | Spearman vs. 30 m |
|---|---|---|---|---|
| 10 m | Pórtico Independencia | Alberti | 2.117 | 0,650 |
| 20 m | Pórtico Independencia | Alberti | 2.550 | 0,933 |
| **30 m** | **Pórtico Independencia** | Alberti | 2.872 | 1,000 |
| 40 m | **Alberti** | Pórtico Independencia | 3.111 | 0,967 |
| 50 m | **Alberti** | Pórtico Independencia | 3.387 | 0,967 |
| 75 m | **Alberti** | Pórtico Independencia | 3.762 | 0,883 |

**El par de los dos primeros es robusto — el orden entre ellos no.** Alberti y Pórtico Independencia son siempre los dos primeros, con cualquier buffer. Pero **quién queda 1º se da vuelta a los 40 m**: tres anchos dan uno y tres dan el otro. El medio de la tabla también se mueve (4 a 6 de 9 puestos cambian según el ancho).

El mecanismo es el mismo sesgo que se corrigió, reapareciendo: Alberti tiene una traza corta (2,2 km) en zona densa, así que **ensanchar el buffer le devuelve los choques de calles vecinas** y le infla la densidad rápido; Pórtico Independencia tiene 32 km y absorbe proporcionalmente menos. Los 30 m se sostienen justamente por ser lo bastante ajustados como para excluir la calle de al lado — pero conviene decir que el 1º contra el 2º depende de esa elección.

**Error propio en la métrica de control.** La primera versión comparaba los dos primeros como *conjunto* (`set`), así que informaba "top2 igual: sí" para los seis anchos y ocultaba que se dan vuelta entre sí. Se corrigió a comparación por orden. Segunda vez en el proyecto que una métrica de verificación mal elegida esconde justo lo que tenía que detectar — la primera fue ordenar los tipos de delito por "mejora" en vez de PEI.

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

Última etapa del roadmap. El dashboard nunca lee los parquet directo — todo pasa por un export para no acoplar el frontend al esquema de Python. Son dos scripts:

- `src/export/generar_export.py` — las salidas por hexágono y los puntos: `hex_riesgo.geojson` (401 hexágonos con riesgo por turno), `modulo_a_k75.json`, `modulo_b_red.json`, `modulo_c.json`, `comisarias.geojson`, `camaras.geojson`.
- `src/export/generar_export_dashboard.py` — las salidas por unidad administrativa, que son las que consume el tablero actual: `barrios_riesgo.geojson`, `comunas_resumen.json`, `curva_k.json`, `sensibilidad_radio.json`, `serie_delitos.json` y `resumen.json`.

De los dos, el tablero solo lee las salidas del segundo más los puntos y las capas de contexto del primero. `hex_riesgo.geojson` se sigue generando porque lo consume `presentacion/gen_mapas.py`.

Tres salidas se dejaron de exportar cuando se reescribió el tablero, porque ya no las lee nadie: `modulo_a.json` (el plan con K=40, reemplazado por el escenario K=75), `modulo_b.json` (la versión sobre hexágonos, reemplazada por la de red vial) y `metricas.json` (alimentaba los paneles de calibración y evolución del dashboard viejo). Los parquet de origen no se tocan; lo que se corta es la copia en `public/data/`, que se subía a producción sin que nada la pidiera. `metricas.json` además llevaba los números de v1/v2 y de cobertura de Módulo A hardcodeados — una segunda copia de las tablas de este README que había que actualizar a mano en los dos lados.

`dashboard/` es un proyecto Next.js 16 + React 19 + TypeScript + Tailwind v4, en el mismo repo (no separado — ver decisión más arriba).

**El primer dashboard se descartó y se reescribió entero.** Dibujaba los 401 hexágonos crudos, con un panel lateral de toggles y paneles de métricas por módulo. Funcionaba, pero nadie fuera del proyecto piensa en hexágonos: la unidad con la que se asignan recursos es el barrio y la comuna. La segunda versión agrega el riesgo a esas unidades y usa una sola selección (turno, **tipo de delito**, comuna, barrio) que filtra el tablero completo a la vez, en lugar de N paneles independientes.

### Filtro por tipo de delito

Pone en el tablero la superficie por tipo de `riesgo_predicho_por_tipo.parquet`, que hasta ahora solo existía como parquet y como la sección "Riesgo por tipo en los módulos" de este README. Al elegir un tipo cambian a la vez la coropleta, las barras por comuna, las dos columnas de la tabla, los KPI y la serie mensual.

Lo que hace no trivial la interfaz es que **la asimetría del análisis tiene que sobrevivir a la pantalla**. Hay seis tipos con delitos registrados y solo cuatro con superficie de riesgo propia, y ese recorte fue una decisión medida, no un olvido. El tablero la respeta en tres lugares:

- Los dos tipos sin superficie (Vialidad, Homicidios) van en un `optgroup` aparte y con el texto "(sin superficie)" en la opción. Al elegirlos, los delitos se filtran pero el mapa sigue dibujando el riesgo agregado y lo dice: el KPI de riesgo cambia la nota a "superficie agregada — Vialidad no tiene una propia" en ámbar, y bajo el mapa aparece el motivo del recorte.
- Con un tipo que **sí** tiene superficie y una capa operativa activa, aparece la advertencia inversa: el mapa muestra la superficie del tipo, pero las ubicaciones de los Módulos A/B/C se optimizan sobre el modelo agregado. Sin ese cartel, filtrar por hurto y ver las patrullas quietas se lee como "este es el plan óptimo para hurto", y las tablas de superposición de más arriba dicen que no: hurto y lesiones comparten apenas el 60% de las ubicaciones.
- El nivel de riesgo **no es comparable entre tipos** — cada superficie está normalizada por separado, así que la media de amenazas (0,014) y la de robo (0,086) no se pueden poner una al lado de la otra. Lo comparable es el ranking entre barrios. Eso va en la ayuda del KPI y no en las salvedades generales, porque es sobre ese número exacto donde se cometería el error.

El fallback al agregado vive en una sola función (`claveRiesgo` en `lib/types.ts`), no repartido por los componentes: si cada uno lo dedujera por su cuenta, alcanzaría con que uno se olvidara para que el mapa dibujara ceros y pareciera "sin riesgo".

### Indicadores para el que mira, no para el que modela

El tablero tenía un KPI que decía **"Riesgo medio por celda: 0,397"**. Es la salida del modelo, pero un 0,397 no se puede dimensionar sin conocer la escala, y encima cambia de escala con el filtro por tipo. Se reemplazó por **tasa cada 100.000 habitantes** (4.512 para toda la Ciudad), que es el estándar con el que se compara delito entre jurisdicciones y además corrige algo que el conteo crudo no: Palermo tiene 226.534 habitantes y Villa Real 5.500, así que un ranking por conteo mide sobre todo cuánta gente vive en cada barrio. La población sale del prorrateo por área de `overlay_poligonos.py` y suma exacto los 2.890.151 del padrón. La salvedad —que mide sobre población residente y por lo tanto sobreestima donde entra mucha gente que no vive ahí, como el microcentro— va en la ayuda del propio KPI.

El panel **"Cuándo ocurren"** (`components/Cuando.tsx`) traduce el volumen a frecuencia y agrega el perfil temporal, desde `perfil_temporal.json`:

- **Cascada de frecuencias**: "un delito cada 4 minutos", más el desglose por hora / día / semana / mes. La unidad del titular se elige sola, porque el rango es enorme: son 130.421 delitos al año (uno cada 4 minutos) pero 78 homicidios (uno cada 4,7 días), y fijar la unidad en minutos daría "cada 6.735 minutos", que no se dimensiona.
- **Perfil horario** con las bandas de turno de fondo, para no tener que contar posiciones y adivinar si el pico de las 18h cae en "tarde" o en "noche". Pico a las 18h, la tarde concentra el 42,6%.
- **Perfil por día de la semana**: viernes es el más cargado, 27,1% arriba del domingo. La escala no arranca en cero a propósito — las diferencias entre días son de ~10% y contra un eje en cero las siete barras se ven iguales.

Tres decisiones de honestidad en este panel:

- **La cascada sigue la selección territorial; los perfiles no.** La cascada es un total dividido por tiempo, así que se puede calcular para cualquier comuna o barrio. Los perfiles vienen agregados a nivel Ciudad. Van visualmente separados y el perfil dice "toda la Ciudad" en su propio encabezado incluso con un filtro puesto, para que nadie filtre por Balvanera, mire el pico de las 18h y crea que es el pico de Balvanera.
- **Con pocos casos no se afirma el patrón.** Debajo de 1.000 hechos en el año, el reparto por hora y por día es ruido: con homicidios el "día pico" cambia de año a año por azar. En ese caso el panel reemplaza la frase por la advertencia y deja solo la lectura por turno, que agrupa 6-8 horas y aguanta mucho mejor el poco volumen. El umbral es grosero a propósito: no pretende ser un test, solo evitar que el tablero anuncie "el sábado es 280% peor que el martes" como si fuera un hallazgo.
- **El delta y la chispa del KPI de delitos siguen al tipo pero no al territorio**, porque la serie mensual está agregada a nivel Ciudad y recortarla por barrio sería inventar el dato. Que sigan al tipo sí importa: con el filtro en lesiones o amenazas el delta es positivo mientras el total cae, que es justo lo que el quiebre de 2025 predice.

#### Población flotante: los molinetes no sirven de denominador, sí de marca

La tasa cada 100.000 divide por población **residente**, así que se infla donde entra mucha gente que no vive ahí. San Nicolás tiene 29.273 vecinos y la tasa más alta de la Ciudad (15.687). Se probó corregir el denominador con los molinetes del subte y **no se sostiene**:

- **Solo 23 de los 48 barrios tienen estación de subte.** Los 25 restantes concentran el 33,1% de los delitos y el 36% de la población, así que la corrección se aplicaría a media ciudad y no a la otra media, y las dos mitades dejarían de ser comparables — que es peor que no corregir.
- **Puerto Madero no tiene subte.** Es el caso de manual de población flotante (6.726 residentes, oficinas y turismo), y corrigiendo solo por molinetes pasaba a ser el barrio número uno del ranking: la corrección lo empeoraba en vez de arreglarlo.
- Con la corrección aplicada igual, el ranking casi no se movía (Spearman 0,9897 contra la tasa sin corregir). El efecto real era grande en un puñado de barrios —San Nicolás −37%, Constitución −26%, Monserrat −25%— y nulo en el resto.
- El factor de conversión de "entradas diarias" a "residentes equivalentes" es un parámetro inventado, sin nada en los datos que lo fije.

Lo que sí funciona es **no tocar el denominador y marcar dónde leerlo con pinzas**. EcoBici sí llega a los 48 barrios (570 estaciones contra 90 del subte), pero sus magnitudes no son sumables con las del subte (46M de viajes contra 2.730M de pasajeros), así que se combinan como percentiles —el mismo criterio que ya usaba `modulo_b_camaras.py` por la misma razón— relativizados por población. Correlaciona con la tasa a Spearman 0,333, o sea que agrega información en vez de repetirla.

En el tablero eso es un asterisco al lado de la tasa en la columna nueva "Cada 100k" de la tabla, para el quinto superior, y una nota en ámbar en el KPI cuando la selección cae ahí. **No corrige el número: avisa que ese número compara peor que los otros.**

#### Validación contra la ENMODO 2018 (`src/validation/validar_presion_visitantes.py`)

El índice de afluencia ve dos modos de transporte. La pregunta es si eso alcanza para ordenar la afluencia real, que incluye tren, colectivo, auto y a pie. La [Encuesta de Movilidad Domiciliaria 2018](https://data.buenosaires.gob.ar/dataset/encuesta-movilidad-domiciliaria) sirve de contraste independiente: encuesta domiciliaria multimodal del AMBA, 16.667 hogares y 59.452 viajes, con el destino de cada viaje georreferenciado a **radio censal** y código INDEC de comuna (`radio_destino`, `cod_partido_destino`, factor de expansión `PONDERA`). De esos viajes, 12.261 terminan en CABA, entre 554 y 1.478 por comuna.

Se compara el índice contra los viajes que llegan a cada comuna **desde otra jurisdicción**, por habitante — la definición operativa de "gente que no vive acá".

**Resultado: Spearman 0,729.** Dos fuentes independientes, con métodos y años distintos, ordenan casi igual. Coinciden en los extremos: ambas ponen la Comuna 1 primera, la 3 segunda y la 8 última.

**Y encontró un punto ciego que después se corrigió.** En la primera versión, con subte y EcoBici solamente, la Comuna 9 (Liniers, Mataderos, Parque Avellaneda) era **cuarta** para la encuesta y **decimocuarta** para el índice: diez puestos. La causa era transparente — Liniers es un nodo de tren y de colectivos de larga distancia, y no tiene subte.

#### Sumar el tren (`pipeline/ingest_trenes_boletos.py`)

Se agregó el modo que faltaba, con dos fuentes: los **boletos vendidos por estación** que publica la CNRT (ZIP con un XLSX por línea, 1994 al presente, actualización mensual) y las **estaciones de ferrocarril** de BA Data para geolocalizarlas. 41 estaciones en CABA, 107,2M de pasajeros en 2025, el 35,6% de la red del AMBA.

Dos trampas del cruce, ambas resueltas con alias explícitos sobre 43 nombres —una cantidad donde el fuzzy match es más riesgo que ayuda—:

- La CNRT usa el nombre oficial y BA Data el corto, o al revés: "Plaza Constitución" vs "Constitución", "Once" vs "Estación Once". Sin los alias se perdían **las dos terminales más grandes de la Ciudad**, 37,0M y 15,3M de pasajeros, el 44% del total de CABA.
- **Retiro son tres terminales** en el GeoJSON (Mitre, San Martín y Belgrano Norte comparten predio y nombre) y tres entradas en la CNRT ("Retiro", "Retiro Ramal Tigre", "Retiro Ramal Suárez/Mitre"). Sin tratarlo, cada fila del GeoJSON se llevaba el total de "Retiro" y el barrio quedaba con 26,4M en vez de los 15,4M reales: 71% de más.

El tren se lee aparte y **no** entra en `hex_flujo_turno.parquet`, que es lo que alimenta el feature set del modelo — sumarlo ahí obligaría a reentrenar, y esto es un indicador del tablero, no una variable del modelo.

**Resultado, medido con el mismo script:** Spearman **0,729 → 0,768**, y Liniers pasa de percentil 0,12 a 0,83, o sea entra al quinto que se marca. La Comuna 9 sube del puesto 14 al 12.

**Lo que queda sin cubrir es el colectivo**, del que no hay pasajeros por parada publicados. Mataderos es el caso: 0,02 de percentil, sin estación de tren ni de subte, pero con afluencia real. Por eso **la falta de asterisco no garantiza que la tasa esté bien**, y eso está dicho en la ayuda del KPI del tablero, no solo acá.

El resultado ordena así: arriba Constitución (1,00), San Nicolás (0,98), Chacarita (0,96), Monserrat (0,94), Retiro (0,92), **Puerto Madero (0,90, sin subte ni tren, capturado por EcoBici)** y Liniers (0,83); abajo Mataderos (0,02), Villa Lugano y Versalles.

**Por qué ENMODO no se usa para corregir el denominador, aunque sea la fuente conceptualmente correcta.** Está vencida, y el desfasaje tiene justo el patrón espacial que arruinaría la corrección. Medido con los molinetes del propio pipeline, que llegan a 2025:

| | 2018 → 2025 |
|---|---|
| Subte, total | −35,3% |
| Microcentro (agregado) | −40,2% |
| San Nicolás | −49,0% |
| Resto de los barrios | −31,1% |
| Nueva Pompeya | −1,0% |

San Nicolás perdió la mitad de su tráfico de subte y Nueva Pompeya el 1%. Un denominador de 2018 aplicado a delitos de 2025 sobrecorregiría exactamente los barrios que la marca quiere señalar, y el error tendría el mismo patrón espacial que el problema que viene a arreglar. Es coherente con lo documentado para el microcentro post-pandemia: teletrabajo del 35% al 70% según rubro, y 25% de vacancia de oficinas contra 14,9% del resto de la Ciudad. **ENMODO sirve para validar el orden, no para fijar el nivel.**

Dos límites más de la fuente: encuesta hogares del AMBA, así que no captura turistas —relevante en San Telmo, Recoleta y Puerto Madero—, y se actualiza cada diez años. La validación quedó como script para poder repetirla cuando salga la próxima ola; si el acuerdo cae de 0,6 avisa solo.

Nota al margen: el INDEC **no** publica datos de movilidad por telefonía celular. Quien sí lo hace es el INE español, con sus [estudios de movilidad a partir de la telefonía móvil](https://www.ine.es/experimental/movilidad/experimental_em.htm). Si en algún momento aparece un equivalente local, reemplazaría a ENMODO y a este índice de una.

Decisiones de la versión actual:

- **Agregación por promedio de hexágonos, no por suma.** Los barrios varían mucho en superficie; sumar convierte el mapa de riesgo en un mapa de tamaños. El total se guarda aparte porque para asignar recursos el volumen sí importa.
- **Leaflet en vez de MapLibre GL.** MapLibre renderiza por WebGL y en esta máquina el proceso GPU de Chrome venía crasheando (`0xC0000005`), con `querySourceFeatures` devolviendo 0 features incluso en un repro mínimo. Leaflet dibuja en Canvas/DOM y no toca WebGL.
- **Leaflet directo, sin react-leaflet.** El mapa se repinta decenas de veces por cambio de filtro; manejar las capas a mano evita reconstruir el árbol de React en cada cambio, y esquiva el problema conocido de react-leaflet con StrictMode montando dos veces.
- **Cuantiles y no escala lineal** para el color, igual que en la primera versión: el riesgo está muy sesgado a la derecha y una rampa lineal deja 40 barrios del mismo color.
- **Las salvedades van dentro del tablero**, colapsadas pero con el número visible en el título. Un tablero que muestra números sin decir de qué no responden invita a leerlos como si respondieran de todo.
- **Los KPIs salen de `resumen.json`**, no hardcodeados en el front: un solo lugar donde corregirlos.

**Gotchas de esta etapa**:
- `create-next-app` no scaffoldea sobre un directorio con archivos (el `public/data/` ya generado por el export) — hubo que crear en un directorio temporal y mergear.
- **Leaflet encuadra solo con zooms enteros.** `fitBounds` sobre la Ciudad calculaba ~12,6, redondeaba a 12, y CABA terminaba ocupando un cuarto del lienzo con el conurbano de relleno. Se arregla con `zoomSnap: 0.25`.
- **`fitBounds` no puede correr en el efecto de creación**: en ese momento el contenedor todavía mide 0 de alto (el grid no resolvió) y el cálculo devuelve el zoom mínimo. Se espera al primer `ResizeObserver` con alto real.
- **La rueda del mouse.** Un mapa dentro de un tablero que scrollea se traga el scroll de la página y hace zoom: bajar con el cursor encima del mapa te deja a nivel de calle sin haberlo pedido. Se desactiva `scrollWheelZoom` y se habilita recién al hacer clic en el mapa.
- **`fetch(..., { cache: "force-cache" })` en los datos era una bomba de tiempo.** Los archivos de `public/data/` tienen nombre fijo, sin hash, así que `force-cache` hacía que el navegador se quedara con la copia vieja para siempre: al regenerar el export, quien ya había abierto el tablero seguía viendo los números anteriores. Apareció al agregar el filtro por tipo — los campos nuevos no estaban en la copia cacheada y el tablero mostraba `NaN`. Se cambió a `no-cache`, que revalida y termina en un 304 sin cuerpo si nada cambió.
- El export de Capa 4 tiraba `ArrayMemoryError` en esta máquina de 3,4GB releyendo `delitos_hex.parquet` por función (1,35M filas). Se carga una sola vez, con la fecha convertida a año/mes enteros y las columnas de texto a categóricas.
- La primera versión no se pudo verificar con la automatización de navegador (la extensión no llegaba a `localhost:3000`); esta sí — se verificó a ojo, con `npm run build` y `npx eslint` limpios.

Gotchas encontrados: `siniestros_hechos` guarda lat/lon como texto, no float (se castea en `hex_utils.asignar_hex_id`); `hora_siniestro` viene como "HH:MM:SS" mientras que `franja` de delitos ya es un número 0-23 (se resuelve en `hex_utils.turno_desde_hora`, detecta el formato).

### Overlay de polígono (`src/etl/overlay_poligonos.py`)

Cierra los 3 cruces de la tabla que no son point-in-hex: `espacios_verdes` (% de área verde por hex — overlay real, 372 de 401 hex tienen algo de verde, media 7,1%), `comisarias` (qué comisaría de patrullaje cubre la mayor parte de cada hex — por área de intersección, no por centroide; los 401 hex quedaron cubiertos) y **población por hex**, prorrateada por área dentro del barrio ya asignado (no hace falta overlay hex-contra-barrio real: como los hexágonos H3-8 tienen área casi idéntica entre sí, prorratear por área da resultados casi uniformes dentro de cada barrio — verificado, la suma total coincide exacto con `poblacion_barrio` real: 2.890.151).

**Bug real encontrado y corregido**: la primera versión calculaba el denominador de la proporción (`area_total_por_barrio`, vía `groupby().transform("sum")`) *antes* de un `.merge()`, y lo reusaba después. `merge()` devuelve un DataFrame con índice nuevo (0..n-1) que no respeta el orden de filas original — pandas alinea operaciones aritméticas por índice, no por posición, así que la división terminó emparejando cada hex con el denominador de OTRO hex, silenciosamente (sin error, sin warning). El síntoma: la población total sumaba 3.478.949 en vez de 2.890.151, un 20% de más, y decenas de miles de más/de menos por barrio sin patrón obvio. Se corrigió haciendo todo el cálculo — merge y transform — sobre el mismo dataframe sin cortes en el medio. Regla general: nunca guardar el resultado de un `groupby().transform()` para usarlo después de un `merge()`/`sort`/cualquier operación que pueda reindexar.
