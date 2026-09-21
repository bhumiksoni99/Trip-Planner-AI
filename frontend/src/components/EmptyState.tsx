import { ArrowRightIcon, GlobeIcon } from "./icons";

// The backend plans from Delhi unless the traveller says otherwise
const ORIGIN = "Delhi";

const ROUTES = [
  {
    name: "Dubai",
    code: "DXB",
    icon: "🏙️",
    blurb: "5 days · Downtown base, desert evening",
    prompt: "Plan a 5 days Dubai trip from Delhi with flights, hotels and sightseeing.",
  },
  {
    name: "Japan",
    code: "HND",
    icon: "🗾",
    blurb: "7 days · Tokyo and Kyoto by rail",
    prompt: "Plan a complete 7 days Japan trip from Delhi including flights, hotels and sightseeing under 2 lakhs.",
  },
  {
    name: "Thailand",
    code: "BKK",
    icon: "🏝️",
    blurb: "7 days · Bangkok, then the islands",
    prompt: "Plan a 7 days Thailand trip from Delhi with budget hotels and sightseeing.",
  },
];

const OPEN_PROMPT = "Suggest three destinations for a week away from Delhi, then plan the one that fits my budget best.";

export default function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-14 sm:px-10">
      <p className="eyebrow">New trip</p>
      <h2 className="mt-4 font-display text-[clamp(2.75rem,5.2vw,4.5rem)] leading-none tracking-[-0.015em] text-balance text-ink">
        Plan the trip.
        <br />
        <em className="italic text-accent">We&apos;ll handle the rest.</em>
      </h2>
      <p className="mt-5 max-w-[46ch] text-base leading-[1.65] text-muted">
        Tell us where you&apos;re headed and roughly when, in the box below. We compare live fares, find a place to
        stay, and return one day-by-day itinerary you can book in a sitting.
      </p>

      <button
        type="button"
        className="btn-solid mt-7"
        onClick={() => document.getElementById("composer")?.focus()}
      >
        Describe a trip
      </button>

      <section className="mt-14 flex items-baseline justify-between gap-4 border-b border-ink pb-3.5">
        <h3 className="font-display text-[28px] tracking-[-0.01em] text-ink">Or start from a route</h3>
        <p className="text-xs font-medium text-faint">From {ORIGIN}</p>
      </section>

      <section className="grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-px border border-t-0 border-line bg-line">
        {ROUTES.map((route) => (
          <button key={route.name} type="button" className="route-card" onClick={() => onPick(route.prompt)}>
            <span aria-hidden className="flex h-[120px] items-center justify-center bg-raised text-4xl">
              {route.icon}
            </span>
            <span className="block px-5 pt-4.5 pb-5.5">
              <span className="flex items-baseline justify-between gap-2">
                <span className="font-display text-2xl leading-none text-ink">{route.name}</span>
                <span className="text-xs font-medium text-faint">{route.code}</span>
              </span>
              <span className="mt-2 block text-[13px] leading-normal text-muted">{route.blurb}</span>
            </span>
          </button>
        ))}

        <button type="button" className="route-card route-card-accent" onClick={() => onPick(OPEN_PROMPT)}>
          <span aria-hidden className="flex h-[120px] items-end p-5 text-accent-soft">
            <GlobeIcon />
          </span>
          <span className="block px-5 pt-4.5 pb-5.5">
            <span className="block font-display text-2xl leading-none">Open to anywhere</span>
            <span className="mt-2 block text-[13px] leading-normal opacity-80">
              Give us a budget and a week. We&apos;ll shortlist three.
            </span>
            <span className="mt-2.5 flex items-center gap-1.5 text-[13px] font-semibold">
              Start with a budget
              <ArrowRightIcon className="size-3" />
            </span>
          </span>
        </button>
      </section>
    </div>
  );
}
