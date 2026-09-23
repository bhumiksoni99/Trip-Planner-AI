"use client";

import { useEffect, useRef, useState } from "react";

import { login, signup, type Account } from "@/lib/api";

type AccountDialogProps = {
  onClose: () => void;
  // Given the account once the email and password are accepted
  onSignedIn: (account: Account) => void;
};

export default function AccountDialog({ onClose, onSignedIn }: AccountDialogProps) {
  const [creating, setCreating] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    emailRef.current?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      onSignedIn(await (creating ? signup(email.trim(), password) : login(email.trim(), password)));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div aria-hidden className="absolute inset-0 bg-ink/30" onClick={onClose} />

      <div role="dialog" aria-modal="true" aria-labelledby="account-title" className="relative w-full max-w-sm rounded-sharp border border-line bg-surface p-6 shadow-lg">
        <h2 id="account-title" className="font-display text-2xl text-ink">
          {creating ? "Create an account" : "Log in"}
        </h2>
        <p className="mt-1 text-sm text-muted">
          {creating ? "Your trips are saved and follow you to any device." : "Welcome back."}
        </p>

        <form onSubmit={submit} className="mt-5 space-y-3">
          <div>
            <label htmlFor="account-email" className="text-xs font-medium text-muted">
              Email
            </label>
            <input
              id="account-email"
              ref={emailRef}
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 block w-full rounded-sharp border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-accent/50 focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="account-password" className="text-xs font-medium text-muted">
              Password
            </label>
            <input
              id="account-password"
              type="password"
              required
              minLength={creating ? 8 : undefined}
              autoComplete={creating ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 block w-full rounded-sharp border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-accent/50 focus:outline-none"
            />
            {creating && <p className="mt-1 text-xs text-faint">At least 8 characters.</p>}
          </div>

          {error && (
            <p role="alert" className="rounded-sharp border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-sharp bg-accent px-4 py-2 text-sm font-medium text-on-accent transition hover:-translate-y-px disabled:opacity-60"
          >
            {busy ? "One moment…" : creating ? "Create account" : "Log in"}
          </button>
        </form>

        <button
          type="button"
          onClick={() => {
            setCreating(!creating);
            setError(null);
          }}
          className="mt-4 text-sm text-muted underline underline-offset-2 hover:text-ink"
        >
          {creating ? "I already have an account" : "Create an account"}
        </button>

        <button type="button" onClick={onClose} aria-label="Close" className="icon-btn absolute top-3 right-3">
          ✕
        </button>
      </div>
    </div>
  );
}
