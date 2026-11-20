import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { auth } from "../api/endpoints.js";
import { getToken, setToken, setUnauthorizedHandler } from "../api/client.js";

export const AuthContext = createContext(null);

const SIGNED_OUT = { status: "signed_out", user: null, permissions: [] };

export function AuthProvider({ children }) {
  const [state, setState] = useState(() =>
    getToken() ? { status: "checking", user: null, permissions: [] } : SIGNED_OUT,
  );

  // Any rejected session (expired, revoked, or the account was deactivated) signs the user out.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null);
      setState(SIGNED_OUT);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // When the page loads with a stored token, confirm it is still valid and load the permissions.
  useEffect(() => {
    if (state.status !== "checking") return undefined;
    let cancelled = false;
    auth.me()
      .then(({ user, permissions }) => {
        if (!cancelled) setState({ status: "signed_in", user, permissions });
      })
      .catch(() => {
        if (!cancelled) {
          setToken(null);
          setState(SIGNED_OUT);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [state.status]);

  const login = useCallback(async (email, password) => {
    const session = await auth.login({ email, password });
    setToken(session.token);
    setState({ status: "signed_in", user: session.user, permissions: session.permissions });
  }, []);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } catch {
      // Signing out locally still proceeds if the server is unreachable; the token expires anyway.
    }
    setToken(null);
    setState(SIGNED_OUT);
  }, []);

  const value = useMemo(() => ({
    status: state.status,
    loading: state.status === "checking",
    user: state.user,
    permissions: state.permissions,
    can: (permission) => state.permissions.includes(permission),
    login,
    logout,
  }), [state, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
