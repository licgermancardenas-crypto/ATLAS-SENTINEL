"use client";

/* Frontera de cliente para la vista 3D.
 *
 * Hace falta porque `next/dynamic` con `ssr: false` solo se puede usar dentro de
 * un componente de cliente, y la página tiene que seguir siendo de servidor para
 * poder exportar `metadata`. Es el mismo arreglo que usa `Dashboard.tsx` con el
 * mapa de Leaflet: MapLibre toca `window` y WebGL al importarse, así que no
 * puede renderizarse en el servidor.
 */

import dynamic from "next/dynamic";

const Ciudad3D = dynamic(() => import("./Ciudad3D"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full w-full place-items-center bg-[#07080a]">
      <span className="text-xs text-slate-400">Cargando la ciudad…</span>
    </div>
  ),
});

export default function Ciudad3DCliente() {
  return <Ciudad3D />;
}
