"use client";

import { useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { requestPlan } from "@/lib/api";
import { addMessage, createThread, deleteThread, removeLastMessage, useThreads } from "@/lib/threads";
import Composer from "./Composer";
import EmptyState from "./EmptyState";
import { MenuIcon, PlusIcon, SidebarIcon } from "./icons";
import Markdown from "./Markdown";
import MessageList from "./MessageList";
import Sidebar from "./Sidebar";

export default function ChatApp() {
  const threads = useThreads();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set());
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [printContent, setPrintContent] = useState<string | null>(null);

  const sortedThreads = useMemo(() => [...threads].sort((a, b) => b.updatedAt - a.updatedAt), [threads]);
  const activeThread = threads.find((thread) => thread.id === activeId) ?? null;
  const activePending = activeThread ? pendingIds.has(activeThread.id) : false;

  function setPending(threadId: string, pending: boolean) {
    setPendingIds((current) => {
      const next = new Set(current);
      if (pending) next.add(threadId);
      else next.delete(threadId);
      return next;
    });
  }

  async function ask(threadId: string, text: string) {
    setPending(threadId, true);
    try {
      const result = await requestPlan(text, threadId);
      addMessage(threadId, { role: "assistant", content: result.final_response });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong. Please try again.";
      addMessage(threadId, { role: "assistant", content: message, error: true });
    } finally {
      setPending(threadId, false);
    }
  }

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;

    let threadId = activeThread?.id;
    if (!threadId) {
      threadId = createThread(trimmed);
      setActiveId(threadId);
    } else if (pendingIds.has(threadId)) {
      return;
    }

    addMessage(threadId, { role: "user", content: trimmed });
    setDraft("");
    void ask(threadId, trimmed);
  }

  function retry() {
    if (!activeThread) return;
    const lastUserMessage = activeThread.messages.findLast((message) => message.role === "user");
    if (!lastUserMessage) return;

    removeLastMessage(activeThread.id); // the error reply
    void ask(activeThread.id, lastUserMessage.content);
  }

  function startNewChat() {
    setActiveId(null);
    setDraft("");
    setMobileSidebarOpen(false);
  }

  function selectThread(threadId: string) {
    setActiveId(threadId);
    setMobileSidebarOpen(false);
  }

  function removeThread(threadId: string) {
    if (!window.confirm("Delete this trip? This can't be undone.")) return;
    deleteThread(threadId);
    if (threadId === activeId) setActiveId(null);
  }

  function downloadPdf(content: string) {
    // Render only this reply into the print view, then open the print dialog ("Save as PDF")
    flushSync(() => setPrintContent(content));
    const previousTitle = document.title;
    document.title = activeThread ? `TripMate AI - ${activeThread.title}` : "TripMate AI - Travel Plan";
    window.addEventListener("afterprint", () => (document.title = previousTitle), { once: true });
    window.print();
  }

  return (
    <>
      <div className="flex h-dvh overflow-hidden print:hidden">
        <Sidebar
          threads={sortedThreads}
          activeId={activeId}
          pendingIds={pendingIds}
          mobileOpen={mobileSidebarOpen}
          collapsed={sidebarCollapsed}
          onSelect={selectThread}
          onNewChat={startNewChat}
          onDelete={removeThread}
          onCloseMobile={() => setMobileSidebarOpen(false)}
          onCollapse={() => setSidebarCollapsed(true)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center gap-1 px-2 sm:px-3">
            <button
              type="button"
              className="icon-btn md:hidden"
              onClick={() => setMobileSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <MenuIcon />
            </button>
            {sidebarCollapsed && (
              <button
                type="button"
                className="icon-btn hidden md:inline-flex"
                onClick={() => setSidebarCollapsed(false)}
                aria-label="Show sidebar"
              >
                <SidebarIcon />
              </button>
            )}
            <h1 className="min-w-0 truncate px-2 text-sm font-medium text-ink">
              {activeThread?.title ?? "New trip"}
            </h1>
            <button
              type="button"
              className={`icon-btn ml-auto ${sidebarCollapsed ? "" : "md:hidden"}`}
              onClick={startNewChat}
              aria-label="New trip"
            >
              <PlusIcon className="size-5" />
            </button>
          </header>

          <main className="flex flex-1 flex-col overflow-y-auto">
            {activeThread ? (
              <MessageList
                threadId={activeThread.id}
                messages={activeThread.messages}
                pending={activePending}
                onRetry={retry}
                onDownload={downloadPdf}
              />
            ) : (
              <EmptyState onPick={send} />
            )}
          </main>

          <Composer value={draft} onChange={setDraft} onSubmit={() => send(draft)} disabled={activePending} />
        </div>
      </div>

      {printContent && (
        <div className="hidden print:block">
          <h1 className="mb-6 font-display text-4xl text-ink">AI Travel Plan</h1>
          <Markdown content={printContent} />
        </div>
      )}
    </>
  );
}
