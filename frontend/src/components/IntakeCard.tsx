"use client";

import { useState } from "react";
import type { IntakePause } from "@/lib/api";

type IntakeCardProps = {
  pause: IntakePause;
  onSubmit: (answers: Record<string, string>) => void;
  onSkipAll: () => void;
};

export default function IntakeCard({ pause, onSubmit, onSkipAll }: IntakeCardProps) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [typed, setTyped] = useState("");

  const question = pause.questions[step];
  const isLast = step === pause.questions.length - 1;

  function advance(answer: string) {
    const collected = answer.trim() ? { ...answers, [question.key]: answer.trim() } : answers;
    setAnswers(collected);
    setTyped("");

    if (isLast) {
      onSubmit(collected);
    } else {
      setStep(step + 1);
    }
  }

  return (
    <div className="flex gap-3 sm:gap-4">
      <span aria-hidden className="brand-mark size-8 shrink-0 text-sm">
        ✈️
      </span>
      <div className="min-w-0 flex-1 rounded-sharp border border-line bg-surface px-4 py-4">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">
          Question {step + 1} of {pause.questions.length}
        </p>
        <p id="intake-question" className="mt-1.5 font-medium text-ink">
          {question.question}
        </p>

        <div className="mt-3 flex flex-wrap gap-2">
          {question.options.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => advance(option)}
              className="rounded-sharp border border-line bg-surface px-3.5 py-1.5 text-sm text-ink transition hover:-translate-y-px hover:border-accent/50"
            >
              {option}
            </button>
          ))}
        </div>

        <form
          className="mt-3 flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (typed.trim()) advance(typed);
          }}
        >
          <label htmlFor="intake-answer" className="sr-only">
            Or type your own answer
          </label>
          <input
            id="intake-answer"
            type="text"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={question.placeholder}
            className="min-w-0 flex-1 rounded-sharp border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-accent/50 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!typed.trim()}
            className="shrink-0 rounded-sharp bg-accent px-4 py-2 text-sm font-medium text-on-accent transition hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
          >
            {isLast ? "Done" : "Next"}
          </button>
        </form>

        <div className="mt-2 flex flex-wrap items-center justify-between">
          <button type="button" onClick={() => advance("")} className="action-btn -ml-2">
            {isLast ? "Skip and plan" : "Skip this question"}
          </button>
          <button type="button" onClick={onSkipAll} className="action-btn -mr-2">
            Skip all, just plan it
          </button>
        </div>
      </div>
    </div>
  );
}
