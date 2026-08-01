import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../api/AuthContext";
import { useMode } from "../modes/ModeContext";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/test", label: "Auth Test" },
  { to: "/users", label: "Users" },
  { to: "/clients", label: "RADIUS Clients" },
  { to: "/events", label: "Auth Events" },
  { to: "/wizard", label: "Wizard" },
];

export function Layout() {
  const { logout } = useAuth();
  const { mode, setMode } = useMode();

  return (
    <div className="min-h-screen">
      <header className="border-b border-black/10 bg-ink text-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <div>
            <p className="font-display text-2xl font-bold tracking-tight">802.1X Lab</p>
            <p className="text-sm text-white/70">
              Learn, test, and demonstrate enterprise authentication
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex overflow-hidden rounded border border-white/20 text-sm">
              <button
                type="button"
                className={`px-3 py-1.5 ${mode === "simple" ? "bg-signal text-ink" : "bg-transparent"}`}
                onClick={() => setMode("simple")}
              >
                Simple
              </button>
              <button
                type="button"
                className={`px-3 py-1.5 ${mode === "advanced" ? "bg-signal text-ink" : "bg-transparent"}`}
                onClick={() => setMode("advanced")}
              >
                Advanced
              </button>
            </div>
            <button
              type="button"
              onClick={logout}
              className="rounded border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10"
            >
              Log out
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 pb-3">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm ${
                  isActive ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
