import { useState } from "react";
import { auth } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { EmptyState, ErrorBanner, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { useAsync } from "../hooks/useAsync.js";

const ROLE_LABELS = {
  admin: "Admin",
  lab_manager: "Lab manager",
  staff: "Staff",
  evaluator: "Evaluator",
};

export default function Users() {
  const { can, user: me } = useAuth();
  const users = useAsync(() => auth.users(), [can("users:manage")]);
  const [form, setForm] = useState({ email: "", password: "", role: "staff" });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  if (!can("users:manage")) {
    return <EmptyState title="Admins only">Your role cannot manage user accounts.</EmptyState>;
  }

  async function run(action, message) {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(message);
      users.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageHeader title="Users" description="Create accounts and assign roles. Changes take effect at the next request." />
      <SuccessBanner>{notice}</SuccessBanner>
      <ErrorBanner error={error} />

      <section className="card mb-6">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Add a user</h2>
        <form
          className="grid gap-3 sm:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            run(() => auth.createUser(form), `Created ${form.email}.`).then(() =>
              setForm({ email: "", password: "", role: "staff" }));
          }}
        >
          <input aria-label="Email" type="email" required className="input" placeholder="name@college.example"
            value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input aria-label="Initial password" type="password" required minLength={12} className="input"
            placeholder="At least 12 characters" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <select aria-label="Role" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button type="submit" className="btn-primary">Create user</button>
        </form>
      </section>

      {users.loading && <LoadingState label="Loading users…" />}
      <ErrorBanner error={users.error} onRetry={users.reload} />

      {users.data && (
        <div className="card overflow-hidden p-0">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className="table-th">Email</th>
                <th scope="col" className="table-th">Role</th>
                <th scope="col" className="table-th">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td className="table-td">{u.email}{u.id === me?.id && <span className="ml-2 text-xs text-slate-400">(you)</span>}</td>
                  <td className="table-td">
                    <select aria-label={`Role for ${u.email}`} className="input w-44" value={u.role}
                      onChange={(e) => run(() => auth.updateUser(u.id, { role: e.target.value }), `Updated role for ${u.email}.`)}>
                      {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </td>
                  <td className="table-td">
                    <button type="button" className={u.is_active ? "text-emerald-800 underline" : "text-red-700 underline"}
                      onClick={() => run(() => auth.updateUser(u.id, { is_active: !u.is_active }),
                        `${u.is_active ? "Deactivated" : "Reactivated"} ${u.email}.`)}>
                      {u.is_active ? "Active · deactivate" : "Inactive · reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
