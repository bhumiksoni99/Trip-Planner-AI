import type { Thread } from "@/lib/threads";
import { ChatIcon, CloseIcon, PlusIcon, SidebarIcon, TrashIcon } from "./icons";

type SidebarProps = {
  threads: Thread[];
  activeId: string | null;
  pendingIds: Set<string>;
  mobileOpen: boolean;
  collapsed: boolean;
  onSelect: (threadId: string) => void;
  onNewChat: () => void;
  onDelete: (threadId: string) => void;
  onCloseMobile: () => void;
  onCollapse: () => void;
};

export default function Sidebar({
  threads,
  activeId,
  pendingIds,
  mobileOpen,
  collapsed,
  onSelect,
  onNewChat,
  onDelete,
  onCloseMobile,
  onCollapse,
}: SidebarProps) {
  return (
    <>
      {mobileOpen && (
        <div aria-hidden className="fixed inset-0 z-30 bg-black/40 backdrop-blur-[2px] md:hidden" onClick={onCloseMobile} />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-line bg-sidebar transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } ${collapsed ? "md:hidden" : ""}`}
      >
        <div className="flex h-14 items-center justify-between px-3">
          <div className="flex items-center gap-2.5 pl-1">
            <span className="brand-mark size-8 text-sm">✈️</span>
            <span className="font-semibold tracking-tight text-ink">TripMate AI</span>
          </div>
          <button type="button" className="icon-btn md:hidden" onClick={onCloseMobile} aria-label="Close sidebar">
            <CloseIcon />
          </button>
          <button type="button" className="icon-btn hidden md:inline-flex" onClick={onCollapse} aria-label="Hide sidebar">
            <SidebarIcon />
          </button>
        </div>

        <div className="px-3 pt-1 pb-3">
          <button
            type="button"
            onClick={onNewChat}
            className="flex w-full items-center gap-2.5 rounded-xl border border-line bg-surface px-3 py-2.5 text-sm font-medium text-ink shadow-sm transition hover:border-accent/40"
          >
            <PlusIcon />
            New trip
          </button>
        </div>

        <nav aria-label="Trips" className="flex-1 overflow-y-auto px-3 pb-3">
          <p className="px-3 pt-2 pb-2 text-xs font-medium tracking-wide text-muted uppercase">Recent trips</p>

          {threads.length === 0 ? (
            <p className="px-3 text-sm text-muted">Your trips will show up here.</p>
          ) : (
            <ul className="space-y-0.5">
              {threads.map((thread) => {
                const active = thread.id === activeId;
                return (
                  <li key={thread.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(thread.id)}
                      aria-current={active ? "page" : undefined}
                      className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition ${
                        active ? "bg-active font-medium text-ink" : "text-muted hover:bg-hover hover:text-ink"
                      }`}
                    >
                      {pendingIds.has(thread.id) ? (
                        <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-line border-t-accent" />
                      ) : (
                        <ChatIcon className="size-4 shrink-0" />
                      )}
                      <span className="truncate pr-7">{thread.title}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(thread.id)}
                      aria-label={`Delete "${thread.title}"`}
                      className={`absolute top-1/2 right-1.5 -translate-y-1/2 rounded-lg p-1.5 text-muted transition hover:bg-hover hover:text-ink focus-visible:opacity-100 ${
                        active ? "opacity-100" : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
                      }`}
                    >
                      <TrashIcon />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-muted">
          Multi-agent planner built with LangGraph, Gemini, Tavily and AviationStack
        </p>
      </aside>
    </>
  );
}
