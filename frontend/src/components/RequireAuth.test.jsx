import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import RequireAuth from "./RequireAuth.jsx";
import { AuthContext } from "../auth/AuthContext.jsx";

function withStatus(status) {
  const value = { status, loading: status === "checking", user: null, permissions: [], can: () => false, login: vi.fn(), logout: vi.fn() };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/labs"]}>
        <Routes>
          <Route path="/login" element={<p>Sign-in page</p>} />
          <Route path="/labs" element={<RequireAuth><p>Protected content</p></RequireAuth>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("RequireAuth", () => {
  it("shows protected content to a signed-in user", () => {
    withStatus("signed_in");
    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });

  it("redirects a signed-out visitor to the sign-in page", () => {
    withStatus("signed_out");
    expect(screen.getByText("Sign-in page")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("waits while the stored session is being checked", () => {
    withStatus("checking");
    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
  });
});
