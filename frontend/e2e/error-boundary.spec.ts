import { expect, test } from "@playwright/test";

import { ask, composer, reset } from "./app";

test.beforeEach(async ({ request }) => reset(request));

/** Breaks a reply so rendering it throws, which is the crash the boundary exists for. */
async function serveAPoisonedPlan(page: import("@playwright/test").Page) {
  await page.route("**/api/plan", async (route) => {
    // A day with no items: DayPlan guards the list of days but maps day.items straight away, so
    // this throws while rendering — the shape a backend change could plausibly produce
    const done = {
      thread_id: "boom",
      pause_type: null,
      pause_payload: null,
      final_response: "## Trip Overview\n\nHere you go.\n\n[[ITINERARY]]",
      days: [{ label: "Day 1", heading: "Arrive in Tokyo", items: null }],
      hotels: [],
      brief: [],
      costs: null,
      header: null,
    };
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: `event: done\ndata: ${JSON.stringify(done)}\n\n`,
    });
  });
}

test("a crash shows the fallback rather than a blank page", async ({ page }) => {
  await serveAPoisonedPlan(page);
  await page.goto("/");

  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");

  await expect(page.getByText("That didn't go to plan.")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start a new trip" })).toBeVisible();

  // The point of the boundary: something is on screen
  await expect(page.locator("body")).not.toBeEmpty();
});

test("the fallback explains that nothing was lost", async ({ page }) => {
  await serveAPoisonedPlan(page);
  await page.goto("/");
  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");

  await expect(page.getByText(/Your trips are saved/)).toBeVisible({ timeout: 20_000 });
});

test("starting a new trip from the fallback gets back to a working app", async ({ page }) => {
  await serveAPoisonedPlan(page);
  await page.goto("/");
  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");
  await expect(page.getByText("That didn't go to plan.")).toBeVisible({ timeout: 20_000 });

  // The broken reply came from a route that only this test poisoned; dropping it lets the app work
  await page.unroute("**/api/plan");
  await page.getByRole("button", { name: "Start a new trip" }).click();

  await expect(composer(page)).toBeVisible();
  await expect(page.getByText("That didn't go to plan.")).toHaveCount(0);
});
