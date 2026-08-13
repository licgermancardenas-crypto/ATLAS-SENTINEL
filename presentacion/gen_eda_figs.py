"""Genera las figuras SVG de la pagina del EDA y las inyecta en el HTML.

Mismo patron que gen_mapas.py: la CSP de los artifacts bloquea cualquier host
externo, asi que no hay libreria de graficos — todo se dibuja como SVG inline
calculado desde los datos del repo. Los colores salen de variables CSS
(currentColor / var(--...)), no hardcodeadas, para que las figuras cambien con
el tema claro/oscuro igual que el resto de la pagina.

Mismo esquema que gen_mapas.py: lee la página fuente de `paginas/`, con los
marcadores vacíos, y escribe la versión completa en `build/`, que es lo que se
publica y no se versiona.

Uso: python presentacion/gen_eda_figs.py
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import wkt
from shapely.ops import unary_union

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
FUENTE = AQUI / "paginas"
BUILD = AQUI / "build"
sys.path.insert(0, str(RAIZ / "src" / "validation"))

from eda_delitos import (  # noqa: E402
    DIAS, cargar_delitos, matriz_vecindad, morans_i, morans_local,
)

PAGINA = "eda-delitos.html"


# ---------------------------------------------------------------- utilidades

def esc(t) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def num(v, dec=0) -> str:
    """Formato es-AR: punto para miles, coma para decimales."""
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


class Ejes:
    """Mapeo de coordenadas de datos a coordenadas del lienzo."""

    def __init__(self, x0, x1, y0, y1, izq=52, der=16, arr=18, aba=34, W=720, H=300):
        self.x0, self.x1, self.y0, self.y1 = x0, x1, y0, y1
        self.izq, self.der, self.arr, self.aba = izq, der, arr, aba
        self.W, self.H = W, H

    @property
    def ancho(self):
        return self.W - self.izq - self.der

    @property
    def alto(self):
        return self.H - self.arr - self.aba

    def x(self, v):
        return self.izq + (v - self.x0) / (self.x1 - self.x0) * self.ancho

    def y(self, v):
        return self.arr + (1 - (v - self.y0) / (self.y1 - self.y0)) * self.alto


def marco(e: Ejes, ticks_y, fmt_y=lambda v: f"{v:.0f}", grilla=True) -> list[str]:
    p = []
    for v in ticks_y:
        y = e.y(v)
        if grilla:
            p.append(f'<line class="gr" x1="{e.izq}" y1="{y:.1f}" x2="{e.W - e.der}" y2="{y:.1f}" />')
        p.append(f'<text class="tk" x="{e.izq - 8}" y="{y + 3.5:.1f}" text-anchor="end">{esc(fmt_y(v))}</text>')
    return p


def envolver(cuerpo: list[str], e: Ejes, titulo: str) -> str:
    return (f'<svg viewBox="0 0 {e.W} {e.H}" class="fig" role="img" aria-label="{esc(titulo)}">'
            + "".join(cuerpo) + "</svg>")


# ---------------------------------------------------------------- figura 1

def fig_serie_anual(d: pd.DataFrame) -> str:
    s = d.groupby("anio").size()
    base = s.loc[2016:2019].mean()
    e = Ejes(2015.6, 2025.4, 0, s.max() * 1.16, H=310)
    p = []

    # banda de cuarentena
    x0, x1 = e.x(2019.62), e.x(2021.38)
    p.append(f'<rect class="banda" x="{x0:.1f}" y="{e.arr}" width="{x1 - x0:.1f}" '
             f'height="{e.alto:.1f}" />')
    p.append(f'<text class="anota-alerta" x="{(x0 + x1) / 2:.1f}" y="{e.arr + 14}" '
             f'text-anchor="middle">cuarentena</text>')

    p += marco(e, [0, 40000, 80000, 120000, 160000], lambda v: f"{v / 1000:.0f}k")

    yb = e.y(base)
    p.append(f'<line class="ref" x1="{e.izq}" y1="{yb:.1f}" x2="{e.W - e.der}" y2="{yb:.1f}" />')
    p.append(f'<text class="anota" x="{e.izq + 6}" y="{yb - 7:.1f}">promedio 2016-2019: {num(base)}</text>')

    pts = [(e.x(a), e.y(v)) for a, v in s.items()]
    p.append('<path class="area" d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
             + f' L{pts[-1][0]:.1f},{e.y(0):.1f} L{pts[0][0]:.1f},{e.y(0):.1f} Z" />')
    p.append('<path class="linea" d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '" />')

    for (x, y), (a, v) in zip(pts, s.items()):
        dest = a in (2020, 2021)
        p.append(f'<circle class="pt{" pt-alerta" if dest else ""}" cx="{x:.1f}" cy="{y:.1f}" '
                 f'r="{4.5 if dest else 3.6}"><title>{a}: {num(v)} delitos</title></circle>')
        p.append(f'<text class="val" x="{x:.1f}" y="{y - 11:.1f}" text-anchor="middle">{v / 1000:.0f}k</text>')
        p.append(f'<text class="tk" x="{x:.1f}" y="{e.H - 12}" text-anchor="middle">{a}</text>')

    return envolver(p, e, f"Delitos registrados por año, 2016 a 2025. Cae a {num(s[2020])} en 2020 "
                          f"y vuelve al nivel previo desde 2022.")


# ---------------------------------------------------------------- figura 2

def fig_estacionalidad(d: pd.DataFrame) -> str:
    r = d[d.anio >= 2022]
    ind = lambda s: s / s.mean()
    paneles = [
        ("Por mes", ind(r.groupby("mes").size()), [f"{m:02d}" for m in range(1, 13)]),
        ("Por día de semana", ind(r.groupby("dia_semana").size()), [n[:3] for n in DIAS]),
        ("Por turno", ind(r.groupby("turno").size()).reindex(
            ["Madrugada", "Mañana", "Tarde", "Noche"]), ["Madr.", "Mañ.", "Tarde", "Noche"]),
    ]
    W, H = 720, 250
    p = [f'<line class="gr" x1="0" y1="0" x2="0" y2="0" />']
    p = []
    ancho_panel = W / 3
    for i, (titulo, serie, etiquetas) in enumerate(paneles):
        ox = i * ancho_panel
        e = Ejes(0, len(serie), 0, 1.85, izq=ox + 42, der=W - ox - ancho_panel + 14,
                 arr=42, aba=44, W=W, H=H)
        amp = serie.max() - serie.min()
        p.append(f'<text class="sub-t" x="{ox + 42}" y="20">{esc(titulo)}</text>')
        p.append(f'<text class="sub-s" x="{ox + 42}" y="34">amplitud {num(amp, 2)}</text>')
        if i == 0:
            p += marco(e, [0, 0.5, 1.0, 1.5], lambda v: num(v, 1))
        else:
            for v in [0, 0.5, 1.0, 1.5]:
                y = e.y(v)
                p.append(f'<line class="gr" x1="{e.izq}" y1="{y:.1f}" x2="{e.W - e.der}" y2="{y:.1f}" />')
        y1 = e.y(1)
        p.append(f'<line class="ref" x1="{e.izq}" y1="{y1:.1f}" x2="{e.W - e.der}" y2="{y1:.1f}" />')
        bw = e.ancho / len(serie) * 0.68
        for j, (etq, v) in enumerate(zip(etiquetas, serie.values)):
            cx = e.x(j + 0.5)
            y = e.y(v)
            clase = "barra" if v >= 1 else "barra barra-baja"
            p.append(f'<rect class="{clase}" x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{e.y(0) - y:.1f}"><title>{esc(etq)}: índice {num(v, 2)}</title></rect>')
            # etiquetas de valor solo donde entran: con 7 o 12 barras en un panel
            # de ~180px se pisan entre sí, y en esos dos casos lo que importa es
            # que la serie es plana, no cada número — la amplitud ya va en el
            # subtítulo del panel.
            if len(serie) <= 4:
                p.append(f'<text class="val" x="{cx:.1f}" y="{y - 5:.1f}" text-anchor="middle">{num(v, 2)}</text>')
            p.append(f'<text class="tk tk-mini" x="{cx:.1f}" y="{e.H - 26:.1f}" '
                     f'text-anchor="middle">{esc(etq)}</text>')
    e0 = Ejes(0, 1, 0, 1, W=W, H=H)
    p.append(f'<text class="tk" x="42" y="{H - 6}">índice: 1,00 = promedio del período 2022-2025</text>')
    return envolver(p, e0, "Estacionalidad por mes, día de semana y turno. La amplitud del turno "
                           "(1,35) es seis veces la del día de semana (0,21) y diez veces la del mes (0,13).")


# ---------------------------------------------------------------- figura 3

ORDEN_TIPOS = ["Robo", "Hurto", "Vialidad", "Lesiones", "Amenazas", "Homicidios"]


def fig_composicion(d: pd.DataFrame) -> str:
    sh = pd.crosstab(d.anio, d.tipo, normalize="index")[ORDEN_TIPOS] * 100
    e = Ejes(2016, 2025, 0, 100, izq=52, der=132, arr=18, aba=34, W=720, H=300)
    p = marco(e, [0, 25, 50, 75, 100], lambda v: f"{v:.0f}%", grilla=False)

    acum = np.zeros(len(sh))
    for k, tipo in enumerate(ORDEN_TIPOS):
        v = sh[tipo].to_numpy()
        arriba = acum + v
        sup = [(e.x(a), e.y(y)) for a, y in zip(sh.index, arriba)]
        inf = [(e.x(a), e.y(y)) for a, y in zip(sh.index, acum)][::-1]
        d_ = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in sup + inf) + " Z"
        p.append(f'<path class="cap c{k}" d="{d_}"><title>{esc(tipo)}: '
                 f'{num(sh[tipo].iloc[0], 1)}% en 2016 → {num(sh[tipo].iloc[-1], 1)}% en 2025</title></path>')
        ym = e.y(acum[-1] + v[-1] / 2)
        if v[-1] > 4:
            # el swatch va como <rect>, no como carácter ■: así no depende de que
            # la fuente tenga el glifo ni de cómo se sirva el charset
            p.append(f'<rect class="sw-r c{k}" x="{e.W - e.der + 10}" y="{ym - 5:.1f}" '
                     f'width="10" height="10" />')
            p.append(f'<text class="leyenda-cap" x="{e.W - e.der + 26}" y="{ym + 3.5:.1f}">'
                     f'{esc(tipo)}</text>')
        acum = arriba

    for a in sh.index:
        p.append(f'<text class="tk" x="{e.x(a):.1f}" y="{e.H - 12}" text-anchor="middle">{a}</text>')
    return envolver(p, e, "Composición por tipo de delito entre 2016 y 2025. Hurto crece del 29,9% "
                          "al 40,4% del total hasta 2024 y lesiones cae del 11,7% al 4,9%.")


def fig_cambio_tipo(d: pd.DataFrame) -> str:
    ab = pd.crosstab(d.anio, d.tipo)
    cam = ((ab.loc[2025] / ab.loc[2024] - 1) * 100).sort_values()
    e = Ejes(-45, 55, 0, len(cam), izq=104, der=20, arr=14, aba=34, W=720, H=232)
    x0 = e.x(0)
    for v in [-40, -20, 0, 20, 40]:
        x = e.x(v)
        p_ = "gr" if v else "ref"
        e_line = f'<line class="{p_}" x1="{x:.1f}" y1="{e.arr}" x2="{x:.1f}" y2="{e.y(0):.1f}" />'
        if v == -40:
            p = [e_line]
        else:
            p.append(e_line)
        p.append(f'<text class="tk" x="{x:.1f}" y="{e.H - 12}" text-anchor="middle">'
                 f'{"+" if v > 0 else ""}{v}%</text>')

    alto = e.alto / len(cam)
    for j, (tipo, v) in enumerate(cam.items()):
        yc = e.y(len(cam) - j - 0.5)
        x = e.x(v)
        clase = "barra-h" + ("" if v >= 0 else " barra-h-baja")
        p.append(f'<rect class="{clase}" x="{min(x0, x):.1f}" y="{yc - alto * 0.3:.1f}" '
                 f'width="{abs(x - x0):.1f}" height="{alto * 0.6:.1f}">'
                 f'<title>{esc(tipo)}: {num(ab.loc[2024, tipo])} en 2024 → '
                 f'{num(ab.loc[2025, tipo])} en 2025</title></rect>')
        p.append(f'<text class="tk tk-fila" x="{e.izq - 10}" y="{yc + 3.5:.1f}" '
                 f'text-anchor="end">{esc(tipo)}</text>')
        dx = 7 if v >= 0 else -7
        anc = "start" if v >= 0 else "end"
        p.append(f'<text class="val" x="{x + dx:.1f}" y="{yc + 3.5:.1f}" '
                 f'text-anchor="{anc}">{"+" if v > 0 else ""}{v:.0f}%</text>')
    return envolver(p, e, "Cambio de cada tipo entre 2024 y 2025: robo baja 27% y hurto 21%, "
                          "mientras amenazas sube 41%, lesiones 33% y vialidad 18%.")


# ---------------------------------------------------------------- figura 4

def fig_moran(serie_i: pd.Series, L: pd.DataFrame, esperado: float) -> str:
    e = Ejes(2015.6, 2025.4, 0, 0.8, izq=52, der=16, arr=18, aba=34, W=720, H=300)
    p = []
    x0, x1 = e.x(2019.62), e.x(2021.38)
    p.append(f'<rect class="banda" x="{x0:.1f}" y="{e.arr}" width="{x1 - x0:.1f}" height="{e.alto:.1f}" />')
    p += marco(e, [0, 0.2, 0.4, 0.6, 0.8], lambda v: num(v, 1))
    ye = e.y(esperado)
    p.append(f'<line class="ref-alerta" x1="{e.izq}" y1="{ye:.1f}" x2="{e.W - e.der}" y2="{ye:.1f}" />')
    p.append(f'<text class="anota-alerta" x="{e.izq + 6}" y="{ye - 7:.1f}">'
             f'valor esperado si el riesgo se repartiera al azar</text>')
    pts = [(e.x(a), e.y(v)) for a, v in serie_i.items()]
    p.append('<path class="linea" d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '" />')
    for (x, y), (a, v) in zip(pts, serie_i.items()):
        p.append(f'<circle class="pt" cx="{x:.1f}" cy="{y:.1f}" r="3.8">'
                 f'<title>{a}: I = {num(v, 3)}</title></circle>')
        p.append(f'<text class="tk" x="{x:.1f}" y="{e.H - 12}" text-anchor="middle">{a}</text>')
    return envolver(p, e, "Moran's I global por año: se mantiene entre +0,64 y +0,71 los diez años, "
                          "muy por encima del valor de azar, y no cae durante la pandemia.")


def fig_moran_scatter(L: pd.DataFrame) -> str:
    e = Ejes(L.z.min() - 0.2, L.z.max() + 0.2, L.lag.min() - 0.3, L.lag.max() + 0.3,
             izq=52, der=16, arr=18, aba=44, W=720, H=340)
    p = [f'<line class="gr" x1="{e.izq}" y1="{e.y(0):.1f}" x2="{e.W - e.der}" y2="{e.y(0):.1f}" />',
         f'<line class="gr" x1="{e.x(0):.1f}" y1="{e.arr}" x2="{e.x(0):.1f}" y2="{e.y(e.y0):.1f}" />']
    p += marco(e, [-1, 0, 1, 2, 3], lambda v: num(v, 0), grilla=False)
    for v in [-1, 0, 1, 2, 3, 4]:
        p.append(f'<text class="tk" x="{e.x(v):.1f}" y="{e.y(e.y0) + 16:.1f}" '
                 f'text-anchor="middle">{num(v, 0)}</text>')
    p.append(f'<text class="tk" x="14" y="{(e.arr + e.y(e.y0)) / 2:.1f}" text-anchor="middle" '
             f'transform="rotate(-90 14 {(e.arr + e.y(e.y0)) / 2:.1f})">'
             f'promedio de sus vecinos</text>')
    pend = float(np.polyfit(L.z, L.lag, 1)[0])
    xa, xb = e.x0 + 0.15, e.x1 - 0.15
    p.append(f'<line class="ajuste" x1="{e.x(xa):.1f}" y1="{e.y(pend * xa):.1f}" '
             f'x2="{e.x(xb):.1f}" y2="{e.y(pend * xb):.1f}" />')
    for z, lag, sig in zip(L.z, L.lag, L.p_valor <= 0.05):
        p.append(f'<circle class="nube{" nube-sig" if sig else ""}" cx="{e.x(z):.1f}" '
                 f'cy="{e.y(lag):.1f}" r="{3.2 if sig else 2.6}" />')
    p.append(f'<text class="tk" x="{(e.izq + e.W - e.der) / 2:.1f}" y="{e.H - 8}" '
             f'text-anchor="middle">delitos del hexágono (estandarizado)</text>')
    p.append(f'<text class="anota" x="{e.izq + 8}" y="{e.arr + 16}">'
             f'la pendiente de la recta ES el estadístico: I = {num(pend, 3)}</text>')
    return envolver(p, e, f"Diagrama de Moran para 2025: la nube tiene pendiente positiva "
                          f"de {num(pend, 3)}, los hexágonos con más delitos están rodeados de "
                          f"hexágonos con más delitos.")


# ---------------------------------------------------------------- figura 5

def fig_lisa(hm: pd.DataFrame, L: pd.DataFrame) -> str:
    geoms = [wkt.loads(w) for w in hm.geometry_wkt]
    tierra = unary_union(geoms)

    xs, ys = [], []
    for g in geoms:
        a, b, c, dd = g.bounds
        xs += [a, c]
        ys += [b, dd]
    W, PAD = 720, 10

    def merc(lon, lat):
        return math.radians(lon), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    mx = [merc(x, y)[0] for x, y in zip(xs, ys)]
    my = [merc(x, y)[1] for x, y in zip(xs, ys)]
    mx0, mx1, my0, my1 = min(mx), max(mx), min(my), max(my)
    escala = (W - 2 * PAD) / (mx1 - mx0)
    H = round((my1 - my0) * escala + 2 * PAD)

    def proy(lon, lat):
        x, y = merc(lon, lat)
        return (x - mx0) * escala + PAD, (my1 - y) * escala + PAD

    def a_d(geom):
        partes = []
        for poli in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom]):
            pts = [proy(lo, la) for lo, la in poli.exterior.coords]
            partes.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
        return " ".join(partes)

    CLASE = {"alto-alto": "q-aa", "bajo-bajo": "q-bb", "alto-bajo": "q-ab", "bajo-alto": "q-ba"}
    ETIQ = {"alto-alto": "núcleo caliente", "bajo-bajo": "zona fría",
            "alto-bajo": "isla caliente", "bajo-alto": "isla fría"}

    p = [f'<path class="ciudad" d="{a_d(tierra)}" />']
    for geom, (_, fila) in zip(geoms, L.iterrows()):
        sig = fila.p_valor <= 0.05
        clase = CLASE[fila.cuadrante] if sig else "q-no"
        etq = ETIQ[fila.cuadrante] if sig else "sin estructura significativa"
        p.append(f'<path class="hx {clase}" d="{a_d(geom)}"><title>{esc(etq)} — '
                 f'p = {num(fila.p_valor, 3)}</title></path>')

    return (f'<svg viewBox="0 0 {W} {H}" class="fig mapa" role="img" '
            f'aria-label="Mapa de la Ciudad de Buenos Aires con los 401 hexágonos coloreados '
            f'según su cluster espacial. El núcleo caliente forma una mancha contigua en el '
            f'centro; las zonas frías están en el norte y el sudeste.">' + "".join(p) + "</svg>")


# ---------------------------------------------------------------- figura 6

def fig_estabilidad(conteos: pd.DataFrame) -> str:
    anios = sorted(conteos.index)
    filas = []
    for a, b in zip(anios, anios[1:]):
        x, y = conteos.loc[a], conteos.loc[b]
        n_top = int(round(len(x) * 0.20))
        ta = set(x.sort_values(ascending=False).head(n_top).index)
        tb = set(y.sort_values(ascending=False).head(n_top).index)
        filas.append((f"{a}→{b}", x.corr(y, method="spearman"), len(ta & tb) / n_top))

    e = Ejes(-0.5, len(filas) - 0.5, 0.5, 1.02, izq=52, der=16, arr=18, aba=48, W=720, H=290)
    p = marco(e, [0.5, 0.6, 0.7, 0.8, 0.9, 1.0], lambda v: num(v, 2))

    for clase, idx in (("linea", 1), ("linea linea-alt", 2)):
        pts = [(e.x(i), e.y(f[idx])) for i, f in enumerate(filas)]
        p.append(f'<path class="{clase}" d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '" />')
        for (x, y), f in zip(pts, filas):
            cl = "pt" if idx == 1 else "pt pt-alt"
            nom = "Spearman" if idx == 1 else "solape del top-20%"
            p.append(f'<circle class="{cl}" cx="{x:.1f}" cy="{y:.1f}" r="3.6">'
                     f'<title>{esc(f[0])} — {nom}: {num(f[idx], 3)}</title></circle>')
    for i, f in enumerate(filas):
        p.append(f'<text class="tk tk-mini" x="{e.x(i):.1f}" y="{e.H - 26}" '
                 f'text-anchor="middle">{esc(f[0])}</text>')
    yl = e.H - 14
    p.append(f'<rect class="sw-r sw-accent-f" x="{e.izq}" y="{yl:.0f}" width="10" height="10" />')
    p.append(f'<text class="leyenda-fig" x="{e.izq + 16}" y="{yl + 8.5:.0f}">'
             f'correlación de Spearman</text>')
    p.append(f'<rect class="sw-r sw-signal-f" x="{e.izq + 190}" y="{yl:.0f}" width="10" height="10" />')
    p.append(f'<text class="leyenda-fig" x="{e.izq + 206}" y="{yl + 8.5:.0f}">'
             f'hexágonos del top-20% que se repiten</text>')
    return envolver(p, e, "Estabilidad del ranking entre años consecutivos: la correlación de "
                          "Spearman nunca baja de 0,970 y el solape del top-20% nunca baja de 87,8%.")


def fig_scatter_anios(conteos: pd.DataFrame) -> str:
    x, y = conteos.loc[2024], conteos.loc[2025]
    lx = np.log10(x + 1)
    ly = np.log10(y + 1)
    top = max(lx.max(), ly.max()) * 1.04
    e = Ejes(0, top, 0, top, izq=52, der=16, arr=18, aba=44, W=720, H=380)
    p = []
    for v in range(0, int(top) + 1):
        p.append(f'<line class="gr" x1="{e.izq}" y1="{e.y(v):.1f}" x2="{e.W - e.der}" y2="{e.y(v):.1f}" />')
        etq = f"{10 ** v:,.0f}".replace(",", ".")
        p.append(f'<text class="tk" x="{e.izq - 8}" y="{e.y(v) + 3.5:.1f}" text-anchor="end">{etq}</text>')
        p.append(f'<text class="tk" x="{e.x(v):.1f}" y="{e.H - 22}" text-anchor="middle">{etq}</text>')
    p.append(f'<line class="ref" x1="{e.x(0):.1f}" y1="{e.y(0):.1f}" '
             f'x2="{e.x(top):.1f}" y2="{e.y(top):.1f}" />')
    for a, b, h in zip(lx, ly, x.index):
        p.append(f'<circle class="nube nube-sig" cx="{e.x(a):.1f}" cy="{e.y(b):.1f}" r="2.8">'
                 f'<title>{esc(h)}: {num(x[h])} en 2024, {num(y[h])} en 2025</title></circle>')
    p.append(f'<text class="tk" x="{(e.izq + e.W - e.der) / 2:.1f}" y="{e.H - 6}" '
             f'text-anchor="middle">delitos por hexágono en 2024 (escala logarítmica)</text>')
    rho = x.corr(y, method="spearman")
    p.append(f'<text class="anota" x="{e.izq + 10}" y="{e.arr + 16}">'
             f'la nube se pega a la diagonal en tres órdenes de magnitud — Spearman {num(rho, 3)}</text>')
    return envolver(p, e, f"Delitos por hexágono en 2024 contra 2025, escala logarítmica. "
                          f"Los puntos se alinean sobre la diagonal, Spearman {num(rho, 3)}.")


# ---------------------------------------------------------------- inyección

def inyectar(html: str, nombre: str, contenido: str) -> str:
    patron = re.compile(f"(<!--{nombre}:START-->).*?(<!--{nombre}:END-->)", re.DOTALL)
    if not patron.search(html):
        raise SystemExit(f"no encontré los marcadores de {nombre}")
    return patron.sub(lambda m: m.group(1) + contenido + m.group(2), html)


def main() -> None:
    d = cargar_delitos()
    hm = (pd.read_parquet(RAIZ / "data" / "features" / "hex_maestra.parquet")
          .dropna(subset=["barrio_id"]).sort_values("hex_id").reset_index(drop=True))
    hexes = list(hm.hex_id)
    W = matriz_vecindad(hexes)

    serie_i = pd.Series({a: morans_i(
        d[d.anio == a].groupby("hex_id").size().reindex(hexes).fillna(0).to_numpy(float), W)[0]
        for a in sorted(d.anio.unique())})
    v2025 = d[d.anio == 2025].groupby("hex_id").size().reindex(hexes).fillna(0).to_numpy(float)
    L = morans_local(v2025, W)
    conteos = (d.groupby(["anio", "hex_id"]).size().unstack(fill_value=0)
               .reindex(columns=hexes, fill_value=0))

    html = (FUENTE / PAGINA).read_text(encoding="utf-8")
    figuras = {
        "FIG1": fig_serie_anual(d),
        "FIG2": fig_estacionalidad(d),
        "FIG3": fig_composicion(d),
        "FIG4": fig_cambio_tipo(d),
        "FIG5": fig_moran(serie_i, L, -1 / (len(hexes) - 1)),
        "FIG6": fig_moran_scatter(L),
        "FIG7": fig_lisa(hm, L),
        "FIG8": fig_estabilidad(conteos),
        "FIG9": fig_scatter_anios(conteos),
    }
    for nombre, svg in figuras.items():
        html = inyectar(html, nombre, svg)
        print(f"{nombre}: {len(svg):,} chars")
    BUILD.mkdir(exist_ok=True)
    (BUILD / PAGINA).write_text(html, encoding="utf-8")

    sig = (L.p_valor <= 0.05)
    print(f"\nLISA: {int(sig.sum())} significativos — "
          f"{L[sig].cuadrante.value_counts().to_dict()}")
    print(f"total: {len(html):,} chars")


if __name__ == "__main__":
    main()
