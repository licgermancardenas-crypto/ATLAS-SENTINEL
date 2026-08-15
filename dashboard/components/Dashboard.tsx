"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { BarrioProps, Capa, DatosDashboard, TipoDelito, Turno } from "@/lib/types";
import { CAPAS, claveDelitos, claveRiesgo, riesgoEsDelTipo, tasaInflada, tipoInfo } from "@/lib/types";
import { cargarDatos } from "@/lib/data";
import { delta, num, num3, pct, pp, tasa100k } from "@/lib/formato";
import { cortesPorCuantil, ETIQUETAS_CLASE, VAR_RIESGO } from "@/lib/escala";
import { KpiRow } from "./Kpi";
import {
  ChipsActivos, ControlK, SelectorCapa, SelectorComuna, SelectorTipo, SelectorTurno, ToggleTema,
} from "./Controles";
import { BarrasComuna, CurvaCobertura, SensibilidadAlRadio, SerieAnual } from "./Graficos";
import TablaBarrios from "./TablaBarrios";
import Salvedades from "./Salvedades";
import Cuando from "./Cuando";

// Leaflet toca `window` al importarse, así que no puede renderizar en el servidor
const Mapa = dynamic(() => import("./Mapa"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full grid place-items-center bg-surface-sunk">
      <span className="text-xs text-ink-muted">Cargando mapa…</span>
    </div>
  ),
});

