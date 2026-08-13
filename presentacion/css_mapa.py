"""Reemplaza el CSS de mapa en las tres paginas, para que las tres queden
identicas y no haya que editarlas a mano una por una."""

from __future__ import annotations

import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent / "paginas"
PAGINAS = ["modulo-a-patrullas.html", "modulo-b-camaras.html", "modulo-c-controles.html"]

# rampa de calor: un solo tono calido, claro -> oscuro (regla de la skill de
# dataviz para escalas secuenciales). Sobre el mapa va semitransparente, asi
# la trama de calles sigue leyendose debajo.
TOKENS_LIGHT = (
    "    --seq-1: #fde3d3; --seq-2: #f9bd9c; --seq-3: #f2926a; --seq-4: #dd6337; --seq-5: #ad3f14;\n"
    "    --map-agua: #ccd9e0; --map-tierra: #f4f2ee;\n"
    "    --via-menor: rgba(18,22,28,0.17); --via-media: rgba(18,22,28,0.34); --via-troncal: #8e949c;\n"
    "    --barrio-linea: rgba(18,22,28,0.16);"
)
TOKENS_DARK = (
    "--seq-1: #2b2119; --seq-2: #4a3020; --seq-3: #74452a; --seq-4: #a85f31; --seq-5: #e08a4a;\n"
    "{i}--map-agua: #0b1016; --map-tierra: #1a1e24;\n"
    "{i}--via-menor: rgba(255,255,255,0.13); --via-media: rgba(255,255,255,0.24); --via-troncal: #6b7480;\n"
    "{i}--barrio-linea: rgba(255,255,255,0.14);"
)

# tokens de mapa ya inyectados en una corrida anterior: se borran antes de
# volver a escribirlos, para que el script se pueda correr las veces que haga
# falta mientras se ajusta el diseño
YA_PUESTOS = re.compile(r"^[ ]*--(?:map-agua|via-menor|barrio-linea): [^\n]*;\n", re.MULTILINE)
LINEA_SEQ = re.compile(r"^(?P<i>[ ]*)--seq-1: [^\n]*--seq-5: #[0-9a-f]{6};$", re.MULTILINE)

CSS = """  /* ============ MAPA ============ */
  .mapa-caja { display: flex; flex-direction: column; gap: 0.85rem; }
  svg.mapa { border-radius: 3px; }

  .agua { fill: var(--map-agua); }
  .tierra { fill: var(--map-tierra); }
  .via { fill: none; stroke-linecap: round; stroke-linejoin: round; }
  .v-menor { stroke: var(--via-menor); stroke-width: 0.5; }
  .v-media { stroke: var(--via-media); stroke-width: 0.9; }
  .v-troncal { stroke: var(--via-troncal); stroke-width: 1.8; }
  .barrio-linea { fill: none; stroke: var(--barrio-linea); stroke-width: 0.8; }

  /* el riesgo va encima de la trama de calles pero semitransparente: es una
     capa tematica sobre un mapa, no un reemplazo del mapa */
  .hx { stroke: none; fill-opacity: 0.45; }
  .hx.b0 { fill: var(--seq-1); }
  .hx.b1 { fill: var(--seq-2); }
  .hx.b2 { fill: var(--seq-3); }
  .hx.b3 { fill: var(--seq-4); }
  .hx.b4 { fill: var(--seq-5); }

  .corr { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.6; }
  .capa-pt.c-existente circle { fill: var(--surface); stroke: var(--ink); stroke-width: 1.6; }
  .capa-pt.c-propuesto circle { fill: var(--accent); stroke: var(--surface); stroke-width: 2; }

  .mapa-leyenda {
    display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1.4rem;
    font-size: 0.78rem; color: var(--ink-2);
  }
  .ml-titulo {
    font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--ink-muted);
  }
  .ml-ramp { display: flex; align-items: center; gap: 3px; }
  .ml-cap { font-size: 0.72rem; color: var(--ink-muted); }
  .ml-sw { width: 22px; height: 10px; border-radius: 1px; }
  .ml-sw.b0 { background: var(--seq-1); }
  .ml-sw.b1 { background: var(--seq-2); }
  .ml-sw.b2 { background: var(--seq-3); }
  .ml-sw.b3 { background: var(--seq-4); }
  .ml-sw.b4 { background: var(--seq-5); }
  .ml-item { display: flex; align-items: center; gap: 0.45rem; }
  .ml-dot { width: 11px; height: 11px; border-radius: 50%; flex: none; }
  .ml-dot.c-existente { background: var(--surface); border: 1.5px solid var(--ink); }
  .ml-dot.c-propuesto { background: var(--accent); }
  .ml-dot.c-corredor { background: var(--accent-soft); border: 1.5px solid var(--accent); border-radius: 2px; }
  .ml-nota { color: var(--ink-muted); font-size: 0.72rem; }

"""


def main() -> None:
    for nombre in PAGINAS:
        ruta = AQUI / nombre
        txt = ruta.read_text(encoding="utf-8")

        txt = YA_PUESTOS.sub("", txt)

        n = len(LINEA_SEQ.findall(txt))
        assert n == 3, f"{nombre}: esperaba 3 bloques de tokens (light + 2 dark), encontré {n}"

        # el primero es el :root claro; los otros dos, los dos scopes oscuros
        estado = {"i": 0}

        def reemplazo(m):
            estado["i"] += 1
            ind = m.group("i")
            if estado["i"] == 1:
                return TOKENS_LIGHT
            return ind + TOKENS_DARK.format(i=ind)

        txt = LINEA_SEQ.sub(reemplazo, txt)

        # el bloque de mapa va desde su comentario hasta el proximo bloque
        patron = re.compile(
            r"  /\* =+ MAPA =+ \*/.*?(?=  /\* =+ |  \.cards \{)", re.DOTALL
        )
        assert patron.search(txt), f"{nombre}: no encontré el bloque CSS de mapa"
        txt = patron.sub(CSS, txt, count=1)

        ruta.write_text(txt, encoding="utf-8")
        print(f"{nombre}: CSS de mapa actualizado")


if __name__ == "__main__":
    main()
