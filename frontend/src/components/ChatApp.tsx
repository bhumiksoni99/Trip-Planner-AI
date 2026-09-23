"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { flushSync } from "react-dom";
import {
  logout,
  requestPlan,
  resumePlan,
  type Account,
  type AgentProgressEvent,
  type ApprovalPause,
  type BriefTerm,
  type IntakePause,
  type PlanDay,
  type PlanCosts,
  type PlanHeader,
  type PlanHotel,
  type PlanResponse,
  type ResumeAnswer,
} from "@/lib/api";
import { setActiveThreadId, useActiveThreadId } from "@/lib/activeThread";
import {
  addMessage,
  claimGuestChats,
  createThread,
  deleteThread,
  loadThread,
  removeLastMessage,
  setAccount,
  useThreads,
} from "@/lib/threads";
import AccountDialog from "./AccountDialog";
import { applyProgress, emptyProgress, type ProgressState } from "./AgentProgress";
import Composer, { type ComposerHandle } from "./Composer";
import EmptyState from "./EmptyState";
import { MenuIcon, PlusIcon, SidebarIcon } from "./icons";
import PlanBody from "./PlanBody";
import LinkPanel, { type OpenLink } from "./LinkPanel";
import MessageList from "./MessageList";
import Sidebar from "./Sidebar";

