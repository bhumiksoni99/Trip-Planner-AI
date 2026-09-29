"use client"; // Error boundaries have to be client components

import { useEffect } from "react";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  retry: () => void;
};

// The last resort: this replaces the root layout, so it renders its own document and — unlike
// error.tsx — gets none of the app's global styles or fonts. Everything here is inline for that
// reason, and it follows the operating system's light or dark setting rather than the app's theme.
const ink = "#14161a";
const canvas = "#f6f4ef";

export default function GlobalError({ error, retry }: GlobalErrorProps) {
  useEffect(() => {
    console.error("Itinera crashed before it could render:", error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, background: canvas, color: ink, fontFamily: "system-ui, sans-serif" }}>
        <title>Itinera AI — something went wrong</title>

        <main
          style={{
            minHeight: "100dvh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "4rem 1.5rem",
          }}
        >
          <div style={{ maxWidth: "28rem" }}>
            <p style={{ margin: 0, fontSize: "0.6875rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8b8f96" }}>
              Something went wrong
            </p>

            <h1 style={{ margin: "1rem 0 0", fontSize: "2rem", lineHeight: 1.15, letterSpacing: "-0.015em" }}>
              That didn&apos;t go to plan.
            </h1>

            <p style={{ margin: "1rem 0 0", fontSize: "1rem", lineHeight: 1.65, color: "#5c6169" }}>
              Itinera couldn&apos;t load. Your trips are saved, so nothing is lost — trying again
              usually works.
            </p>

            <button
              type="button"
              onClick={() => retry()}
              style={{
                marginTop: "1.75rem",
                padding: "0.8rem 1.25rem",
                fontSize: "0.875rem",
                fontWeight: 600,
                color: canvas,
                background: ink,
                border: "none",
                borderRadius: "2px",
                cursor: "pointer",
              }}
            >
              Try again
            </button>

            {error.digest && (
              <p style={{ margin: "2rem 0 0", paddingTop: "1rem", borderTop: "1px solid #e6e2da", fontSize: "0.6875rem", color: "#8b8f96" }}>
                If you report this, quote{" "}
                <span style={{ fontFamily: "ui-monospace, monospace", color: "#5c6169" }}>{error.digest}</span>.
              </p>
            )}
          </div>
        </main>
      </body>
    </html>
  );
}
