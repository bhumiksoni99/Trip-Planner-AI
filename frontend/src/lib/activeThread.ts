import { useSyncExternalStore } from "react";

// Which trip is open lives in the URL as ?thread=, so a refresh or a copied link reopens it.
// The URL is read through a store, the same way threads read localStorage, which keeps the
// server's render (no thread) and the browser's first render in step.
const PARAM = "thread";
const listeners = new Set<() => void>();

function getSnapshot() {
  return new URLSearchParams(window.location.search).get(PARAM);
}

function getServerSnapshot(): string | null {
  return null;
}

function subscribe(listener: () => void) {
  listeners.add(listener);

  // Back and forward change the URL without going through setActiveThreadId
  window.addEventListener("popstate", listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function useActiveThreadId() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function setActiveThreadId(threadId: string | null) {
  const url = new URL(window.location.href);

  if (threadId) url.searchParams.set(PARAM, threadId);
  else url.searchParams.delete(PARAM);

  // Replace rather than push, so Back leaves the app instead of stepping through every trip opened
  window.history.replaceState(null, "", url);
  listeners.forEach((listener) => listener());
}
