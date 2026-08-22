"use client";

import { useMemo, useRef } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { BarrioProps } from "@/lib/types";
import {
  CAPAS, claveDelitos, claveRiesgo, esDemografica, riesgoEsDelTipo,
  superficieInfo, tasaInflada, tipoInfo,
} from "@/lib/types";
import { delta, num, pct, pp, tasa100k } from "@/lib/formato";
import { cortesPorCuantil } from "@/lib/escala";
import { KpiRow } from "./Kpi";
import {
  ChipsActivos, ControlK, SelectorCapa, SelectorComuna, SelectorSuperficie, SelectorTipo,
  SelectorTurno, ToggleTema,
} from "./Controles";
import {
  BarrasComuna, BrechaCobertura, CurvaCobertura, SensibilidadAlRadio, SerieAnual, Vulnerables,
} from "./Graficos";
import TablaBarrios from "./TablaBarrios";
import Salvedades from "./Salvedades";
import Pronostico from "./Pronostico";
import Poblacion from "./Poblacion";
import Equidad from "./Equidad";
import Victimas from "./Victimas";
import { AnclaSeccion, NavSecciones } from "./Secciones";
import { AvisoSuperficie, Leyenda, LeyendaPuntos } from "./MapaChrome";
import { useSeleccion } from "@/lib/useSeleccion";
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
  // el scroll no lo tiene el window sino este contenedor, así que el
  // scroll-spy de secciones y el salto por ancla necesitan la referencia
  const cuerpo = useRef<HTMLDivElement>(null);

  /* Todo el estado de selección y la sincronización con la URL viven en el
     hook, compartidos con la página del mapa a pantalla completa. Duplicarlos
     era garantizar que un día se separaran. */
  const {
    datos, error, turno, setTurno, tipo, setTipo, comuna, elegirComuna, setComuna,
    barrio, elegirBarrio, capa, setCapa, superficie, setSuperficie,
    kPatrullas, setKPatrullas, tema, alternarTema, qs,
  } = useSeleccion();

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
    const puntoPob = datos.coberturaPob.curva.find((p) => p.k === kPatrullas);
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
             + `La población es la del censo, repartida entre las zonas según cuánto ocupa cada una `
             + `(2.890.151 habitantes en total). `
             + `Mide sobre población residente, así que sobreestima donde entra mucha gente que no vive ahí. `
             + `La selección actual está marcada cuando cae en el cuarto de mayor afluencia no residente, `
             + `medida con el flujo de subte, tren, colectivo y EcoBici por habitante. `
             + `Se comparó contra la Encuesta de Movilidad Domiciliaria 2018 y ordena los barrios casi `
             + `igual: 0,81 en una escala donde 1 sería idéntico. `
             + `El colectivo entra repartido: SUBE informa por línea y no por parada, así que los boletos de cada `
             + `línea se distribuyen parejo entre sus paradas — sirve para el ranking, no para el nivel de un barrio suelto.`,
      },
      {
        etiqueta: "Cobertura actual",
        valor: pct(actual),
        nota: <>{datos.curvaK.n_comisarias} comisarías · {pct(datos.coberturaPob.actual.poblacion)}{" "}
          de la población</>,
        ayuda: `Riesgo que queda a ${datos.curvaK.radio_m} m de calle de alguna comisaría. `
             + `Medido en habitantes en vez de en riesgo, esas mismas comisarías alcanzan a `
             + `${num(datos.coberturaPob.actual.habitantes)} personas, el `
             + `${pct(datos.coberturaPob.actual.poblacion)} de la Ciudad: el riesgo está más `
             + `concentrado que la gente, así que cubrirlo no es lo mismo que cubrir residentes.`,
      },
      {
        etiqueta: `Cobertura con ${kPatrullas}`,
        valor: cob === null ? "—" : pct(cob),
        nota: cob === null
          ? <span className="text-[var(--bad)]">Sin solución: la equidad no se puede cumplir</span>
          : <>{punto?.reusa_comisaria ?? 0} reutilizan comisaría
              {puntoPob?.poblacion != null && <> · {pct(puntoPob.poblacion)} de la población</>}</>,
        delta: cob === null ? undefined : { texto: pp(cob - actual), tono: cob >= actual ? "bueno" as const : "malo" as const },
        ayuda: "Cuánto riesgo quedaría cubierto si se ubicaran esa cantidad de patrullas en los "
             + "mejores lugares posibles, en vez de donde están las comisarías hoy.",
      },
      {
        etiqueta: "Concentración",
        valor: pct(r.modelo.concentracion_30pct_area),
        nota: <>de los delitos en el 30% del área</>,
        ayuda: "Lo que el modelo hace bien es priorizar: en el 10% del territorio que marca como más "
             + "riesgoso ocurren 2,8 veces más delitos que si se eligiera ese 10% al azar. Y está a "
             + "menos de un punto del mejor reparto que se podría haber hecho sabiendo de antemano "
             + "dónde iba a pasar todo.",
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
          <span className="text-xs text-ink-muted">Cargando ATLAS SENTINEL…</span>
        </div>
      </main>
    );
  }

  const clave = claveRiesgo(turno, tipo);
  const capaInfo = CAPAS.find((c) => c.key === capa)!;
  const superficiePropia = riesgoEsDelTipo(tipo);
  const supInfo = superficieInfo(superficie);
  const demografica = esDemografica(superficie);

  // los cortes de la leyenda salen del mismo conjunto que pinta el mapa: los 48
  // barrios para el riesgo, las 15 comunas para la edad. Calcularlos siempre
  // sobre barrios dejaría la escala diciendo una cosa y el mapa otra.
  const cortes = supInfo.unidad === "comuna"
    ? cortesPorCuantil(datos.comunasGeo.features.map((f) => f.properties[supInfo.campo!] ?? NaN))
    : supInfo.campo
    ? cortesPorCuantil(datos.demografia.barrios.map(
        (b) => (b[supInfo.campo as "densidad" | "pct_nbi"] as number | null) ?? NaN))
    : cortesPorCuantil(props.map((b) => b[clave] as number));

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
              ATLAS SENTINEL <span className="text-ink-muted font-normal">· Riesgo urbano</span>
            </h1>
            <span className="text-[11px] text-ink-muted whitespace-nowrap hidden sm:block">
              Ciudad de Buenos Aires · {datos.resumen.periodo.desde}–{datos.resumen.periodo.hasta}
            </span>
          </div>
          {/* Los chips de filtro activo y las dos acciones globales comparten
              la fila del título, que estaba vacía a la derecha. Antes las
              acciones colgaban al final de la fila de filtros y empujaban al
              deslizador de patrullas a una tercera fila: tres franjas de
              encabezado sobre un tablero que ya scrollea mucho. */}
          <div className="flex items-center gap-3 flex-wrap">
            <ChipsActivos
              comuna={comuna} barrio={barrio} tipo={tipo}
              onLimpiarComuna={() => elegirComuna(null)}
              onLimpiarBarrio={() => elegirBarrio(null)}
              onLimpiarTipo={() => setTipo("todos")}
            />
            <div className="flex items-center gap-2">
              {/* los dos links llevan la selección puesta: el mapa a pantalla
                  completa es la misma vista, no otro tablero */}
              <Link href={`/mapa${qs ? `?${qs}` : ""}`}
                className="rounded border border-line bg-surface-1 px-2.5 py-1 text-[11px]
                           hover:bg-surface-sunk">
                Mapa completo
              </Link>
              <Link href="/3d"
                className="rounded border border-line bg-surface-1 px-2.5 py-1 text-[11px]
                           hover:bg-surface-sunk">
                Ver en 3D
              </Link>
              <ToggleTema tema={tema} onChange={alternarTema} />
            </div>
          </div>
        </div>
        <div className="px-4 pb-2.5 flex items-end gap-3 flex-wrap">
          <SelectorTurno valor={turno} onChange={setTurno} />
          <SelectorTipo valor={tipo} onChange={setTipo} />
          <SelectorComuna valor={comuna} onChange={elegirComuna} comunas={datos.comunas} />
          <SelectorSuperficie valor={superficie} onChange={setSuperficie} />
          <SelectorCapa valor={capa} onChange={setCapa} />
          {capa === "patrullas" && <ControlK valor={kPatrullas} onChange={setKPatrullas} disponibles={ks} />}
        </div>
      </header>

      {/* ---------- cuerpo ----------
          Cuatro secciones agrupadas por la pregunta que contestan, no por el
          módulo del que salió cada panel. Antes eran trece tarjetas apiladas en
          el orden en que se fueron construyendo. */}
      <div ref={cuerpo} className="flex-1 min-h-0 overflow-auto scroll-fino p-3 flex flex-col gap-3">
        <NavSecciones contenedor={cuerpo} />

        <KpiRow items={kpis} />

        <AnclaSeccion id="donde" titulo="Dónde"
                      bajada="Qué zonas concentran el riesgo, y con qué contexto">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
            {/* alto atado al viewport: con un min-height fijo, en una pantalla de
                portátil el mapa empuja los KPIs fuera de la primera vista */}
            {/* `isolate` no es decorativo: Leaflet numera sus panes con z-index
                de varios cientos y, sin un contexto de apilado propio, la
                tarjeta del mapa se dibujaba por encima de la barra pegajosa
                de secciones y la hacía desaparecer al scrollear. */}
            <section className="card isolate overflow-hidden flex flex-col h-[clamp(24rem,58vh,36rem)]">
              <div className="px-3 py-2 border-b border-line flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
                    {demografica ? `${supInfo.label} · por ${supInfo.unidad}`
                      : superficiePropia ? `Riesgo de ${tipoInfo(tipo).label.toLowerCase()} por barrio`
                      : "Riesgo por barrio"}
                  </h3>
                  <p className="text-[11px] text-ink-muted truncate">
                    {demografica ? supInfo.descripcion : capaInfo.descripcion}
                  </p>
                </div>
                <Leyenda cortes={cortes} demografica={demografica} formato={supInfo.formato} />
              </div>
              <div className="flex-1 min-h-0">
                <Mapa
                  datos={datos} turno={turno} capa={capa} superficie={superficie} tipo={tipo} comuna={comuna}
                  barrioActivo={barrio} kPatrullas={kPatrullas} tema={tema}
                  onBarrio={elegirBarrio}
                />
              </div>
              <AvisoSuperficie tipo={tipo} capa={capa} superficie={superficie} />
              {capa !== "ninguna" && <LeyendaPuntos capa={capa} k={kPatrullas} />}
            </section>

            <div className="flex flex-col gap-3 min-w-0">
              <section className="card p-3">
                <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                  Riesgo medio por comuna
                </h3>
                <p className="text-[11px] text-ink-muted mb-2">
                  Delitos esperados en una zona de 700 m durante el turno{" "}
                  {turno === "manana" ? "mañana" : turno}, ×100 para que se lean.
                  Clic para filtrar todo el tablero.
                </p>
                <BarrasComuna comunas={datos.comunas} turno={turno} tipo={tipo} seleccion={comuna}
                              onSeleccion={elegirComuna} />
              </section>

              <Cuando perfil={datos.perfil} tipo={tipo}
                      delitosSeleccion={delitosFoco} ambito={ambito} />
            </div>
          </div>

          <section className="card overflow-hidden max-h-[30rem] flex flex-col">
            <TablaBarrios barrios={props} turno={turno} tipo={tipo} comuna={comuna}
                          barrioActivo={barrio} onBarrio={elegirBarrio} />
          </section>
        </AnclaSeccion>

        <AnclaSeccion id="que-hacer" titulo="Qué hacer"
                      bajada="Los módulos de decisión, y a quién alcanzan">
          <div className="grid gap-3 lg:grid-cols-2">
            <section className="card p-3">
              <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                Cobertura según cantidad de patrullas
              </h3>
              <p className="text-[11px] text-ink-muted mb-2">
                Cada punto es una optimización completa, no una interpolación. Clic para fijar el escenario.
              </p>
              <CurvaCobertura curva={datos.curvaK} pob={datos.coberturaPob}
                              kActual={kPatrullas} onK={setKPatrullas} />
              <div className="mt-2 flex flex-col gap-2.5">
                <BrechaCobertura pob={datos.coberturaPob} kActual={kPatrullas} />
                <Vulnerables pob={datos.coberturaPob} kActual={kPatrullas} />
              </div>
            </section>

            <div className="flex flex-col gap-3 min-w-0">
              <Equidad datos={datos.equidad} kPatrullas={kPatrullas} />

              {/* pegado a los otros dos y no al final: es lo que hay que leer
                  antes de tomar las ubicaciones del mapa como un plan */}
              <section className="card p-3">
                <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                  Si el radio no fuera {datos.curvaK.radio_m} m
                </h3>
                <p className="text-[11px] text-ink-muted mb-2">
                  La ganancia aguanta en todo el barrido. Las ubicaciones no: fuera
                  de {datos.curvaK.radio_m} m, casi ninguna se repite.
                </p>
                <SensibilidadAlRadio datos={datos.radio} />
              </section>
            </div>
          </div>
        </AnclaSeccion>

        <AnclaSeccion id="quienes" titulo="Quiénes"
                      bajada="Quién vive en cada zona y quién aparece como víctima">
          <Poblacion
            datos={datos.demografia} comuna={comuna} barrio={barrio}
            onComuna={setComuna} onBarrio={elegirBarrio}
          />
          <Victimas datos={datos.victimas} />
        </AnclaSeccion>

        <AnclaSeccion id="que-viene" titulo="Qué viene"
                      bajada="Lo registrado y la proyección, en la misma línea">
          <div className="grid gap-3 lg:grid-cols-2">
            <section className="card p-3">
              <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
                Delitos por mes y tipo
              </h3>
              <SerieAnual serie={datos.serie} tipo={tipo} onTipo={setTipo} />
            </section>

            <Pronostico datos={datos.pronostico} serie={datos.serie} tipo={tipo} />
          </div>

          <Salvedades items={datos.resumen.salvedades} />
        </AnclaSeccion>
      </div>
    </main>
  );
}
