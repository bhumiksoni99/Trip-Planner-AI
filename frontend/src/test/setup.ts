import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Each test starts with an empty browser: the thread store keeps a guest's chat ids in localStorage,
// and a list left over from one test would show up in the next
beforeEach(() => {
  window.localStorage.clear();
});
