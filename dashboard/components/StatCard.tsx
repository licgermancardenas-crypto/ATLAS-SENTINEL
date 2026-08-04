interface Props {
  label: string;
  value: string;
  delta?: { label: string; positivo: boolean };
}

export default function StatCard({ label, value, delta }: Props) {
  return (
    <div className="bg-surface-2 border border-border rounded-lg px-4 py-3 flex flex-col gap-1">
      <span className="text-xs text-text-secondary uppercase tracking-wide">{label}</span>
      <span className="text-2xl font-mono font-semibold tabular-nums">{value}</span>
      {delta && (
        <span
          className={`text-xs font-mono ${delta.positivo ? "text-status-good" : "text-text-secondary"}`}
        >
          {delta.label}
        </span>
      )}
    </div>
  );
}
