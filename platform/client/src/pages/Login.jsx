import { useState } from "react";
import { useAuth } from "../lib/auth.jsx";

export default function Login() {
  const { login, notice } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            DI
          </span>
          <span className="brand-text">
            <span className="brand-name">DevIntel</span>
            <span className="brand-sub">Development intelligence</span>
          </span>
        </div>
        <h1 className="login-title">Sign in</h1>
        <p className="muted small login-intro">
          AI-driven integrated development analytics and decision support
        </p>
        <label className="field-label" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label className="field-label" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {notice && !error && <p className="notice small">{notice}</p>}
        {error && <p className="error small">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
