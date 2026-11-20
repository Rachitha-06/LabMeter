import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthContext } from "../auth/AuthContext.jsx";

const DEFAULT_USER = { id: 1, email: "tester@example.test", role: "admin", is_active: true };

/** Render a component inside a signed-in auth context with the given permissions. */
export function renderWithAuth(ui, { permissions = [], user = DEFAULT_USER, route = "/" } = {}) {
  const value = {
    status: "signed_in",
    loading: false,
    user,
    permissions,
    can: (permission) => permissions.includes(permission),
    login: vi.fn(),
    logout: vi.fn(),
  };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </AuthContext.Provider>,
  );
}

/** Render a component in a signed-out auth context, with an optional login mock. */
export function renderSignedOut(ui, { login = vi.fn(), route = "/" } = {}) {
  const value = {
    status: "signed_out",
    loading: false,
    user: null,
    permissions: [],
    can: () => false,
    login,
    logout: vi.fn(),
  };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </AuthContext.Provider>,
  );
}
