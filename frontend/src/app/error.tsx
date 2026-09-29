"use client"; // Error boundaries have to be client components

import { useEffect } from "react";

type ErrorProps = {
  error: Error & { digest?: string };
  // Re-renders the segment. Worth offering, because the cause is often a request that failed once
  retry: () => void;
};

export default function AppError({ error, retry }: ErrorProps) {
  useEffect(() => {
    // The browser console is the only place this goes for now. When there's somewhere to send it,
    // this is the line that reports it
    console.error("Itinera crashed:", error);
  }, [error]);

  return (
    <div className="flex min-h-dvh items-center justify-center px-6 py-16">
      <div className="w-full max-w-md">
        <p className="eyebrow">Something went wrong</p>

        <h1 className="mt-4 font-display text-[clamp(2rem,4vw,2.75rem)] leading-tight tracking-[-0.015em] text-ink">
          That didn&apos;t go to plan.
        </h1>

        <p className="mt-4 text-base leading-[1.65] text-muted">
          The page hit an error it couldn&apos;t recover from on its own. Your trips are saved, so
          nothing is lost — trying again usually works.
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <button type="button" className="btn-solid" onClick={() => retry()}>
            Try again
          </button>
          {/* A full document load, deliberately. The router's own navigation isn't enough here:
              / and /?thread=x are the same route segment, so the boundary stays mounted, and the
              reply that can't be rendered is still in memory waiting to throw again. Throwing the
              whole page away is the only reliable way out, which is why the usual rule against
              this doesn't apply inside an error boundary */}
          <button
            type="button"
            className="btn-outline"
            // eslint-disable-next-line @next/next/no-location-assign-relative-destination
            onClick={() => window.location.assign("/")}
          >
            Start a new trip
          </button>
        </div>

        {/* A server error's message is withheld from the browser on purpose; the digest is what ties
            it to the line in the server's log */}
        {error.digest && (
          <p className="mt-8 border-t border-line pt-4 text-[11px] leading-relaxed text-faint">
            If you report this, quote <span className="font-mono text-muted">{error.digest}</span>.
          </p>
        )}
      </div>
    </div>
  );
}
