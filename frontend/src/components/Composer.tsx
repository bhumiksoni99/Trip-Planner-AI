"use client";

import { useRef } from "react";
import { ArrowRightIcon } from "./icons";

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
    <div className="shrink-0 border-t border-line">
      <form
        className="mx-auto w-full max-w-3xl px-3 pt-3.5 pb-4 sm:px-6"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="flex items-stretch rounded-sharp border border-line-strong bg-surface transition focus-within:border-accent">
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
            placeholder={'Where to, and roughly when? e.g. "Five days in Dubai next month, under ₹2 lakh"'}
            className="max-h-52 min-w-0 flex-1 resize-none bg-transparent px-[18px] py-3.5 leading-6 text-ink placeholder:text-faint focus:outline-none"
          />
          <button type="submit" className="send-btn shrink-0" disabled={!canSend}>
            Send
            <ArrowRightIcon />
          </button>
        </div>
        <p className="mt-2 text-xs text-faint">
          TripMate can make mistakes. Check flight times and prices before booking.
        </p>
      </form>
    </div>
  );
}
