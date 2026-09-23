import type { Account } from "@/lib/api";
import type { Thread } from "@/lib/threads";
import { ChatIcon, CloseIcon, PlusIcon, SidebarIcon, TrashIcon } from "./icons";

type SidebarProps = {
  threads: Thread[];
  activeId: string | null;
  pendingIds: Set<string>;
  mobileOpen: boolean;
  collapsed: boolean;
  // Null when nobody is logged in, so the chats are this browser's alone
  account: Account | null;
  onLogin: () => void;
  onLogout: () => void;
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
  account,
  onLogin,
  onLogout,
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
        className={`fixed inset-y-0 left-0 z-40 flex w-[264px] shrink-0 flex-col bg-sidebar text-sidebar-ink transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } ${collapsed ? "md:hidden" : ""}`}
      >
        <div className="flex h-14 items-center justify-between px-5">
          <div className="flex items-center gap-2.5">
            <span className="text-base">✈️</span>
            <span className="text-[15px] font-semibold tracking-[0.01em] text-sidebar-ink">Itinera</span>
          </div>
          <button type="button" className="icon-btn text-faint hover:bg-sidebar-hover hover:text-sidebar-ink md:hidden" onClick={onCloseMobile} aria-label="Close sidebar">
            <CloseIcon />
          </button>
          <button type="button" className="icon-btn hidden text-faint hover:bg-sidebar-hover hover:text-sidebar-ink md:inline-flex" onClick={onCollapse} aria-label="Hide sidebar">
            <SidebarIcon />
          </button>
        </div>

        <div className="px-5 pt-1 pb-3">
          <button
            type="button"
            onClick={onNewChat}
            className="flex w-full items-center justify-between rounded-sharp bg-sidebar-ink px-3.5 py-2.5 text-sm font-semibold text-sidebar transition hover:opacity-90"
          >
            New trip
            <PlusIcon />
          </button>
        </div>

        <nav aria-label="Trips" className="flex-1 overflow-y-auto px-5 pb-3">
          <p className="eyebrow pt-6 pb-2.5">Trips</p>

          {threads.length === 0 ? (
            <p className="text-sm text-faint">Your trips will show up here.</p>
          ) : (
            <ul className="-mx-2 space-y-0.5">
              {threads.map((thread) => {
                const active = thread.id === activeId;
                return (
                  <li key={thread.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(thread.id)}
                      aria-current={active ? "page" : undefined}
                      className={`flex w-full items-center gap-2.5 rounded-sharp px-2.5 py-2 text-left text-sm transition ${
                        active
                          ? "bg-sidebar-active font-medium text-sidebar-ink"
                          : "text-faint hover:bg-sidebar-hover hover:text-sidebar-ink"
                      }`}
                    >
                      {pendingIds.has(thread.id) ? (
                        <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-sidebar-active border-t-sidebar-ink" />
                      ) : (
                        <ChatIcon className="size-4 shrink-0" />
                      )}
                      <span className="truncate pr-7">{thread.title}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(thread.id)}
                      aria-label={`Delete "${thread.title}"`}
                      className={`absolute top-1/2 right-1.5 -translate-y-1/2 rounded-sharp p-1.5 text-faint transition hover:bg-sidebar-active hover:text-sidebar-ink focus-visible:opacity-100 ${
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

        <div className="border-t border-sidebar-hover px-5 py-4">
          {account ? (
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-xs text-sidebar-ink" title={account.email}>
                {account.email}
              </span>
              <button type="button" onClick={onLogout} className="shrink-0 text-xs text-faint underline underline-offset-2 hover:text-sidebar-ink">
                Log out
              </button>
            </div>
          ) : (
            <div className="space-y-1.5">
              <p className="text-[11px] leading-relaxed text-faint">Trips are saved to this browser only.</p>
              <button type="button" onClick={onLogin} className="text-xs font-medium text-sidebar-ink underline underline-offset-2">
                Log in to keep them
              </button>
            </div>
          )}

          <p className="mt-3 text-[11px] leading-relaxed text-faint">
            Multi-agent planner built with LangGraph, Gemini, Tavily and AviationStack
          </p>
        </div>
      </aside>
    </>
  );
}
