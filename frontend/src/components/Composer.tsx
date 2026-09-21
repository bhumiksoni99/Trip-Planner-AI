"use client";

import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { ArrowRightIcon } from "./icons";

export type ComposerHandle = {
  clear: () => void;
  focus: () => void;
};

type ComposerProps = {
  onSubmit: (text: string) => void;
  disabled: boolean;
  ref?: Ref<ComposerHandle>;
};

const MAX_HEIGHT = 208;

export default function Composer({ onSubmit, disabled, ref }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // The draft lives in the textarea, not in React state. Holding it in state re-rendered the whole
  // conversation on every keystroke, which meant re-parsing each plan's Markdown as you typed.
  // This only tracks whether there is any text, so Send can enable itself.
  const [hasText, setHasText] = useState(false);
  const canSend = !disabled && hasText;

  useImperativeHandle(ref, () => ({ clear: reset, focus: () => textareaRef.current?.focus() }));

  function reset() {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.value = "";
    textarea.style.height = "auto";
    setHasText(false);
  }

  function submit() {
    const text = textareaRef.current?.value.trim() ?? "";
    if (!text || disabled) return;

    reset();
    onSubmit(text);
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
            defaultValue=""
            onChange={(event) => {
              const textarea = event.currentTarget;
              textarea.style.height = "auto";
              textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`;

              // Returning the same value makes React skip the render, so most keystrokes cost nothing
              const filled = textarea.value.trim().length > 0;
              setHasText((current) => (current === filled ? current : filled));
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
          Itinera can make mistakes. Check flight times and prices before booking.
        </p>
      </form>
    </div>
  );
}
