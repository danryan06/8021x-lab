import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../api/AuthContext";
import { useTheme } from "../modes/ThemeContext";
import { Button, Field, PasswordInput, StatusBanner } from "../components/ui";

export function LoginPage() {
  const { token, login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (token) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
    } catch {
      setError("Login failed. Check ADMIN_USERNAME / ADMIN_PASSWORD in .env.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <button
        type="button"
        onClick={toggleTheme}
        className="ui-btn-ghost absolute right-4 top-4"
      >
        {theme === "dark" ? "Light mode" : "Dark mode"}
      </button>
      <form onSubmit={onSubmit} className="ui-panel page-enter w-full max-w-md p-8">
        <h1 className="brand-mark font-display text-3xl font-bold tracking-tight">
          802.1X Lab
        </h1>
        <p className="mt-3 text-sm text-ink/70">
          Sign in to manage your authentication sandbox.
        </p>
        <Field label="Username" className="mt-6">
          <input
            className="ui-input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </Field>
        <Field label="Password" className="mt-4">
          <PasswordInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </Field>
        {error && (
          <div className="mt-3">
            <StatusBanner tone="error">{error}</StatusBanner>
          </div>
        )}
        <Button
          type="submit"
          disabled={loading}
          className="mt-6 w-full"
          variant="signal"
        >
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
