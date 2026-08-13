"""Rinde una previsualizacion PNG del mapa con matplotlib, leyendo los MISMOS
paths SVG que se inyectaron en las paginas -- asi lo que se mira es el
resultado real y no una reconstruccion aparte. Replica el orden de capas del
SVG: agua, tierra, calles, calor (recortado a la costa), avenidas y troncales
POR ENCIMA del calor, corredores, puntos."""

from __future__ import annotations

import re
import sys
from pathlib import Path as FsPath

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from matplotlib.path import Path as MplPath

# lee de build/, que es donde queda la página con el mapa ya inyectado
AQUI = FsPath(__file__).resolve().parent / "build"

TEMA = {
    "light": dict(agua="#ccd9e0", tierra="#f4f2ee", menor=(0.07, 0.09, 0.11, 0.17),
                  media=(0.07, 0.09, 0.11, 0.34), troncal="#8e949c",
                  barrio=(0.07, 0.09, 0.11, 0.16), ink="#12161c", surf="#fdfdfc",
                  ramp=["#fde3d3", "#f9bd9c", "#f2926a", "#dd6337", "#ad3f14"]),
    "dark": dict(agua="#0b1016", tierra="#1a1e24", menor=(1, 1, 1, 0.13),
                 media=(1, 1, 1, 0.24), troncal="#6b7480",
                 barrio=(1, 1, 1, 0.14), ink="#f3f5f6", surf="#15181d",
                 ramp=["#2b2119", "#4a3020", "#74452a", "#a85f31", "#e08a4a"]),
}

ALPHA_CALOR = 0.45


def subpaths(d: str):
    for trozo in d.split("M")[1:]:
        pts = []
        for par in trozo.replace("Z", "").split("L"):
            par = par.strip()
            if not par:
                continue
            x, y = par.split(",")
            pts.append((float(x), float(y)))
        if pts:
            yield pts


def path_compuesto(d: str) -> MplPath:
    """Un solo Path de matplotlib con todos los subpaths, para usar de clip."""
    verts, codes = [], []
    for pts in subpaths(d):
        verts.extend(pts + [pts[0]])
        codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(pts) - 1) + [MplPath.CLOSEPOLY])
    return MplPath(verts, codes)


def main() -> None:
    pagina = sys.argv[1] if len(sys.argv) > 1 else "modulo-a-patrullas.html"
    modo = sys.argv[2] if len(sys.argv) > 2 else "light"
    t = TEMA[modo]

    html = (AQUI / pagina).read_text(encoding="utf-8")
    svg = re.search(r'<svg viewBox="0 0 (\d+) (\d+)" class="mapa".*?</svg>', html, re.DOTALL)
    W, H = int(svg.group(1)), int(svg.group(2))
    s = svg.group(0)

    fig, ax = plt.subplots(figsize=(W / 100, H / 100), dpi=100)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    fig.patch.set_facecolor(t["agua"]); ax.set_facecolor(t["agua"])

    d_tierra = re.search(r'class="tierra" d="([^"]+)"', s).group(1)
    for pts in subpaths(d_tierra):
        ax.add_patch(MplPoly(pts, closed=True, facecolor=t["tierra"], edgecolor="none", zorder=1))
    clip = path_compuesto(d_tierra)

    vias = {c: re.search(rf'id="via-{c}" class="via v-{c}" d="([^"]+)"', s).group(1)
            for c in ("menor", "media", "troncal")}

    def trazar(clase, color, lw, z):
        for pts in subpaths(vias[clase]):
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=color, linewidth=lw, solid_capstyle="round", zorder=z)

    trazar("menor", t["menor"], 0.35, 2)
    trazar("media", t["media"], 0.6, 3)
    trazar("troncal", t["troncal"], 1.2, 4)

    for pts in subpaths(re.search(r'id="barrios" class="barrio-linea" d="([^"]+)"', s).group(1)):
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=t["barrio"], linewidth=0.5, zorder=5)

    # calor, recortado a la silueta de la ciudad
    for b, d in re.findall(r'class="hx b(\d)" d="([^"]+)"', s):
        for pts in subpaths(d):
            p = MplPoly(pts, closed=True, facecolor=t["ramp"][int(b)],
                        edgecolor="none", alpha=ALPHA_CALOR, zorder=6)
            ax.add_patch(p)
            p.set_clip_path(clip, ax.transData)

    # avenidas y troncales de nuevo, encima del calor (el <use> del SVG)
    trazar("media", t["media"], 0.6, 6.5)
    trazar("troncal", t["troncal"], 1.2, 6.6)

    for d in re.findall(r'class="corr" d="([^"]+)"', s):
        for pts in subpaths(d):
            ax.add_patch(MplPoly(pts, closed=True, facecolor="none",
                                 edgecolor="#2a78d6", linewidth=1.1, zorder=7))

    for clase, fill, edge in (("c-existente", t["surf"], t["ink"]),
                              ("c-propuesto", "#2a78d6", t["surf"])):
        bloque = re.search(rf'<g class="capa-pt {clase}">(.*?)</g>', s, re.DOTALL)
        if not bloque:
            continue
        for cx, cy, r in re.findall(r'cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', bloque.group(1)):
            ax.add_patch(plt.Circle((float(cx), float(cy)), float(r),
                                    facecolor=fill, edgecolor=edge, linewidth=1.2, zorder=8))

    salida = AQUI / f"preview-{pagina.split('-')[1]}-{modo}.png"
    fig.savefig(salida, facecolor=t["agua"], bbox_inches="tight", pad_inches=0)
    print(salida.name)


if __name__ == "__main__":
    main()
