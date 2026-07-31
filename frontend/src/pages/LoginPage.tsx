import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../api/AuthContext";

export function LoginPage() {
  const { token, login } = useAuth();
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
    <div className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md border border-black/10 bg-white/80 p-8 shadow-sm backdrop-blur"
      >
        <h1 className="font-display text-3xl font-bold">802.1X Lab</h1>
        <p className="mt-2 text-sm text-ink/70">
          Sign in to manage your authentication sandbox.
        </p>
        <label className="mt-6 block text-sm font-medium">
          Username
          <input
            className="mt-1 w-full border border-black/15 px-3 py-2"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="mt-4 block text-sm font-medium">
          Password
          <input
            type="password"
            className="mt-1 w-full border border-black/15 px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <p className="mt-3 text-sm text-fail">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="mt-6 w-full bg-ink px-4 py-2.5 font-medium text-white hover:bg-slatepanel disabled:opacity-60"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