export default function ChatApp({ account: signedInOnLoad }: { account: Account | null }) {
  const router = useRouter();
  // Seeded by the server, which is the only side that can read the login cookie, and kept here so
  // logging in or out updates the app straight away rather than waiting for the page to re-render
  const [account, setSession] = useState(signedInOnLoad);
  const threads = useThreads();
  // Which trip is open is held in the URL, not in state, so ?thread= and the UI can't drift apart
  const activeId = useActiveThreadId();
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set());
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [printContent, setPrintContent] = useState<{
    content: string;
    days?: PlanDay[];
    hotels?: PlanHotel[];
    brief?: BriefTerm[];
    header?: PlanHeader | null;
    costs?: PlanCosts | null;
  } | null>(null);
  // A link from a plan, shown beside the chat instead of navigating away
  const [openLink, setOpenLink] = useState<OpenLink | null>(null);
  // What the backend is waiting on per thread: trip details, or approval of a draft plan
  const [pauses, setPauses] = useState<Record<string, IntakePause | ApprovalPause>>({});
  // Which agents are running for each thread, as the backend reports them
  const [progress, setProgress] = useState<Record<string, ProgressState>>({});
  // The composer keeps its own draft, so typing doesn't re-render the conversation
  const composerRef = useRef<ComposerHandle>(null);
  const [accountOpen, setAccountOpen] = useState(false);

  // The store lists the account's chats when logged in, and this browser's when not
  useEffect(() => {
    setAccount(account?.id ?? null);
  }, [account?.id]);

  // A chat's messages live in the database, so opening one fetches it, along with any question it
  // is paused on. That is what brings the intake card back after a refresh
  useEffect(() => {
    const thread = activeId ? threads.find((item) => item.id === activeId) : null;
    if (!activeId || !thread || thread.loaded || thread.local || pendingIds.has(activeId)) return;

    void loadThread(activeId).then((detail) => {
      if (detail) setPause(activeId, detail.pause);
      else setActiveThreadId(null); // gone, or someone else's
    });
  }, [activeId, threads, pendingIds]);

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

  function setPause(threadId: string, pause: IntakePause | ApprovalPause | null) {
    setPauses((current) => {
      const next = { ...current };
      if (pause) next[threadId] = pause;
      else delete next[threadId];
      return next;
    });
  }

  // A paused run shows its card: trip details to fill in, or a draft plan to approve
  function applyResult(threadId: string, result: PlanResponse) {
    const pause = result.pause_payload;

    if (pause?.type === "approval") {
      addMessage(threadId, {
        role: "assistant",
        content: [pause.itinerary, pause.budget].filter(Boolean).join("\n\n") || "Here is the plan so far.",
      });
      setPause(threadId, pause);
    } else if (pause?.type === "intake") {
      setPause(threadId, pause);
    } else {
      addMessage(threadId, {
        role: "assistant",
        content: result.final_response,
        days: result.days,
        hotels: result.hotels,
        brief: result.brief,
        header: result.header,
        costs: result.costs,
      });
    }
  }

  // Each run reports its own agents, so the checklist starts empty and fills as they run
  function trackProgress(threadId: string) {
    setProgress((current) => ({ ...current, [threadId]: emptyProgress }));

    return (event: AgentProgressEvent) =>
      setProgress((current) => ({
        ...current,
        [threadId]: applyProgress(current[threadId] ?? emptyProgress, event),
      }));
  }

  async function ask(threadId: string, text: string) {
    setPending(threadId, true);
    try {
      applyResult(threadId, await requestPlan(text, threadId, trackProgress(threadId)));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong. Please try again.";
      addMessage(threadId, { role: "assistant", content: message, error: true });
    } finally {
      setPending(threadId, false);
    }
  }

  async function answerPause(threadId: string, answer: ResumeAnswer) {
    setPause(threadId, null);
    setPending(threadId, true);
    try {
      applyResult(threadId, await resumePlan(threadId, answer, trackProgress(threadId)));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong. Please try again.";
      addMessage(threadId, { role: "assistant", content: message, error: true });
    } finally {
      setPending(threadId, false);
    }
  }

  function requestChanges(threadId: string, feedback: string) {
    addMessage(threadId, { role: "user", content: feedback });
    void answerPause(threadId, { approved: false, feedback });
  }

  function submitIntake(threadId: string, answers: Record<string, string>) {
    const filled = Object.entries(answers).filter(([, value]) => value.trim());
    addMessage(threadId, {
      role: "user",
      content: filled.map(([key, value]) => `${key.replace(/_/g, " ")}: ${value.trim()}`).join("\n"),
    });
    void answerPause(threadId, { answers: Object.fromEntries(filled) });
  }

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;

    let threadId = activeThread?.id;
    if (!threadId) {
      threadId = createThread(trimmed);
      setActiveThreadId(threadId);
    } else if (pendingIds.has(threadId)) {
      return;
    }

    addMessage(threadId, { role: "user", content: trimmed });
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
    composerRef.current?.clear();
    setActiveThreadId(null);
    setMobileSidebarOpen(false);
  }

  function selectThread(threadId: string) {
    setActiveThreadId(threadId);
    setMobileSidebarOpen(false);
  }

  function removeThread(threadId: string) {
    if (!window.confirm("Delete this trip? This can't be undone.")) return;
    if (threadId === activeId) setActiveThreadId(null);

    void deleteThread(threadId).catch(() => {
      window.alert("Couldn't delete that trip. Please try again.");
    });
  }

  async function signedIn(user: Account) {
    setAccountOpen(false);
    // The chats planned before logging in belong to this account now; their conversations are already
    // in the database, so only who owns them changes
    await claimGuestChats();
    setSession(user);
    router.refresh(); // keeps the server's idea of who is logged in in step
  }

  async function signOut() {
    await logout().catch(() => undefined);
    setSession(null);
    router.refresh();
  }

  function downloadPdf(content: string, days?: PlanDay[], hotels?: PlanHotel[], brief?: BriefTerm[], header?: PlanHeader | null, costs?: PlanCosts | null) {
    // Render only this reply into the print view, then open the print dialog ("Save as PDF")
    flushSync(() => setPrintContent({ content, days, hotels, brief, header, costs }));
    const previousTitle = document.title;
    document.title = activeThread ? `Itinera AI - ${activeThread.title}` : "Itinera AI - Travel Plan";
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
          account={account}
          onLogin={() => setAccountOpen(true)}
          onLogout={signOut}
          onSelect={selectThread}
          onNewChat={startNewChat}
          onDelete={removeThread}
          onCloseMobile={() => setMobileSidebarOpen(false)}
          onCollapse={() => setSidebarCollapsed(true)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-15 shrink-0 items-center gap-1 border-b border-line px-2 sm:px-3">
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
            <div className="flex min-w-0 items-baseline gap-3 px-2">
              <span className="eyebrow shrink-0">{activeThread ? "Trip" : "New trip"}</span>
              <h1 className="min-w-0 truncate text-[15px] font-medium text-ink">
                {activeThread?.title ?? "Untitled"}
              </h1>
            </div>
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
                progress={progress[activeThread.id] ?? emptyProgress}
                onRetry={retry}
                onDownload={downloadPdf}
                pause={pauses[activeThread.id] ?? null}
                onApprove={() => void answerPause(activeThread.id, { approved: true })}
                onRequestChanges={(feedback) => requestChanges(activeThread.id, feedback)}
                onIntakeSubmit={(answers) => submitIntake(activeThread.id, answers)}
                onIntakeSkip={() => void answerPause(activeThread.id, { skipped: true })}
                onLinkClick={(href, label) => setOpenLink({ href, label })}
              />
            ) : (
              <EmptyState onPick={send} account={account} onLogin={() => setAccountOpen(true)} onLogout={signOut} />
            )}
          </main>

          <Composer ref={composerRef} onSubmit={send} disabled={activePending} />
        </div>

        {openLink && <LinkPanel key={openLink.href} link={openLink} onClose={() => setOpenLink(null)} />}
        {accountOpen && <AccountDialog onClose={() => setAccountOpen(false)} onSignedIn={signedIn} />}
      </div>

      {printContent && (
        <div className="hidden print:block">
          <h1 className="mb-6 font-display text-4xl text-ink">AI Travel Plan</h1>
          <PlanBody
            content={printContent.content}
            days={printContent.days}
            hotels={printContent.hotels}
            brief={printContent.brief}
            header={printContent.header}
            costs={printContent.costs}
          />
        </div>
      )}
    </>
  );
}