export default function Dashboard() {
  const [datos, setDatos] = useState<DatosDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [turno, setTurno] = useState<Turno>("tarde");
  const [comuna, setComuna] = useState<number | null>(null);
  const [capa, setCapa] = useState<Capa>("patrullas");
  const [tipo, setTipo] = useState<TipoDelito>("todos");
  const [kPatrullas, setKPatrullas] = useState(75);
  const [barrio, setBarrio] = useState<string | null>(null);
  const [tema, setTema] = useState<"light" | "dark">("light");

  useEffect(() => {
    cargarDatos().then(setDatos).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", tema);
  }, [tema]);

  // al elegir un barrio conviene fijar también su comuna: si no, el mapa
  // resalta un polígono y la tabla sigue mostrando los otros 47. Va en el
  // handler y no en un efecto: derivarlo después del render hace que el tablero
  // se pinte una vez con la selección a medias.
  const elegirBarrio = useCallback((nombre: string | null) => {
    setBarrio(nombre);
    if (!nombre || !datos) return;
    const b = datos.barrios.features.find((f) => f.properties.nombre === nombre);
    if (b?.properties.comuna != null) setComuna(b.properties.comuna);
  }, [datos]);

  const props: BarrioProps[] = useMemo(
    () => datos?.barrios.features.map((f) => f.properties) ?? [], [datos],
  );

  const ks = useMemo(
    () => datos?.curvaK.curva.filter((p) => p.cobertura !== null).map((p) => p.k) ?? [],
    [datos],
  );

  const kpis = useMemo(() => {
    if (!datos) return [];
    const r = datos.resumen;
    const claveD = claveDelitos(tipo);
    const sel = comuna === null ? props : props.filter((b) => b.comuna === comuna);
    const foco = barrio ? props.filter((b) => b.nombre === barrio) : sel;

    const delitos = foco.reduce((s, b) => s + (b[claveD] as number), 0);
    const poblacion = foco.reduce((s, b) => s + ((b.poblacion as number) ?? 0), 0);
    const tasa = tasa100k(delitos, poblacion);
    // con toda la Ciudad seleccionada la advertencia no aplica: el numerador y
    // el denominador cubren lo mismo. Solo importa al mirar una parte
    const infladaSel = foco.length < props.length
      && foco.some((b) => tasaInflada(b.presion_visitantes as number | null));

    const punto = datos.curvaK.curva.find((p) => p.k === kPatrullas);
    const cob = punto?.cobertura ?? null;
    const actual = datos.curvaK.cobertura_actual;

    // la serie anual se calcula por tipo, no solo del total: así el delta y la
    // chispa siguen sirviendo con el filtro puesto, que es donde más informan
    // (lesiones y amenazas suben en 2025 mientras el total baja)
    const etiquetaSerie = tipo === "todos" ? null : tipoInfo(tipo).label;
    const serieAnual = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025].map((a) =>
      datos.serie
        .filter((f) => f.anio === a && (etiquetaSerie === null || f.tipo === etiquetaSerie))
        .reduce((s, f) => s + f.n, 0),
    );
    const previo = serieAnual[serieAnual.length - 2];
    const ultimo = serieAnual[serieAnual.length - 1];

    return [
      {
        etiqueta: tipo !== "todos" ? `${tipoInfo(tipo).label} registrados`
                : barrio ? "Delitos · barrio" : comuna !== null ? "Delitos · comuna" : "Delitos registrados",
        valor: num(delitos),
        nota: <>en {r.periodo.hasta}{barrio ? ` · ${barrio}` : comuna !== null ? ` · Comuna ${comuna}` : " · toda la Ciudad"}</>,
        // el delta y la chispa siguen al tipo, pero no a la comuna ni al
        // barrio: la serie mensual está agregada a nivel Ciudad y no se puede
        // recortar por territorio sin inventar el dato
        delta: comuna === null && !barrio && previo > 0
          ? { texto: delta(ultimo / previo - 1), tono: "alerta" as const }
          : undefined,
        chispa: comuna === null && !barrio ? serieAnual : undefined,
        ayuda: "Delitos georreferenciados del último año cerrado. El nivel de 2025 está bajo revisión — ver salvedades.",
      },
      {
        // reemplaza al "riesgo medio por celda", que era el índice crudo del
        // modelo: un 0,397 no se puede dimensionar sin conocer la escala. La
        // tasa cada 100.000 es el estándar con el que se compara delito entre
        // jurisdicciones, y además corrige lo que el conteo crudo no: Palermo
        // tiene 226.534 habitantes y Villa Real 5.500, así que el ranking por
        // conteo mide sobre todo cuánta gente vive en cada barrio.
        etiqueta: "Tasa de delito",
        valor: tasa === null ? "—" : num(tasa),
        nota: tasa === null
          ? <span className="text-[var(--warn)]">sin población para esta selección</span>
          : infladaSel
          ? <span className="text-[var(--warn)]">sobreestimada · mucha gente que no vive acá</span>
          : <>cada 100.000 habitantes · {num(poblacion)} hab.</>,
        ayuda: `Delitos de ${tipo === "todos" ? "todos los tipos" : tipoInfo(tipo).label.toLowerCase()} `
             + `por cada 100.000 habitantes de la selección. Es lo comparable entre barrios de tamaño distinto. `
             + `La población sale del padrón prorrateado por área (2.890.151 en total). `
             + `Mide sobre población residente, así que sobreestima donde entra mucha gente que no vive ahí. `
             + `La selección actual está marcada cuando cae en el quinto de mayor afluencia no residente, `
             + `medida con el flujo de subte y EcoBici por habitante. `
             + `Esa medida se validó contra la Encuesta de Movilidad Domiciliaria 2018 y ordena igual (Spearman 0,73), `
             + `pero al ver solo dos modos subestima los barrios que se llegan en tren o colectivo: `
             + `Liniers y Mataderos son el caso claro, y ahí la tasa también está sobreestimada aunque no aparezca marcada.`,
      },
      {
        etiqueta: "Cobertura actual",
        valor: pct(actual),
        nota: <>{datos.curvaK.n_comisarias} comisarías, donde están hoy</>,
        ayuda: `Riesgo que queda a ${datos.curvaK.radio_m} m de calle de alguna comisaría.`,
      },
      {
        etiqueta: `Cobertura con ${kPatrullas}`,
        valor: cob === null ? "—" : pct(cob),
        nota: cob === null
          ? <span className="text-[var(--bad)]">Sin solución: la equidad no se puede cumplir</span>
          : <>{punto?.reusa_comisaria ?? 0} reutilizan comisaría</>,
        delta: cob === null ? undefined : { texto: pp(cob - actual), tono: cob >= actual ? "bueno" as const : "malo" as const },
        ayuda: "Resultado del optimizador para ese presupuesto de patrullas.",
      },
      {
        etiqueta: "Concentración",
        valor: pct(r.modelo.concentracion_30pct_area),
        nota: <>de los delitos en el 30% del área</>,
        ayuda: "Lo que el modelo hace bien: priorizar. PAI 2,77 y PEI 99,5% sobre el 10% del área.",
      },
    ];
    // sin `turno`: desde que el riesgo medio salió de esta fila, ninguna tarjeta
    // depende del turno — delitos, tasa y cobertura son anuales
  }, [datos, tipo, comuna, barrio, kPatrullas, props]);

  if (error) {
    return (
      <main className="h-full grid place-items-center p-6">
        <div className="card p-5 max-w-md flex flex-col gap-2">
          <h1 className="text-sm font-semibold text-[var(--bad)]">No se pudieron cargar los datos</h1>
          <p className="text-xs text-ink-2">{error}</p>
          <button onClick={() => location.reload()}
                  className="mt-2 self-start px-3 py-1.5 text-xs rounded bg-brand text-white cursor-pointer">
            Reintentar
          </button>
        </div>
      </main>
    );
  }

  if (!datos) {
    return (
      <main className="h-full grid place-items-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-1 w-40 bg-surface-sunk rounded overflow-hidden">
            <div className="h-full w-1/3 bg-brand animate-pulse" />
          </div>
          <span className="text-xs text-ink-muted">Cargando SIGE-BA…</span>
        </div>
      </main>
    );
  }

  const clave = claveRiesgo(turno, tipo);
  const cortes = cortesPorCuantil(props.map((b) => b[clave] as number));
  const capaInfo = CAPAS.find((c) => c.key === capa)!;
  const superficiePropia = riesgoEsDelTipo(tipo);

  // la cascada de frecuencias sí puede seguir la selección territorial, porque
  // es un total dividido por tiempo. Los perfiles de hora y día no, y por eso
  // el panel los separa — ver el comentario de cabecera de Cuando.tsx
  const focoActual = barrio
    ? props.filter((b) => b.nombre === barrio)
    : comuna === null ? props : props.filter((b) => b.comuna === comuna);
  const delitosFoco = focoActual.reduce((s, b) => s + (b[claveDelitos(tipo)] as number), 0);
  const ambito = barrio ?? (comuna === null ? "toda la Ciudad" : `Comuna ${comuna}`);

  return (
    <main className="h-full flex flex-col overflow-hidden">
      {/* ---------- encabezado ---------- */}
      <header className="shrink-0 border-b border-line bg-surface-2">
        <div className="px-4 py-2.5 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-baseline gap-3 min-w-0">
            <h1 className="text-[15px] font-semibold tracking-tight whitespace-nowrap">
              SIGE-BA <span className="text-ink-muted font-normal">· Riesgo urbano</span>
            </h1>
            <span className="text-[11px] text-ink-muted whitespace-nowrap hidden sm:block">
              Ciudad de Buenos Aires · {datos.resumen.periodo.desde}–{datos.resumen.periodo.hasta}
            </span>
          </div>
          <ChipsActivos
            comuna={comuna} barrio={barrio} tipo={tipo}
            onLimpiarComuna={() => { setComuna(null); setBarrio(null); }}
            onLimpiarBarrio={() => setBarrio(null)}
            onLimpiarTipo={() => setTipo("todos")}
          />
        </div>
        <div className="px-4 pb-2.5 flex items-end gap-3 flex-wrap">
          <SelectorTurno valor={turno} onChange={setTurno} />
          <SelectorTipo valor={tipo} onChange={setTipo} />
          <SelectorComuna valor={comuna} onChange={(c) => { setComuna(c); setBarrio(null); }} comunas={datos.comunas} />
          <SelectorCapa valor={capa} onChange={setCapa} />
          {capa === "patrullas" && <ControlK valor={kPatrullas} onChange={setKPatrullas} disponibles={ks} />}
          <div className="ml-auto flex items-end gap-2">
            <ToggleTema tema={tema} onChange={() => setTema((t) => (t === "light" ? "dark" : "light"))} />
          </div>
        </div>
      </header>

      {/* ---------- cuerpo ---------- */}
      <div className="flex-1 min-h-0 overflow-auto scroll-fino p-3 flex flex-col gap-3">
        <KpiRow items={kpis} />

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
          {/* mapa */}
          {/* alto atado al viewport: con un min-height fijo, en una pantalla de
              portátil el mapa empuja los KPIs fuera de la primera vista */}
          <section className="card overflow-hidden flex flex-col h-[clamp(24rem,58vh,36rem)]">
            <div className="px-3 py-2 border-b border-line flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
                  {superficiePropia ? `Riesgo de ${tipoInfo(tipo).label.toLowerCase()} por barrio` : "Riesgo por barrio"}
                </h2>
                <p className="text-[11px] text-ink-muted truncate">{capaInfo.descripcion}</p>
              </div>
              <Leyenda cortes={cortes} />
            </div>
            <div className="flex-1 min-h-0">
              <Mapa
                datos={datos} turno={turno} capa={capa} tipo={tipo} comuna={comuna}
                barrioActivo={barrio} kPatrullas={kPatrullas} tema={tema}
                onBarrio={elegirBarrio}
              />
            </div>
            <AvisoSuperficie tipo={tipo} capa={capa} />
            {capa !== "ninguna" && <LeyendaPuntos capa={capa} k={kPatrullas} />}
          </section>

          {/* panel derecho */}
          <div className="flex flex-col gap-3 min-w-0">
            <section className="card p-3">
              <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                Cobertura según cantidad de patrullas
              </h2>
              <p className="text-[11px] text-ink-muted mb-2">
                Cada punto es una optimización completa, no una interpolación. Clic para fijar el escenario.
              </p>
              <CurvaCobertura curva={datos.curvaK} kActual={kPatrullas} onK={setKPatrullas} />
            </section>

            <Cuando perfil={datos.perfil} tipo={tipo}
                    delitosSeleccion={delitosFoco} ambito={ambito} />

            <section className="card p-3">
              <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                Riesgo medio por comuna
              </h2>
              <p className="text-[11px] text-ink-muted mb-2">
                Turno {turno === "manana" ? "mañana" : turno}, ×100. Clic para filtrar todo el tablero.
              </p>
              <BarrasComuna comunas={datos.comunas} turno={turno} tipo={tipo} seleccion={comuna}
                            onSeleccion={(c) => { setComuna(c); setBarrio(null); }} />
            </section>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
          <section className="card overflow-hidden max-h-[30rem] flex flex-col">
            <TablaBarrios barrios={props} turno={turno} tipo={tipo} comuna={comuna}
                          barrioActivo={barrio} onBarrio={elegirBarrio} />
          </section>
          <div className="flex flex-col gap-3 min-w-0">
            <section className="card p-3">
              <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                Delitos por mes y tipo
              </h2>
              <SerieAnual serie={datos.serie} tipo={tipo} onTipo={setTipo} />
            </section>

            {/* va acá, pegado a las salvedades y no al Módulo A: es lo que hay
                que leer antes de tomar las ubicaciones del mapa como un plan */}
            <section className="card p-3">
              <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                Si el radio no fuera {datos.curvaK.radio_m} m
              </h2>
              <p className="text-[11px] text-ink-muted mb-2">
                La ganancia aguanta en todo el barrido. Las ubicaciones no: fuera
                de {datos.curvaK.radio_m} m, casi ninguna se repite.
              </p>
              <SensibilidadAlRadio datos={datos.radio} />
            </section>

            <Salvedades items={datos.resumen.salvedades} />
          </div>
        </div>
      </div>
    </main>
  );
}

