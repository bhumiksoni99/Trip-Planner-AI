"use client";

import { useEffect, useState } from "react";

import { deleteAccount } from "@/lib/api";

type DeleteAccountDialogProps = {
  email: string;
  onClose: () => void;
  // Called once the account is gone, so the app can drop back to being a guest
  onDeleted: () => void;
};

export default function DeleteAccountDialog({ email, onClose, onDeleted }: DeleteAccountDialogProps) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Typing the address is the confirmation: this can't be undone, and a single click is too easy
  // to make by accident
  const confirmed = typed.trim().toLowerCase() === email.toLowerCase();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deleteAccount();
      onDeleted();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Couldn't delete your account. Please try again.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div aria-hidden className="absolute inset-0 bg-ink/30" onClick={onClose} />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        className="relative w-full max-w-sm rounded-sharp border border-line bg-surface p-6 shadow-lg"
      >
        <h2 id="delete-account-title" className="font-display text-2xl text-ink">
          Delete your account
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          This deletes every trip you&apos;ve planned, and the conversations behind them. It can&apos;t be undone.
        </p>

        <label htmlFor="delete-confirm" className="mt-5 block text-xs font-medium text-muted">
          Type <span className="font-semibold text-ink">{email}</span> to confirm
        </label>
        <input
          id="delete-confirm"
          type="text"
          autoComplete="off"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          className="mt-1 block w-full rounded-sharp border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-accent/50 focus:outline-none"
        />

        {error && (
          <p role="alert" className="mt-3 rounded-sharp border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}

        <div className="mt-5 flex items-center justify-end gap-3">
          <button type="button" onClick={onClose} className="text-sm text-muted hover:text-ink">
            Cancel
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={!confirmed || busy}
            className="rounded-sharp bg-red-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Deleting…" : "Delete everything"}
          </button>
        </div>

        <button type="button" onClick={onClose} aria-label="Close" className="icon-btn absolute top-3 right-3">
          ✕
        </button>
      </div>
    </div>
  );
}
