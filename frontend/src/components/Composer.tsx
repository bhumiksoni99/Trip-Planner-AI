"use client";

import { useRef } from "react";
import { SendIcon } from "./icons";

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
};

const MAX_HEIGHT = 208;

export default function Composer({ value, onChange, onSubmit, disabled }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && value.trim().length > 0;

  function resize(textarea: HTMLTextAreaElement) {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`;
  }

  function submit() {
    if (!canSend) return;
    onSubmit();
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  return (
    <form
      className="mx-auto w-full max-w-3xl px-3 pb-3 sm:px-6 sm:pb-5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="flex items-end gap-2 rounded-[1.75rem] border border-line bg-surface p-2 pl-5 shadow-[var(--composer-shadow)] transition focus-within:border-accent/50">
        <label htmlFor="composer" className="sr-only">
          Describe your trip
        </label>
        <textarea
          id="composer"
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            resize(event.currentTarget);
          }}
          onKeyDown={(event) => {
            // Enter sends, Shift+Enter adds a new line
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder="Where would you like to go?"
          className="max-h-52 flex-1 resize-none bg-transparent py-2 leading-6 text-ink placeholder:text-muted/70 focus:outline-none"
        />
        <button type="submit" className="send-btn shrink-0" disabled={!canSend} aria-label="Send">
          <SendIcon />
        </button>
      </div>
      <p className="mt-2 text-center text-xs text-muted">
        TripMate can make mistakes. Check flight times and prices before booking.
      </p>
    </form>
  );
}
