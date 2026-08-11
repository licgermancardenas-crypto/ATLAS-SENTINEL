/**
 * Salvedades del modelo y de los tres módulos.
 *
 * Va como pestaña propia y no como nota al pie: el dashboard se usa para
 * decidir dónde poner recursos públicos, y cada número que muestra tiene un
 * alcance más chico del que sugiere. Los valores acá son los medidos, no
 * aproximaciones — si cambian los datos hay que actualizarlos a mano, igual
 * que el resto de las métricas escritas en generar_export.py.
 */

interface Salvedad {
  clave: string;
  texto: React.ReactNode;
}

interface Grupo {
  titulo: string;
  items: Salvedad[];
}

const GRUPOS: Grupo[] = [
  {
    titulo: "Modelo de riesgo",
    items: [
      {
        clave: "Le gana poco al promedio histórico",
        texto: (
          <>
            MAE 0,292 contra 0,298 de un baseline que sólo promedia el historial de cada
            hexágono y turno. Lo que sí hace bien es <strong>concentrar</strong>: el 20% del
            área priorizada reúne el 45,5% de los delitos, estable los 12 meses del período
            de prueba (44,0% a 47,4%).
          </>
        ),
      },
      {
        clave: "Calibración desigual por tramo",
        texto: (
          <>
            En los deciles 3 a 9 el error no pasa de 2,6%. En los tres más bajos
            <strong> subestima</strong> — hasta 33,5% en relativo en el decil 0— aunque en
            absoluto son 0,003 delitos por celda.
          </>
        ),
      },
      {
        clave: "Es una tasa, no un pronóstico",
        texto: (
          <>
            El score es riesgo esperado por hexágono y turno. No predice hechos concretos ni
            dice cuándo va a ocurrir algo.
          </>
        ),
      },
    ],
  },
  {
    titulo: "Módulo A — patrullas",
    items: [
      {
        clave: "Cobertura no es delito evitado",
        texto: (
          <>
            El 58,7% mide riesgo esperado que queda a 800 m de calle de alguna unidad. Medir
            el efecto real exige un piloto con zonas de control.
          </>
        ),
      },
      {
        clave: "Radio fijo y un solo turno",
        texto: (
          <>
            Se asume una cobertura efectiva de 800 m igual para toda la Ciudad, y se optimiza
            el turno Tarde. Ambos son parámetros ajustables, no supuestos estructurales.
          </>
        ),
      },
      {
        clave: "Con menos de 10 unidades no hay plan",
        texto: (
          <>
            La restricción de equidad exige al menos un hexágono cubierto por cada una de las
            15 comunas. Con K=5 el problema es <strong>infactible</strong>: el modelo se niega
            a producir un plan que abandone comunas enteras.
          </>
        ),
      },
    ],
  },
  {
    titulo: "Módulo B — zonas para cámaras",
    items: [
      {
        clave: "Prioriza zonas, no ubica cámaras",
        texto: (
          <>
            Cada hexágono mide unos 700 m de centro a centro, muy por encima del alcance de
            una cámara. Dónde va exactamente cada una dentro de la zona —esquina, altura,
            ángulo— es una decisión de campo.
          </>
        ),
      },
      {
        clave: "Los pesos son una elección",
        texto: (
          <>
            Oscuridad y flujo peatonal entran como multiplicadores de hasta ×2 cada uno.
            Es una decisión de diseño defendible, no un resultado empírico: con otros pesos
            cambia el ranking.
          </>
        ),
      },
      {
        clave: "Las cámaras actuales son de tránsito",
        texto: (
          <>
            Las 224 relevadas son de fiscalización vehicular. Contarlas como cobertura de
            seguridad probablemente <strong>sobreestima</strong> lo que hoy está cubierto.
          </>
        ),
      },
    ],
  },
  {
    titulo: "Módulo C — accesos",
    items: [
      {
        clave: "Nueve casos es poco",
        texto: (
          <>
            Cada escalón de percentil vale 11 puntos. Los dos primeros puestos aguantan
            cualquier normalización razonable; <strong>del 3° al 9° el orden no debería
            tomarse literal</strong>.
          </>
        ),
      },
      {
        clave: "Siniestros del hexágono, no de la traza",
        texto: (
          <>
            La accidentalidad cuenta todos los siniestros del hexágono, incluidos los de
            calles comunes sin relación con el acceso. En zonas céntricas densas infla el
            número.
          </>
        ),
      },
      {
        clave: "Dos ventanas temporales",
        texto: (
          <>
            Los siniestros son acumulados 2019-2025; el riesgo delictivo es la estimación
            para 2025. Se combinan como percentiles, así que la escala no es el problema,
            pero no describen el mismo período.
          </>
        ),
      },
    ],
  },
];

export default function LimitsPanel() {
  return (
    <div className="flex flex-col gap-5">
      <p className="text-xs text-text-secondary leading-relaxed">
        Qué <strong className="text-text-primary">no</strong> dice cada número de este
        tablero. Conviene tenerlo a mano antes de comprometer recursos.
      </p>

      {GRUPOS.map((g) => (
        <div key={g.titulo}>
          <h3 className="text-sm font-semibold mb-2">{g.titulo}</h3>
          <div className="flex flex-col gap-3">
            {g.items.map((it) => (
              <div
                key={it.clave}
                className="border-l-2 border-status-serious pl-3 flex flex-col gap-1"
              >
                <span className="text-xs font-mono text-text-primary">{it.clave}</span>
                <p className="text-xs text-text-secondary leading-relaxed">{it.texto}</p>
              </div>
            ))}
          </div>
        </div>
      ))}

      <p className="text-xs text-text-secondary leading-relaxed border-t border-border pt-3">
        Ninguna de estas salvedades invalida el tablero: acotan para qué sirve. Prioriza
        dónde mirar primero; no reemplaza el criterio operativo ni mide el efecto de
        intervenir.
      </p>
    </div>
  );
}
