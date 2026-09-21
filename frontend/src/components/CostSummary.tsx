import type { PlanCosts } from "@/lib/api";

export default function CostSummary({ costs }: { costs: PlanCosts }) {
  if (!costs.lines.length && !costs.total) return null;

  const overBudget = costs.percent !== null && costs.percent > 100;

  return (
    <section className="my-6 break-inside-avoid border border-line bg-surface">
      <header className="border-b border-line px-5 py-3.5">
        <h4 className="text-sm font-semibold text-ink">Cost summary</h4>
      </header>

      {costs.lines.map((line) => (
        <div key={line.label} className="flex items-baseline justify-between gap-6 border-b border-line px-5 py-3">
          <div className="min-w-0">
            <p className="text-sm text-ink">{line.label}</p>
            {line.note && <p className="mt-0.5 text-xs leading-snug text-faint">{line.note}</p>}
          </div>
          <p className="shrink-0 text-sm text-ink tabular-nums">{line.amount}</p>
        </div>
      ))}

      {costs.total && (
        <div className="border-t border-ink px-5 py-3.5">
          <div className="flex items-baseline justify-between gap-6">
            <p className="text-sm font-semibold text-ink">Total</p>
            <p className="shrink-0 font-semibold text-ink tabular-nums">{costs.total}</p>
          </div>

          {costs.percent !== null && costs.ceiling && (
            <div className="mt-2.5 flex items-center gap-4">
              <p className={`shrink-0 text-xs ${overBudget ? "text-assumed-ink" : "text-faint"}`}>
                {costs.percent}% of a {costs.ceiling} budget
              </p>
              <div aria-hidden className="h-1 min-w-0 flex-1 bg-line">
                <div
                  className={`h-full ${overBudget ? "bg-assumed-ink" : "bg-accent"}`}
                  style={{ width: `${Math.min(costs.percent, 100)}%` }}
                />
              </div>
            </div>
          )}

          <p className="mt-2 text-xs text-faint">
            Estimated per person. No fares come back with the flight data, so treat these as a guide.
          </p>
        </div>
      )}
    </section>
  );
}
