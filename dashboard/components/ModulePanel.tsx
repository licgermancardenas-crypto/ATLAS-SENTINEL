import type { ModuloC } from "@/lib/types";

interface Toggle {
  key: string;
  label: string;
  color: string;
  checked: boolean;
}

interface Props {
  toggles: Toggle[];
  onToggle: (key: string) => void;
  moduloC: ModuloC[];
}

export default function ModulePanel({ toggles, onToggle, moduloC }: Props) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h3 className="text-sm font-semibold mb-2">Capas</h3>
        <div className="flex flex-col gap-2">
          {toggles.map((t) => (
            <label key={t.key} className="flex items-center gap-2 cursor-pointer text-sm select-none">
              <input
                type="checkbox"
                checked={t.checked}
                onChange={() => onToggle(t.key)}
                className="w-4 h-4 accent-[var(--risk-400)] cursor-pointer"
              />
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: t.color }} />
              {t.label}
            </label>
          ))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Módulo C — controles de acceso</h3>
        {/* "por hexágono" no es un detalle: los corredores varían 7,3x en tamaño,
            así que el total crudo premiaba al corredor grande por ser grande */}
        <p className="text-xs text-text-secondary mb-2">
          Ranking por siniestros y riesgo delictivo del corredor, ambos medidos por hexágono.
        </p>
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-text-secondary text-left border-b border-border">
              <th className="py-1 font-normal">#</th>
              <th className="font-normal">Acceso</th>
              <th className="font-normal text-right">Sin./hex</th>
              <th className="font-normal text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {moduloC.slice(0, 6).map((m) => (
              <tr key={m.nombre} className="border-b border-border/50">
                <td className="py-1.5 text-text-secondary">{m.ranking}</td>
                <td className="py-1.5">
                  {m.nombre}
                  {m.n_accesos_agrupados > 1 && (
                    <span className="text-text-secondary"> ({m.n_accesos_agrupados} accesos)</span>
                  )}
                  <div className="text-text-secondary">{m.autopista}</div>
                </td>
                <td className="py-1.5 text-right tabular-nums">{Math.round(m.accidentalidad_por_hex)}</td>
                <td className="py-1.5 text-right tabular-nums">{m.score_control.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