function Leyenda({ cortes }: { cortes: number[] }) {
  return (
    <div className="flex items-center gap-2 shrink-0">
      <span className="text-[10px] text-ink-muted">bajo</span>
      <div className="flex" role="img" aria-label="Escala de riesgo en cinco clases por quintiles">
        {VAR_RIESGO.map((v, i) => (
          <span key={v} className="w-6 h-3 first:rounded-l-sm last:rounded-r-sm"
                style={{ background: `var(${v})` }}
                title={`${ETIQUETAS_CLASE[i]}${cortes[i] !== undefined ? ` · hasta ${num3(cortes[i])}` : ""}`} />
        ))}
      </div>
      <span className="text-[10px] text-ink-muted">alto</span>
    </div>
  );
}

/* Las dos cosas que el filtro por tipo NO cambia, dichas donde se las puede
   leer mal. Sin esto, alguien filtra por hurto, ve moverse la coropleta y las
   patrullas quietas, y concluye que ese es el plan óptimo para hurto — cuando
   los Módulos A/B/C se resuelven sobre el modelo agregado. El README lo tiene
   medido: hurto y lesiones comparten solo el 60% de las ubicaciones. */

function AvisoSuperficie({ tipo, capa }: { tipo: TipoDelito; capa: Capa }) {
  if (tipo === "todos") return null;
  const info = tipoInfo(tipo);
  const mensaje = !info.superficie
    ? `${info.label}: los delitos del tablero son de este tipo, pero el mapa dibuja el riesgo agregado. ${info.nota}`
    : capa !== "ninguna"
    ? `El mapa muestra la superficie de ${info.label.toLowerCase()}, pero las ubicaciones propuestas se optimizan sobre el modelo agregado — no son el plan óptimo para ${info.label.toLowerCase()}.`
    : null;
  if (!mensaje) return null;
  return (
    <p className="px-3 py-1.5 border-t border-line text-[11px] leading-snug text-ink-2
                  flex items-start gap-1.5 bg-[var(--warn-wash,transparent)]">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--warn)" strokeWidth="2.2"
           strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-[2px]" aria-hidden="true">
        <circle cx="12" cy="12" r="10" /><path d="M12 8v5M12 16h.01" />
      </svg>
      <span>{mensaje}</span>
    </p>
  );
}

function LeyendaPuntos({ capa, k }: { capa: Capa; k: number }) {
  const items =
    capa === "patrullas"
      ? [{ c: "var(--pt-existente)", t: "Comisarías actuales (75)" },
         { c: "var(--pt-propuesto)", t: `Patrullas propuestas (${k})` }]
      : capa === "camaras"
      ? [{ c: "var(--pt-existente)", t: "Cámaras existentes (224)" },
         { c: "var(--pt-propuesto)", t: "Cámaras propuestas (30)" }]
      : [{ c: "var(--pt-alerta)", t: "Accesos rankeados (9) — el tamaño es el puesto" }];
  return (
    <div className="px-3 py-1.5 border-t border-line flex items-center gap-4 flex-wrap">
      {items.map((i) => (
        <span key={i.t} className="inline-flex items-center gap-1.5 text-[11px] text-ink-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: i.c }} />
          {i.t}
        </span>
      ))}
    </div>
  );
}
