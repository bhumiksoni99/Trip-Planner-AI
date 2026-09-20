"use client";

import { useEffect, useRef, useState } from "react";
import type { Message } from "@/lib/threads";
import { CheckIcon, CopyIcon, DownloadIcon, RetryIcon } from "./icons";
import Markdown from "./Markdown";

type MessageListProps = {
  threadId: string;
  messages: Message[];
  pending: boolean;
  onRetry: () => void;
  onDownload: (content: string) => void;
};

export default function MessageList({ threadId, messages, pending, onRetry, onDownload }: MessageListProps) {
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // While waiting, keep the thinking indicator in view; otherwise show the start of the latest message
  useEffect(() => {
    if (pending) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    } else {
      lastMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [threadId, messages.length, pending]);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-4 pt-6 pb-10 sm:px-6">
      {messages.map((message, index) => {
        const isLast = index === messages.length - 1;
        return (
          <div key={message.id} ref={isLast ? lastMessageRef : undefined} className="scroll-mt-6">
            {message.role === "user" ? (
              <UserMessage content={message.content} />
            ) : message.error ? (
              <ErrorMessage content={message.content} onRetry={isLast && !pending ? onRetry : undefined} />
            ) : (
              <AssistantMessage content={message.content} onDownload={onDownload} />
            )}
          </div>
        );
      })}

      {pending && <ThinkingMessage />}
      <div ref={endRef} />
    </div>
  );
}

function Avatar() {
  return <span className="brand-mark size-8 shrink-0 text-sm">✈️</span>;
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-3xl rounded-br-lg bg-bubble px-4 py-2.5 leading-relaxed whitespace-pre-wrap text-ink">
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({ content, onDownload }: { content: string; onDownload: (content: string) => void }) {
  return (
    <div className="flex gap-3 sm:gap-4">
      <Avatar />
      <div className="min-w-0 flex-1 pt-0.5">
        <Markdown content={content} />
        <div className="mt-4 -ml-2 flex flex-wrap gap-1">
          <CopyButton text={content} />
          <button type="button" className="action-btn" onClick={() => onDownload(content)}>
            <DownloadIcon />
            Download PDF
          </button>
        </div>
      </div>
    </div>
  );
}

function ErrorMessage({ content, onRetry }: { content: string; onRetry?: () => void }) {
  return (
    <div className="flex gap-3 sm:gap-4">
      <Avatar />
      <div
        role="alert"
        className="min-w-0 flex-1 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200"
      >
        <p className="font-semibold">Couldn&apos;t plan this trip</p>
        <p className="mt-0.5 opacity-90">{content}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 -ml-2 font-medium transition hover:bg-red-100 dark:hover:bg-red-900/40"
          >
            <RetryIcon />
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

function ThinkingMessage() {
  return (
    <div className="flex gap-3 sm:gap-4" aria-live="polite" aria-busy="true">
      <Avatar />
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          Planning your trip
          <span aria-hidden className="flex gap-1">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </span>
        </div>
        <p className="mt-1 text-sm text-muted">
          Searching flights, finding hotels and writing your itinerary. This can take a minute.
        </p>
        <div aria-hidden className="mt-5 space-y-2.5">
          <div className="shimmer h-3.5 w-full rounded-md" />
          <div className="shimmer h-3.5 w-11/12 rounded-md" />
          <div className="shimmer h-3.5 w-3/5 rounded-md" />
        </div>
      </div>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked by the browser; nothing else to do
    }
  }

  return (
    <button type="button" className="action-btn" onClick={handleCopy}>
      {copied ? <CheckIcon className="size-4 text-teal" /> : <CopyIcon />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
