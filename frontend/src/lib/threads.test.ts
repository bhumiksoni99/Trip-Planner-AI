import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatDetail, ChatSummary } from "./api";

vi.mock("./api", () => ({
  claimChats: vi.fn(),
  deleteChat: vi.fn(),
  listChats: vi.fn(),
  loadChat: vi.fn(),
}));

const GUEST_KEY = "itinera:guest-chats";

/** The store keeps who is signed in and the current list in module state, so each test gets its own. */
async function load() {
  vi.resetModules();
  const api = vi.mocked(await import("./api"));
  const threads = await import("./threads");
  return { api, ...threads };
}

const summary = (id: string, title: string): ChatSummary => ({ id, title, updatedAt: 1 });

const guestChats = (): ChatSummary[] => JSON.parse(localStorage.getItem(GUEST_KEY) ?? "[]");

beforeEach(() => localStorage.clear());

describe("a guest", () => {
  it("lists the chats this browser started", async () => {
    localStorage.setItem(GUEST_KEY, JSON.stringify([summary("a", "Lisbon trip"), summary("b", "Porto")]));
    const store = await load();

    const { result } = renderHook(() => store.useThreads());
    await waitFor(() => expect(result.current).toHaveLength(2));

    expect(result.current.map((thread) => thread.title)).toEqual(["Lisbon trip", "Porto"]);
    // The sidebar entry carries no messages until the chat is opened and fetched
    expect(result.current[0].messages).toEqual([]);
  });

  it("tells the sidebar as soon as a chat is added", async () => {
    const store = await load();
    const { result } = renderHook(() => store.useThreads());
    await waitFor(() => expect(result.current).toEqual([]));

    act(() => void store.createThread("Plan a trip to Lisbon"));

    expect(result.current.map((thread) => thread.title)).toEqual(["Plan a trip to Lisbon"]);
  });

  it("remembers a new chat, so it is still listed after a refresh", async () => {
    const store = await load();
    await store.refreshThreads();

    const id = store.createThread("Plan a trip to Lisbon");

    expect(guestChats()).toEqual([{ id, title: "Plan a trip to Lisbon", updatedAt: expect.any(Number) }]);
  });

  it("shortens a long first message into a title", async () => {
    const store = await load();
    await store.refreshThreads();

    store.createThread("x".repeat(80));
    const [chat] = guestChats();

    expect(chat.title).toHaveLength(58); // 57 characters and the ellipsis
    expect(chat.title.endsWith("…")).toBe(true);
  });

  it("never asks the server for a list", async () => {
    const store = await load();
    await store.refreshThreads();
    expect(store.api.listChats).not.toHaveBeenCalled();
  });

  it("forgets a deleted chat without calling the server", async () => {
    localStorage.setItem(GUEST_KEY, JSON.stringify([summary("a", "Lisbon"), summary("b", "Porto")]));
    const store = await load();
    await store.refreshThreads();

    await store.deleteThread("a");

    expect(guestChats().map((chat) => chat.id)).toEqual(["b"]);
    expect(store.api.deleteChat).not.toHaveBeenCalled();
  });

  it("keeps the ids from chats saved before the database was the only source", async () => {
    // The old key held whole conversations; only the ids and titles are worth keeping, since the
    // messages themselves are already in the database under the same ids
    localStorage.setItem(
      "itinera:threads",
      JSON.stringify([{ id: "old", title: "Tokyo", updatedAt: 5, messages: [{ id: "m", role: "user", content: "hi" }] }]),
    );
    const store = await load();

    await store.refreshThreads();

    expect(guestChats()).toEqual([{ id: "old", title: "Tokyo", updatedAt: 5 }]);
    expect(localStorage.getItem("itinera:threads")).toBeNull();
  });

  it("starts with an empty sidebar when storage is unreadable", async () => {
    localStorage.setItem(GUEST_KEY, "{ not json");
    const store = await load();

    await expect(store.refreshThreads()).resolves.toBeUndefined();
  });
});

