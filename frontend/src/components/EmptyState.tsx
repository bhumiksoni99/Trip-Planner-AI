const SUGGESTIONS = [
  {
    label: "Japan Trip",
    icon: "🗾",
    prompt: "Plan a complete 7 days Japan trip from Delhi including flights, hotels and sightseeing under 2 lakhs.",
  },
  {
    label: "Dubai Trip",
    icon: "🏙️",
    prompt: "Plan a 5 days Dubai trip from Delhi with flights, hotels and sightseeing.",
  },
  {
    label: "Thailand Trip",
    icon: "🏝️",
    prompt: "Plan a 7 days Thailand trip from Delhi with budget hotels and sightseeing.",
  },
  {
    label: "Global Flights",
    icon: "🌍",
    prompt: "Give me all country flight info.",
  },
];

export default function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="relative mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-4 py-10 text-center">
      <div aria-hidden className="hero-glow pointer-events-none absolute inset-x-0 top-1/4 mx-auto h-64 max-w-xl" />

      <span className="brand-mark relative size-12 text-xl">✈️</span>
      <h2 className="relative mt-5 font-display text-4xl leading-tight text-ink sm:text-5xl">
        Where do you want to <span className="text-gradient pr-1 italic">go?</span>
      </h2>
      <p className="relative mt-3 max-w-md text-balance text-muted">
        Tell me where you&apos;re headed. I&apos;ll search flights, find hotels and put together a day-by-day plan.
      </p>

      <div className="relative mt-9 grid w-full gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((suggestion) => (
          <button key={suggestion.label} type="button" className="suggestion" onClick={() => onPick(suggestion.prompt)}>
            <span className="flex items-center gap-2 text-sm font-semibold text-ink">
              <span aria-hidden>{suggestion.icon}</span>
              {suggestion.label}
            </span>
            <span className="line-clamp-2 text-sm text-muted">{suggestion.prompt}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
