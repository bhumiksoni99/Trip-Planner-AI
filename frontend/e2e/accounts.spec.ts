import { expect, test } from "@playwright/test";

import { anEmail, ask, cards, logIn, reset, seed, sidebar, signUp, waitForPlan } from "./app";

test.beforeEach(async ({ request }) => reset(request));

test("a guest's trip follows them to the account they sign up for", async ({ page }) => {
  await page.goto("/");

  // Plan as a guest: the chat is in the database with no owner, and only this browser knows its id
  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");
  await waitForPlan(page);
  await expect(sidebar.chat(page, "Plan a 5 day trip to Tokyo from Delhi in May")).toBeVisible();
  await expect(sidebar.loginButton(page)).toBeVisible();

  const email = anEmail();
  await sidebar.loginButton(page).click();
  await signUp(page, email);

  // The sidebar now belongs to the account, and the guest's trip came with it
  await expect(sidebar.signedInAs(page, email)).toBeVisible();
  await expect(sidebar.chat(page, "Plan a 5 day trip to Tokyo from Delhi in May")).toBeVisible();

  // Nothing is left behind in this browser, since the account owns the chat now
  const leftBehind = await page.evaluate(() => localStorage.getItem("itinera:guest-chats"));
  expect(JSON.parse(leftBehind ?? "[]")).toEqual([]);
});

test("logging out empties the sidebar, and logging back in brings it back", async ({ page }) => {
  const email = anEmail();
  await page.goto("/");

  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");
  await waitForPlan(page);
  await sidebar.loginButton(page).click();
  await signUp(page, email);
  await expect(sidebar.chat(page, "Plan a 5 day trip to Tokyo from Delhi in May")).toBeVisible();

  await sidebar.logoutButton(page).click();

  // Back to a guest: the account's chats are not this browser's to see
  await expect(sidebar.loginButton(page)).toBeVisible();
  await expect(sidebar.chat(page, "Plan a 5 day trip to Tokyo from Delhi in May")).toHaveCount(0);

  await sidebar.loginButton(page).click();
  await logIn(page, email);

  await expect(sidebar.signedInAs(page, email)).toBeVisible();
  await expect(sidebar.chat(page, "Plan a 5 day trip to Tokyo from Delhi in May")).toBeVisible();
});

test("the account's trips are there in a browser that has never seen them", async ({ page, browser, request }) => {
  const email = anEmail();
  await seed(request, {
    users: [{ id: "user-9", email, password: "hunter2hunter2", token: "token-9" }],
    chats: [{
      id: "saved-trip", userId: "user-9", title: "Five days in Kyoto", updatedAt: Date.now(),
      messages: [{ id: "m1", role: "user", content: "Five days in Kyoto" }],
    }],
  });

  await page.goto("/");
  await sidebar.loginButton(page).click();
  await logIn(page, email);

  await expect(sidebar.chat(page, "Five days in Kyoto")).toBeVisible();

  // A second browser, same account: this is the whole point of having one
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto("/");
  await sidebar.loginButton(otherPage).click();
  await logIn(otherPage, email);

  await expect(sidebar.chat(otherPage, "Five days in Kyoto")).toBeVisible();
  await other.close();
});

test("a wrong password is refused, and says so", async ({ page, request }) => {
  const email = anEmail();
  await seed(request, { users: [{ id: "user-9", email, password: "the-right-one", token: "token-9" }] });

  await page.goto("/");
  await sidebar.loginButton(page).click();
  await logIn(page, email, "the-wrong-one");

  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Wrong email or password.");
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("staying logged in survives a reload, because the cookie is the server's", async ({ page }) => {
  const email = anEmail();
  await page.goto("/");
  await sidebar.loginButton(page).click();
  await signUp(page, email);
  await expect(sidebar.signedInAs(page, email)).toBeVisible();

  await page.reload();

  // The token lives in an httpOnly cookie the page's own scripts can't read
  await expect(sidebar.signedInAs(page, email)).toBeVisible();
  const readable = await page.evaluate(() => document.cookie);
  expect(readable).not.toContain("itinera_token");
});

test("a signed-in trip and its cards come back after a reload", async ({ page }) => {
  const email = anEmail();
  await page.goto("/");
  await sidebar.loginButton(page).click();
  await signUp(page, email);

  await ask(page, "Plan a 5 day trip to Tokyo from Delhi in May");
  await waitForPlan(page);
  await expect(cards.days(page)).toBeVisible();

  await page.reload();
  await sidebar.chat(page, "Plan a 5 day trip to Tokyo from Delhi in May").click();

  await expect(cards.hotels(page)).toBeVisible();
  await expect(cards.days(page)).toBeVisible();
});
