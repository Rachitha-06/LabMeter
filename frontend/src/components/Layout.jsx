import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { health } from "../api/endpoints.js";

const ROLE_LABELS = { admin: "Admin", lab_manager: "Lab manager", staff: "Staff", evaluator: "Evaluator" };

const links = [
  { to: "/", label: "Dashboard", end: true, permission: "analytics:read" },
  { to: "/labs", label: "Laboratories", permission: "labs:read" },
  { to: "/readings", label: "Readings", permission: "readings:read" },
  { to: "/forecasts", label: "Forecasts", permission: "forecasts:read" },
  { to: "/alerts", label: "Alerts", permission: "alerts:read" },
  { to: "/energy", label: "Tariffs & factors", permission: "energy:read" },
  { to: "/import", label: "CSV import", permission: "imports:write" },
  { to: "/users", label: "Users", permission: "users:manage" },
];

function ApiStatus() {
  const status = useAsync(() => health(), []);
  if (status.loading) return <span className="text-xs text-slate-400">Checking API…</span>;
  if (status.error) {
    return (
      <button type="button" onClick={status.reload} className="text-xs text-red-700 underline">
        API unreachable · retry
      </button>
    );
  }
  return <span className="text-xs text-emerald-700">API connected</span>;
}

export default function Layout() {
  const { can, user, logout } = useAuth();
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:flex md:w-56 md:flex-col md:border-b-0 md:border-r">
        <div className="px-4 py-4">
          <p className="text-lg font-semibold text-emerald-800">LabMeter Suite</p>
          <p className="text-xs text-slate-500">Lab energy monitoring</p>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-3 md:flex-col md:pb-0">
          {links.filter((link) => can(link.permission)).map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-2 text-sm ${
                  isActive ? "bg-emerald-50 font-medium text-emerald-900" : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 md:mt-auto md:border-t md:border-slate-200">
          <p className="truncate text-sm text-slate-700" title={user?.email}>{user?.email}</p>
          <p className="text-xs text-slate-500">{ROLE_LABELS[user?.role] ?? user?.role}</p>
          <button type="button" onClick={logout} className="mt-2 text-xs text-slate-600 underline">Sign out</button>
          <div className="mt-3 hidden md:block"><ApiStatus /></div>
        </div>
      </aside>
      <main className="flex-1 p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  );
}