describe("a signed-in traveller", () => {
  it("lists the account's chats from the server", async () => {
    const store = await load();
    store.api.listChats.mockResolvedValue([summary("a", "Tokyo"), summary("b", "Kyoto")]);

    store.setAccount("user-1");
    await vi.waitFor(() => expect(store.api.listChats).toHaveBeenCalled());
  });

  it("keeps the sidebar as it is when the request fails", async () => {
    const store = await load();
    store.api.listChats.mockRejectedValue(new Error("offline"));

    store.setAccount("user-1");
    await expect(store.refreshThreads()).resolves.toBeUndefined();
  });

  it("doesn't save new chats to this browser, since the backend records them", async () => {
    const store = await load();
    store.api.listChats.mockResolvedValue([]);
    store.setAccount("user-1");
    await store.refreshThreads();

    store.createThread("Plan a trip to Lisbon");

    expect(guestChats()).toEqual([]);
  });

  it("asks the server to delete a chat, and puts it back if that fails", async () => {
    const store = await load();
    store.api.listChats.mockResolvedValue([summary("a", "Tokyo")]);
    store.setAccount("user-1");
    await store.refreshThreads();

    store.api.deleteChat.mockRejectedValue(new Error("nope"));
    await expect(store.deleteThread("a")).rejects.toThrow("nope");

    store.api.deleteChat.mockResolvedValue({ id: "a" });
    await expect(store.deleteThread("a")).resolves.toBeUndefined();
    expect(store.api.deleteChat).toHaveBeenCalledWith("a");
  });
});

describe("logging in", () => {
  it("hands this browser's chats to the account, then empties the local list", async () => {
    localStorage.setItem(GUEST_KEY, JSON.stringify([summary("a", "Lisbon"), summary("b", "Porto")]));
    const store = await load();
    await store.refreshThreads();

    store.api.claimChats.mockResolvedValue({ claimed: ["a", "b"] });
    store.api.listChats.mockResolvedValue([]);
    store.setAccount("user-1");
    await store.claimGuestChats();

    expect(store.api.claimChats).toHaveBeenCalledWith(["a", "b"]);
    expect(guestChats()).toEqual([]);
  });

  it("keeps the list for another try when claiming fails", async () => {
    localStorage.setItem(GUEST_KEY, JSON.stringify([summary("a", "Lisbon")]));
    const store = await load();
    await store.refreshThreads();

    store.api.claimChats.mockRejectedValue(new Error("offline"));
    await store.claimGuestChats();

    expect(guestChats()).toHaveLength(1);
  });

  it("asks for nothing when this browser has no chats", async () => {
    const store = await load();
    await store.refreshThreads();

    await store.claimGuestChats();

    expect(store.api.claimChats).not.toHaveBeenCalled();
  });
});

describe("opening a chat", () => {
  it("drops it from the sidebar when it is gone or someone else's", async () => {
    localStorage.setItem(GUEST_KEY, JSON.stringify([summary("a", "Lisbon"), summary("b", "Porto")]));
    const store = await load();
    await store.refreshThreads();

    store.api.loadChat.mockResolvedValue(null);
    await expect(store.loadThread("a")).resolves.toBeNull();

    expect(guestChats().map((chat) => chat.id)).toEqual(["b"]);
  });

  it("returns the chat's messages and whatever it is paused on", async () => {
    localStorage.setItem(GUEST_KEY, JSON.stringify([summary("a", "Lisbon")]));
    const store = await load();
    await store.refreshThreads();

    const detail: ChatDetail = {
      id: "a",
      title: "Lisbon",
      updatedAt: 9,
      messages: [{ id: "m1", role: "user", content: "plan a trip" }],
      pause: null,
    };
    store.api.loadChat.mockResolvedValue(detail);

    await expect(store.loadThread("a")).resolves.toEqual(detail);
  });
});

describe("newId", () => {
  it("looks like the thread ids the backend checkpoints under", async () => {
    const { newId } = await load();
    expect(newId()).toMatch(/^[0-9a-f]{32}$/);
    expect(newId()).not.toBe(newId());
  });
});
