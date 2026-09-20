import { useSyncExternalStore } from "react";

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  error?: boolean;
};

export type Thread = {
  // Also sent to the backend as `thread_id`, so its LangGraph checkpoints use the same ID
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
};

// Threads live in this browser's localStorage; the backend has no endpoint to list them yet
const STORAGE_KEY = "tripmate:threads";
const NO_THREADS: Thread[] = [];
const listeners = new Set<() => void>();
let threads: Thread[] | null = null;

function load(): Thread[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? (JSON.parse(saved) as Thread[]) : [];
  } catch {
    return [];
  }
}

function getSnapshot() {
  threads ??= load();
  return threads;
}

function getServerSnapshot() {
  return NO_THREADS;
}

function subscribe(listener: () => void) {
  listeners.add(listener);

  // Pick up changes made in other tabs
  function handleStorage(event: StorageEvent) {
    if (event.key !== STORAGE_KEY) return;
    threads = load();
    listener();
  }
  window.addEventListener("storage", handleStorage);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", handleStorage);
  };
}

function update(change: (current: Thread[]) => Thread[]) {
  threads = change(getSnapshot());
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
  } catch {
    // Storage can be full or blocked; the threads still work for this session
  }
  listeners.forEach((listener) => listener());
}

export function useThreads() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

// 32 hex characters, like Python's uuid4().hex. crypto.randomUUID() only exists on HTTPS or localhost.
export function newId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function createThread(firstMessage: string): string {
  const id = newId();
  const title = firstMessage.length > 60 ? `${firstMessage.slice(0, 57).trimEnd()}…` : firstMessage;
  update((current) => [{ id, title, messages: [], updatedAt: Date.now() }, ...current]);
  return id;
}

export function addMessage(threadId: string, message: Omit<Message, "id">) {
  update((current) =>
    current.map((thread) =>
      thread.id === threadId
        ? { ...thread, messages: [...thread.messages, { ...message, id: newId() }], updatedAt: Date.now() }
        : thread,
    ),
  );
}

export function removeLastMessage(threadId: string) {
  update((current) =>
    current.map((thread) =>
      thread.id === threadId ? { ...thread, messages: thread.messages.slice(0, -1) } : thread,
    ),
  );
}

export function deleteThread(threadId: string) {
  update((current) => current.filter((thread) => thread.id !== threadId));
}
