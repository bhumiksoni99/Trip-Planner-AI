import type { BriefTerm } from "@/lib/api";

export default function PlanBrief({ terms }: { terms: BriefTerm[] }) {
  if (!terms.length) return null;

  const assumedCount = terms.filter((term) => term.assumed).length;

  // An unfilled cell would show the grid's line colour, so pad the last row out.
  // The count differs per breakpoint: two columns on phones, three from sm up.
  const mobileFillers = (2 - (terms.length % 2)) % 2;
  const desktopFillers = (3 - (terms.length % 3)) % 3;
  const fillers = Array.from({ length: Math.max(mobileFillers, desktopFillers) }, (_, index) => ({
    key: index,
    className: `${index < mobileFillers ? "block" : "hidden"} ${index < desktopFillers ? "sm:block" : "sm:hidden"}`,
  }));

  return (
    <section className="mb-6">
      <p className="text-sm text-muted">
        The brief we planned against
        {assumedCount > 0 && <> — what you didn&apos;t tell us is shown in amber, so you can correct it below.</>}
      </p>

      {/* A fixed column count, so the last row never leaves an empty cell */}
      <div className="mt-3 grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3">
        {terms.map((term) => (
          <div key={term.label} className={term.assumed ? "bg-assumed px-4 py-3.5" : "bg-surface px-4 py-3.5"}>
            <p
              className={`text-[11px] font-semibold tracking-[0.12em] uppercase ${
                term.assumed ? "text-assumed-ink" : "text-faint"
              }`}
            >
              {term.label}
              {term.assumed && " · assumed"}
            </p>
            <p className={`mt-1 text-sm font-medium ${term.assumed ? "text-assumed-ink" : "text-ink"}`}>
              {term.value}
            </p>
          </div>
        ))}

        {fillers.map((filler) => (
          <div key={`filler-${filler.key}`} aria-hidden className={`bg-surface ${filler.className}`} />
        ))}
      </div>
    </section>
  );
}
