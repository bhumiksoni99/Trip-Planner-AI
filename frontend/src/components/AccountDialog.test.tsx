import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountDialog from "./AccountDialog";

vi.mock("@/lib/api", () => ({ login: vi.fn(), signup: vi.fn() }));

const api = vi.mocked(await import("@/lib/api"));

const ACCOUNT = { id: "user-1", email: "traveller@example.com" };

function open(props: Partial<Parameters<typeof AccountDialog>[0]> = {}) {
  const onClose = vi.fn();
  const onSignedIn = vi.fn();
  const { container } = render(<AccountDialog onClose={onClose} onSignedIn={onSignedIn} {...props} />);
  return { onClose, onSignedIn, container, user: userEvent.setup() };
}

beforeEach(() => vi.clearAllMocks());

describe("<AccountDialog />", () => {
  it("opens on the log in form, with the email field focused", () => {
    open();

    expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveFocus();
  });

  it("logs in and hands the account back", async () => {
    api.login.mockResolvedValue(ACCOUNT);
    const { onSignedIn, user } = open();

    await user.type(screen.getByLabelText("Email"), "traveller@example.com");
    await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(api.login).toHaveBeenCalledWith("traveller@example.com", "hunter2hunter2");
    expect(onSignedIn).toHaveBeenCalledWith(ACCOUNT);
  });

  it("trims a stray space off the email", async () => {
    api.login.mockResolvedValue(ACCOUNT);
    const { user } = open();

    await user.type(screen.getByLabelText("Email"), "  traveller@example.com  ");
    await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(api.login).toHaveBeenCalledWith("traveller@example.com", "hunter2hunter2");
  });

  it("switches to creating an account, and signs up instead", async () => {
    api.signup.mockResolvedValue(ACCOUNT);
    const { onSignedIn, user } = open();

    await user.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.getByRole("heading", { name: "Create an account" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(api.signup).toHaveBeenCalledWith("new@example.com", "hunter2hunter2");
    expect(api.login).not.toHaveBeenCalled();
    expect(onSignedIn).toHaveBeenCalledWith(ACCOUNT);
  });

  it("asks for a longer password only when creating an account", async () => {
    const { user } = open();
    expect(screen.getByLabelText("Password")).not.toHaveAttribute("minLength");

    await user.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("minLength", "8");
  });

  it("shows what the backend said when logging in fails", async () => {
    api.login.mockRejectedValue(new Error("Wrong email or password."));
    const { onSignedIn, user } = open();

    await user.type(screen.getByLabelText("Email"), "traveller@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("lets the traveller try again after a failure", async () => {
    api.login.mockRejectedValueOnce(new Error("Wrong email or password."));
    const { user } = open();

    await user.type(screen.getByLabelText("Email"), "traveller@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await screen.findByRole("alert");

    // The button is usable again, rather than stuck on "One moment…"
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled();
  });

  it("clears the error when switching between logging in and signing up", async () => {
    api.login.mockRejectedValue(new Error("Wrong email or password."));
    const { user } = open();

    await user.type(screen.getByLabelText("Email"), "traveller@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("closes on the close button, on Escape, and on the backdrop", async () => {
    const { onClose, user, container } = open();

    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.keyboard("{Escape}");

    // The backdrop is aria-hidden, so it has no role to query by: it's the overlay behind the dialog
    const backdrop = container.querySelector("[aria-hidden]");
    expect(backdrop).not.toBeNull();
    await user.click(backdrop as Element);

    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("is a modal dialog, so assistive tech treats the page behind it as inert", () => {
    open();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});
