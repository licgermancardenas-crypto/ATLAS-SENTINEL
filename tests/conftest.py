"""
P2 de la auditoría técnica externa (sección 11): cero tests en todo el
repositorio pese a que ya se encontró un bug real (proration de
población, ver overlay_poligonos.py) que un test de propiedad simple
hubiera atrapado en segundos en vez de en una revisión manual.

Este conftest agrega los subdirectorios de src/ al sys.path para que los
tests puedan importar los módulos de pipeline directamente, sin
necesitar convertir el repo en un paquete instalable (ver auditoría,
recomendación de empaquetar con pyproject.toml — deuda separada, no
bloquea escribir tests ahora).
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for sub in ["etl", "model_core", "optimization", "validation", "export", "scenarios"]:
    sys.path.insert(0, str(RAIZ / "src" / sub))

DATA_FEATURES = RAIZ / "data" / "features"
DATA_PROCESSED = RAIZ / "data" / "processed"
