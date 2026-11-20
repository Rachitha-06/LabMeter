import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Login from "./Login.jsx";
import { renderSignedOut } from "../test/renderWithAuth.jsx";
import { ApiError } from "../api/client.js";

describe("Login page", () => {
  it("submits the email and password entered", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    renderSignedOut(<Login />, { login });
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "lab@example.test" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "a-long-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("lab@example.test", "a-long-password-1"));
  });

  it("shows a server rejection and clears the password field", async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, "invalid_credentials", "email or password is incorrect"));
    renderSignedOut(<Login />, { login });
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "lab@example.test" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("email or password is incorrect");
    expect(screen.getByLabelText(/password/i)).toHaveValue("");
  });

  it("shows the retry time when sign-in is locked", async () => {
    const login = vi.fn().mockRejectedValue(
      new ApiError(429, "too_many_attempts", "too many failed sign-in attempts; try again later", { retry_after_seconds: 600 }),
    );
    renderSignedOut(<Login />, { login });
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "lab@example.test" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "anything-here" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("too many failed sign-in attempts");
  });
});
