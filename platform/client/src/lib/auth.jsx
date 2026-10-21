import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(!!tokenStore.get());
  const [notice, setNotice] = useState(null); // shown on the login page, e.g. "session expired"

  const logout = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
  }, []);

  useEffect(() => {
    // Any 401 from the API: sign out and tell the user why.
    setUnauthorizedHandler(() => {
      logout();
      setNotice("Your session has expired. Please sign in again.");
    });
    if (!tokenStore.get()) return;
    api("/auth/me")
      .then((d) => setUser(d.user))
      .catch((e) => {
        if (e.status !== 401) setNotice(e.message); // server or database down: keep the token, explain
        setUser(null);
      })
      .finally(() => setChecking(false));
  }, [logout]);

  const login = useCallback(async (email, password) => {
    const d = await api("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    tokenStore.set(d.token);
    setNotice(null);
    setUser(d.user);
  }, []);

  const value = useMemo(
    () => ({
      user,
      checking,
      notice,
      login,
      logout,
      isManager: user?.role === "manager",
    }),
    [user, checking, notice, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
