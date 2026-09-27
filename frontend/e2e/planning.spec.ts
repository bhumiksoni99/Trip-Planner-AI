import { expect, test } from "@playwright/test";

import { ask, cards, composer, reset, waitForPlan } from "./app";

test.beforeEach(async ({ request }) => reset(request));

test("a trip missing its details is asked about, and the card survives a refresh", async ({ page }) => {
  await page.goto("/");

  // No dates and no length, so the run pauses at intake rather than guessing
  await ask(page, "Plan a trip to Tokyo");

  await expect(page.getByText("Question 1 of 2")).toBeVisible();
  await expect(page.getByText("When are you going?")).toBeVisible();

  // The pause lives in the checkpoint, not the tab, so a refresh mid-intake brings it back
  await page.reload();
  await expect(page.getByText("Question 1 of 2")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("When are you going?")).toBeVisible();

  // Answer both questions: the first from the offered options, the second typed
  await page.getByRole("button", { name: "Next month" }).click();
  await expect(page.getByText("Question 2 of 2")).toBeVisible();
  await page.getByLabel("Or type your own answer").fill("5 days");
  await page.getByRole("button", { name: "Done" }).click();

  // What the traveller answered is shown back as their own message
  await expect(page.getByText("travel dates: Next month")).toBeVisible();
  await waitForPlan(page);
  await expect(cards.days(page)).toBeVisible();
});

test("the questions can be skipped, and the trip is planned anyway", async ({ page }) => {
  await page.goto("/");
  await ask(page, "Plan a trip to Tokyo");

  await expect(page.getByText("Question 1 of 2")).toBeVisible();
  await page.getByRole("button", { name: "Skip all, just plan it" }).click();

  await waitForPlan(page);
  await expect(page.getByText("Question 1 of 2")).toHaveCount(0);
});

test("the checklist ticks through the agents, then the plan renders with its cards", async ({ page }) => {
  await page.goto("/");
  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");

  const checklist = page.getByRole("list", { name: "Planning progress" });
  await expect(checklist).toBeVisible();

  // The agents the supervisor picked, in the order they run — and the steps that aren't the
  // traveller's business are not among them
  await expect(checklist).toContainText("Finding flights");
  await expect(checklist).toContainText("Writing the itinerary");
  await expect(checklist).toContainText("Putting your plan together");
  await expect(checklist).not.toContainText("photo");

  await waitForPlan(page);

  await expect(cards.header(page)).toBeVisible();
  await expect(cards.hotels(page)).toBeVisible();
  await expect(cards.days(page)).toBeVisible();
  await expect(cards.costs(page)).toBeVisible();
  // The markers the write-up leaves for the cards are replaced, never shown
  await expect(page.getByText("[[")).toHaveCount(0);
});

test("a hotels-only answer shows hotels and no day-by-day plan", async ({ page }) => {
  await page.goto("/");

  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");
  await waitForPlan(page);
  await expect(cards.days(page)).toBeVisible();

  // Asking only about the hotels re-runs only the hotels: the itinerary isn't rewritten, and the
  // reply carries no day cards for the UI to put back underneath it
  await ask(page, "make the hotels cheaper, 3 star at most");
  await expect(page.getByText("Cheaper places in Tokyo.")).toBeVisible({ timeout: 20_000 });

  const reply = page.locator("main article, main .whitespace-pre-wrap").last();
  await expect(reply).toBeVisible();

  // The new reply has hotels but no day-by-day plan; the earlier full plan still has its own
  await expect(cards.days(page)).toHaveCount(1);
  await expect(page.getByText("Hotel Gracery")).toHaveCount(2);
});

test("the trip that's open is in the URL, so a link goes back to it", async ({ page }) => {
  await page.goto("/");
  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");
  await waitForPlan(page);

  await expect(page).toHaveURL(/\?thread=[0-9a-f]{32}/);
  const url = page.url();

  await page.goto("/");
  await expect(cards.days(page)).toHaveCount(0);

  await page.goto(url);
  await expect(cards.days(page)).toBeVisible({ timeout: 15_000 });
});

test("the composer won't send an empty message", async ({ page }) => {
  await page.goto("/");

  await composer(page).fill("   ");
  await composer(page).press("Enter");

  await expect(page.getByRole("list", { name: "Planning progress" })).toHaveCount(0);
});
