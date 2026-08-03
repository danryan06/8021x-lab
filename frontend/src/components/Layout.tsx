import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../api/AuthContext";
import { useMode } from "../modes/ModeContext";
import { useTheme } from "../modes/ThemeContext";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/test", label: "Auth Test" },
  { to: "/users", label: "Users" },
  { to: "/clients", label: "RADIUS Clients" },
  { to: "/certificates", label: "Certificates" },
  { to: "/events", label: "Auth Events" },
  { to: "/wizard", label: "Wizard" },
];

export function Layout() {
  const { logout } = useAuth();
  const { mode, setMode } = useMode();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen">
      <header className="border-b border-white/10 bg-header text-header-fg">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <div>
            <p className="brand-mark font-display text-2xl font-bold tracking-tight">
              802.1X Lab
            </p>
            <p className="mt-2 text-sm text-header-fg/65">
              Learn, test, and demonstrate enterprise authentication
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex overflow-hidden rounded border border-header-fg/20 text-sm">
              <button
                type="button"
                className={`px-3 py-1.5 transition ${
                  mode === "simple" ? "bg-signal text-signal-ink" : "hover:bg-header-fg/10"
                }`}
                onClick={() => setMode("simple")}
              >
                Simple
              </button>
              <button
                type="button"
                className={`px-3 py-1.5 transition ${
                  mode === "advanced" ? "bg-signal text-signal-ink" : "hover:bg-header-fg/10"
                }`}
                onClick={() => setMode("advanced")}
              >
                Advanced
              </button>
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              className="rounded border border-header-fg/20 px-3 py-1.5 text-sm transition hover:bg-header-fg/10"
              title="Toggle light/dark theme"
            >
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            <button
              type="button"
              onClick={logout}
              className="rounded border border-header-fg/20 px-3 py-1.5 text-sm transition hover:bg-header-fg/10"
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
                `rounded px-3 py-1.5 text-sm transition ${
                  isActive
                    ? "bg-header-fg/15 text-header-fg"
                    : "text-header-fg/65 hover:bg-header-fg/10"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="page-enter mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
