import { expect, type Page, type Request } from "@playwright/test";

import { STUB_URL } from "../playwright.config";

/** Wipes the stub backend's world, so each test starts from nothing. */
export async function reset(request: { post: (url: string, options?: object) => Promise<unknown> }) {
  await request.post(`${STUB_URL}/__reset`);
}

/** Plants accounts and chats directly in the stub, for a state a test needs but isn't testing. */
export async function seed(
  request: { post: (url: string, options?: object) => Promise<unknown> },
  data: { users?: object[]; chats?: object[] },
) {
  await request.post(`${STUB_URL}/__seed`, { data });
}

// The sidebar and the home page both offer to log in and show who is signed in, so every account
// query says which one it means rather than matching whichever came first
const aside = (page: Page) => page.getByRole("complementary");
const main = (page: Page) => page.getByRole("main");

export const sidebar = {
  loginButton: (page: Page) => aside(page).getByRole("button", { name: "Log in to keep them" }),
  logoutButton: (page: Page) => aside(page).getByRole("button", { name: "Log out" }),
  signedInAs: (page: Page, email: string) => aside(page).getByText(email),
  chat: (page: Page, title: string) => aside(page).getByRole("button", { name: title, exact: true }),
};

export const home = {
  loginButton: (page: Page) => main(page).getByRole("button", { name: "Log in", exact: true }),
  signedInAs: (page: Page, email: string) => main(page).getByText(email),
};

export const composer = (page: Page) => page.getByPlaceholder("Where to, and roughly when?");

/** Types a trip into the composer and sends it. */
export async function ask(page: Page, message: string) {
  await composer(page).fill(message);
  await composer(page).press("Enter");
}

/** Signs up through the dialog, from whichever button opened it. */
export async function signUp(page: Page, email: string, password = "hunter2hunter2") {
  await page.getByRole("dialog").getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
}

/** Logs in through the dialog. */
export async function logIn(page: Page, email: string, password = "hunter2hunter2") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("dialog").getByRole("button", { name: "Log in", exact: true }).click();
}

export const cards = {
  days: (page: Page) => page.getByRole("heading", { name: "Day by day" }),
  hotels: (page: Page) => page.getByText("Hotel Gracery"),
  costs: (page: Page) => page.getByRole("heading", { name: "Cost summary" }),
  header: (page: Page) => page.getByText("Five days in Tokyo"),
};

/** Waits until a plan has finished streaming and its write-up is on screen. */
export async function waitForPlan(page: Page) {
  await expect(page.getByRole("heading", { name: "Hotels" }).first()).toBeVisible({ timeout: 20_000 });
}

/** A unique email, so tests never collide on the stub's account list. */
export const anEmail = () => `traveller-${Date.now()}-${Math.floor(Math.random() * 1000)}@example.com`;

export const isApiCall = (request: Request, path: string) =>
  request.url().includes(path) && request.method() !== "GET";
