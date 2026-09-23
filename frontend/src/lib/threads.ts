import { useSyncExternalStore } from "react";
import {
  claimChats,
  deleteChat,
  listChats,
  loadChat,
  type BriefTerm,
  type ChatDetail,
  type ChatSummary,
  type PlanCosts,
  type PlanDay,
  type PlanHeader,
  type PlanHotel,
} from "./api";

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  error?: boolean;
  // The day-by-day plan, rendered as cards above the write-up. Missing on replies made before this existed
  days?: PlanDay[];
  // The shortlisted hotels, rendered as cards in the Hotels section
  hotels?: PlanHotel[];
  // The cost breakdown, rendered as a table in the budget section
  costs?: PlanCosts | null;
  // The plan's title card, shown under the brief
  header?: PlanHeader | null;
  // The terms the plan was made against, shown as a strip at the top of the reply
  brief?: BriefTerm[];
};

export type Thread = {
  // Also sent to the backend as `thread_id`, so its LangGraph checkpoints use the same ID
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
  // Its messages have been fetched, rather than being a sidebar entry we haven't opened yet
  loaded?: boolean;
  // Started in this tab and not planned yet, so the server has never heard of it
  local?: boolean;
};

// The chats themselves live in Postgres, under the same id LangGraph checkpoints them with. A guest's
// browser only remembers which chats it started, so the sidebar can list them; every message is loaded
// from the database. A logged-in traveller's list comes from the server instead.
const GUEST_KEY = "itinera:guest-chats";
// Where whole chats used to be copied before the database became the only source
const COPY_KEYS = ["itinera:threads", "tripmate:threads"];

const NO_THREADS: Thread[] = [];
const listeners = new Set<() => void>();

let threads: Thread[] = NO_THREADS;
let signedInAs: string | null = null;
let started = false;

function announce() {
  listeners.forEach((listener) => listener());
}

function setThreads(next: Thread[]) {
  threads = next;
  announce();
}

function guestList(): ChatSummary[] {
  try {
    const saved = localStorage.getItem(GUEST_KEY);
    if (saved) return JSON.parse(saved) as ChatSummary[];

    // Chats from before the database was the source: keep their ids and titles, drop the copied
    // messages. The conversations themselves are already saved under the same ids
    for (const key of COPY_KEYS) {
      const copies = localStorage.getItem(key);
      if (!copies) continue;
      const list = (JSON.parse(copies) as Thread[]).map(({ id, title, updatedAt }) => ({ id, title, updatedAt }));
      saveGuestList(list);
      COPY_KEYS.forEach((old) => localStorage.removeItem(old));
      return list;
    }
  } catch {
    // Unreadable or blocked storage; the guest simply starts with an empty sidebar
  }
  return [];
}

function saveGuestList(list: ChatSummary[]) {
  try {
    localStorage.setItem(GUEST_KEY, JSON.stringify(list));
  } catch {
    // Storage can be full or blocked; the chats still work for this session
  }
}

function asThreads(list: ChatSummary[]): Thread[] {
  // Keep whatever we've already loaded, so switching chats doesn't refetch every time
  const loaded = new Map(threads.map((thread) => [thread.id, thread]));
  return list.map(({ id, title, updatedAt }) => {
    const known = loaded.get(id);
    return { id, title, updatedAt, messages: known?.messages ?? [], loaded: known?.loaded };
  });
}

/** Reloads the sidebar: the account's chats when logged in, this browser's list when not. */
export async function refreshThreads() {
  if (!signedInAs) {
    setThreads(asThreads(guestList()));
    return;
  }

  try {
    setThreads(asThreads(await listChats()));
  } catch {
    // Offline or a failed request: leave the list as it is rather than emptying the sidebar
  }
}

/** Tells the store who is logged in. Called by the app whenever that changes. */
export function setAccount(userId: string | null) {
  if (signedInAs === userId && started) return;
  signedInAs = userId;
  started = true;
  threads = NO_THREADS;
  void refreshThreads();
}

/** Hands this browser's guest chats to the account just logged into. */
export async function claimGuestChats() {
  const list = guestList();
  if (!list.length) return;

  try {
    await claimChats(list.map((chat) => chat.id));
    saveGuestList([]);
    await refreshThreads();
  } catch {
    // Kept for the next attempt; claiming the same chats twice is harmless
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!started) {
    started = true;
    void refreshThreads();
  }
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return threads;
}

function getServerSnapshot() {
  return NO_THREADS;
}

export function useThreads() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

// 32 hex characters, like Python's uuid4().hex. crypto.randomUUID() only exists on HTTPS or localhost.
export function newId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function titleOf(message: string) {
  return message.length > 60 ? `${message.slice(0, 57).trimEnd()}…` : message;
}

export function createThread(firstMessage: string): string {
  const id = newId();
  const thread: Thread = { id, title: titleOf(firstMessage), messages: [], updatedAt: Date.now(), loaded: true, local: true };
  setThreads([thread, ...threads]);

  // A guest's browser is the only record of which chats are theirs. A logged-in traveller's chat is
  // recorded by the backend when the plan starts
  if (!signedInAs) saveGuestList([{ id, title: thread.title, updatedAt: thread.updatedAt }, ...guestList()]);

  return id;
}

function change(threadId: string, update: (thread: Thread) => Thread) {
  setThreads(threads.map((thread) => (thread.id === threadId ? update(thread) : thread)));
}

export function addMessage(threadId: string, message: Omit<Message, "id"> & { id?: string }) {
  change(threadId, (thread) => ({
    ...thread,
    messages: [...thread.messages, { ...message, id: message.id ?? newId() }],
    updatedAt: Date.now(),
  }));
}

export function removeLastMessage(threadId: string) {
  change(threadId, (thread) => ({ ...thread, messages: thread.messages.slice(0, -1) }));
}

/** Fetches a chat's messages, and whatever question it is paused on, from the database. */
export async function loadThread(threadId: string): Promise<ChatDetail | null> {
  const detail = await loadChat(threadId);

  if (!detail) {
    // Gone, or someone else's
    setThreads(threads.filter((thread) => thread.id !== threadId));
    if (!signedInAs) saveGuestList(guestList().filter((chat) => chat.id !== threadId));
    return null;
  }

  change(threadId, (thread) => ({ ...thread, title: detail.title, messages: detail.messages, updatedAt: detail.updatedAt, loaded: true, local: false }));
  return detail;
}

export async function deleteThread(threadId: string) {
  const previous = threads;
  setThreads(threads.filter((thread) => thread.id !== threadId));

  if (!signedInAs) {
    saveGuestList(guestList().filter((chat) => chat.id !== threadId));
    return;
  }

  try {
    await deleteChat(threadId);
  } catch (error) {
    setThreads(previous); // put it back, since it's still there
    throw error;
  }
}
