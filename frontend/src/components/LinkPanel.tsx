"use client";

import { useEffect, useState } from "react";
import { fetchPlacePreview, type PlacePreview } from "@/lib/api";
import { CloseIcon } from "./icons";

export type OpenLink = {
  href: string;
  label: string;
};

// Google, Kayak and most travel sites refuse to be framed, so the preview is built from search results instead
function searchQuery(link: OpenLink) {
  try {
    const url = new URL(link.href);
    const query = url.searchParams.get("q") ?? url.searchParams.get("query");
    if (query) return query.replace(/\+/g, " ");
  } catch {
    // not a url we can read, fall back to the link's own text
  }

  return link.label;
}

function hostOf(href: string) {
  try {
    return new URL(href).hostname.replace(/^www\./, "");
  } catch {
    return href;
  }
}

export default function LinkPanel({ link, onClose }: { link: OpenLink; onClose: () => void }) {
  const query = searchQuery(link);
  const [preview, setPreview] = useState<PlacePreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ChatApp gives the panel a key per link, so each link starts with fresh state
  useEffect(() => {
    let live = true;

    fetchPlacePreview(query)
      .then((result) => live && setPreview(result))
      .catch((err: Error) => live && setError(err.message));

    return () => {
      live = false;
    };
  }, [query]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <>
      <div aria-hidden className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]" onClick={onClose} />

      <aside
        aria-label={link.label}
        className="slide-up fixed inset-x-0 bottom-0 z-50 mx-auto flex h-[85dvh] max-w-6xl flex-col rounded-t-3xl border border-line bg-surface shadow-[var(--composer-shadow)] print:hidden"
      >
        <span aria-hidden className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-line" />

        <header className="flex items-start gap-2 border-b border-line px-4 py-3 sm:px-6">
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-2xl text-ink">{link.label}</p>
            <p className="truncate text-xs text-muted">{hostOf(link.href)}</p>
          </div>
          <a href={link.href} target="_blank" rel="noopener noreferrer" className="action-btn shrink-0">
            Open in Google ↗
          </a>
          <button type="button" className="icon-btn shrink-0" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
          {error && <p className="text-sm text-muted">{error}</p>}

          {!preview && !error && (
            <div aria-hidden className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[0, 1, 2, 3].map((index) => (
                  <div key={index} className="shimmer aspect-4/3 rounded-2xl" />
                ))}
              </div>
              <div className="shimmer h-4 w-2/3 rounded-md" />
              <div className="shimmer h-4 w-1/2 rounded-md" />
            </div>
          )}

          {preview && (
            <>
              {preview.images.length > 0 && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {preview.images.slice(0, 8).map((image) => (
                    // Remote photos from search results, so plain img rather than next/image
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={image.url}
                      src={image.url}
                      alt={image.description ?? link.label}
                      loading="lazy"
                      className="aspect-4/3 w-full rounded-2xl border border-line object-cover"
                      onError={(event) => event.currentTarget.classList.add("hidden")}
                    />
                  ))}
                </div>
              )}

              <ul className="mt-5 space-y-3">
                {preview.results.map((result) => (
                  <li key={result.url} className="rounded-2xl border border-line bg-surface-strong px-4 py-3">
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-accent hover:underline"
                    >
                      {result.title}
                    </a>
                    <p className="mt-0.5 text-xs text-muted">{hostOf(result.url)}</p>
                    <p className="mt-1.5 line-clamp-3 text-sm text-ink">{result.content}</p>
                  </li>
                ))}
              </ul>

              {preview.images.length === 0 && preview.results.length === 0 && (
                <p className="text-sm text-muted">Nothing came back for this one. Try opening it in Google.</p>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}
