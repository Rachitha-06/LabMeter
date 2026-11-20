import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { ErrorBanner } from "../components/States.jsx";

export default function Login() {
  const { status, login } = useAuth();
  useEffect(() => {
    document.title = "Sign in · LabMeter Suite";
  }, []);
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (status === "signed_in") {
    return <Navigate to={location.state?.from ?? "/"} replace />;
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(location.state?.from ?? "/", { replace: true });
    } catch (err) {
      setError(err);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="card w-full max-w-sm">
        <h1 className="text-lg font-semibold text-emerald-800">LabMeter Suite</h1>
        <p className="mb-4 text-sm text-slate-500">Sign in with your account.</p>
        <form className="space-y-4" onSubmit={submit}>
          <div>
            <label className="label" htmlFor="login-email">Email</label>
            <input id="login-email" type="email" autoComplete="username" required className="input"
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="login-password">Password</label>
            <input id="login-password" type="password" autoComplete="current-password" required className="input"
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <ErrorBanner error={error} />
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
