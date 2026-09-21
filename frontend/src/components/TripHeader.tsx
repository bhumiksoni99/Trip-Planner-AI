"use client";

import { useState } from "react";
import type { PlanHeader } from "@/lib/api";

export default function TripHeader({ header }: { header: PlanHeader }) {
  // Search photos come from whoever hosts them, so one can still fail in the browser
  const [photoFailed, setPhotoFailed] = useState(false);
  const showPhoto = Boolean(header.image) && !photoFailed;

  const subtitle = [header.dates, header.duration, header.origin && `from ${header.origin}`]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="mb-6 break-inside-avoid">
      {header.summary && <p className="mb-4 text-base leading-[1.6] text-ink">{header.summary}</p>}

      <div className={`grid border border-line bg-surface ${showPhoto ? "sm:grid-cols-2" : ""}`}>
        <div className="flex flex-col justify-between gap-8 px-6 py-6">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.12em] text-faint uppercase">Itinerary</p>
            <h3 className="mt-2 font-display text-[clamp(2.25rem,4vw,3.25rem)] leading-none tracking-[-0.015em] text-ink">
              {header.destination}
            </h3>
            {subtitle && <p className="mt-2.5 text-sm text-muted">{subtitle}</p>}
          </div>

          {header.total && (
            <div>
              {/* Never a quote: the flight data carries no fares, so this is the budget agent's estimate */}
              <p className="text-[11px] font-semibold tracking-[0.1em] text-faint uppercase">Estimated total</p>
              <p className="mt-1 text-xl font-semibold text-ink">{header.total}</p>
            </div>
          )}
        </div>

        {showPhoto && (
          // A remote search result, so a plain img rather than next/image
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={header.image}
            alt={header.destination}
            loading="lazy"
            className="h-full max-h-[260px] min-h-[200px] w-full border-line object-cover sm:border-l"
            onError={() => setPhotoFailed(true)}
          />
        )}
      </div>

      {header.total && (
        <p className="mt-2 text-xs text-faint">Total is an estimate per person. Check prices before booking.</p>
      )}
    </section>
  );
}
