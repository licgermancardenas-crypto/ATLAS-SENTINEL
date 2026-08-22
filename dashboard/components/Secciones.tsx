"use client";

import { useEffect, useRef, useState } from "react";

/* El tablero creció a trece paneles y su orden era el orden en que se
   construyeron. Eso funciona mientras hay cuatro; con trece, todo lo que no
   sea el mapa vive abajo de un scroll de varios miles de píxeles y no hay
   forma de saber que existe.

   Estas cuatro secciones agrupan por **la pregunta que contesta cada panel**,
   no por el módulo del que salieron:

     Dónde     el mapa y las unidades: qué zona concentra riesgo
     Qué hacer los módulos de decisión: cobertura, equidad, sensibilidad
     Quiénes   el contexto: población, víctimas, cuándo ocurre
     Qué viene la proyección

   La barra no es un router: el tablero sigue siendo una sola página y una sola
   selección. Es un índice con posición actual, que es lo que faltaba. */

export interface Seccion {
  id: string;
  label: string;
  /** Qué pregunta contesta. Va en el title, no ocupa espacio en la barra. */
  ayuda: string;
}

export const SECCIONES: Seccion[] = [
  { id: "donde", label: "Dónde", ayuda: "Qué zonas concentran el riesgo" },
  { id: "que-hacer", label: "Qué hacer", ayuda: "Cobertura, equidad y sensibilidad del plan" },
  { id: "quienes", label: "Quiénes", ayuda: "Quién vive ahí, quién es la víctima y cuándo ocurre" },
  { id: "que-viene", label: "Qué viene", ayuda: "El pronóstico mensual de la Ciudad" },
];

/** Ancla de sección. El `scroll-mt` compensa la barra pegajosa: sin eso el
 *  encabezado queda tapado justo después de saltar. */
export function AnclaSeccion({
  id, titulo, bajada, children,
}: { id: string; titulo: string; bajada: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-14 flex flex-col gap-3">
      <div className="flex items-baseline gap-2 flex-wrap pt-1">
        <h2 id={`${id}-h`} className="text-[13px] font-semibold tracking-tight text-ink">
          {titulo}
        </h2>
        <p className="text-[11px] text-ink-muted">{bajada}</p>
      </div>
      {children}
    </section>
  );
}

export function NavSecciones({ contenedor }: { contenedor: React.RefObject<HTMLElement | null> }) {
  const [activa, setActiva] = useState(SECCIONES[0].id);
  const clickeando = useRef(false);

  /* La posición actual se observa, no se deriva del clic: alguien que scrollea
     a mano también tiene que ver dónde está. Durante el salto programático se
     suspende, porque el observer dispara con todas las secciones intermedias y
     la barra parpadearía recorriéndolas. */
  useEffect(() => {
    const raiz = contenedor.current;
    if (!raiz) return;
    const obs = new IntersectionObserver(
      (entradas) => {
        if (clickeando.current) return;
        const visible = entradas
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActiva(visible.target.id);
      },
      // la banda de disparo es el tercio superior del contenedor: una sección
      // se considera "la actual" cuando su encabezado llegó arriba, no cuando
      // asoma por abajo
      { root: raiz, rootMargin: "-8% 0px -70% 0px", threshold: 0 },
    );
    SECCIONES.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [contenedor]);

  const ir = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    clickeando.current = true;
    setActiva(id);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => { clickeando.current = false; }, 700);
  };

  return (
    <nav aria-label="Secciones del tablero"
         /* opaca y no translúcida: con 95% + blur, las filas de la tabla de la
            sección anterior se veían por detrás de los botones y la barra
            parecía rota. En una herramienta densa el vidrio esmerilado no
            aporta nada y cuesta legibilidad. */
         className="sticky top-0 z-30 -mx-3 -mt-3 mb-0 px-3 py-1.5 bg-surface-0
                    border-b border-line-strong flex items-center gap-1 overflow-x-auto scroll-fino">
      {SECCIONES.map((s) => {
        const on = s.id === activa;
        return (
          <button
            key={s.id}
            onClick={() => ir(s.id)}
            title={s.ayuda}
            aria-current={on ? "true" : undefined}
            className={`px-2.5 py-1 text-[11.5px] rounded whitespace-nowrap cursor-pointer
                        transition-colors duration-150 border ${
              on ? "border-transparent bg-brand text-white font-medium"
                 : "border-transparent text-ink-2 hover:bg-surface-sunk"}`}
          >
            {s.label}
          </button>
        );
      })}
    </nav>
  );
}
