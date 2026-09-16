import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null = checking, false = logged out

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      try {
        await api.post("/auth/refresh");
        const { data } = await api.get("/auth/me");
        setUser(data);
      } catch {
        setUser(false);
      }
    }
  }, []);

  useEffect(() => {
    // Skip /me check during OAuth callback processing
    if (
      window.location.hash?.includes("session_id=") ||
      window.location.search?.includes("session_id=") ||
      window.location.search?.includes("code=") ||
      window.location.pathname === "/auth/callback"
    ) {
      setUser(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setUser(data);
    return data;
  }, []);

  const register = useCallback(async (name, email, password, consents, recoveryEmail = "") => {
    const { data } = await api.post("/auth/register", {
      name, email, password,
      recovery_email: recoveryEmail || undefined,
      consent_privacy: consents.privacy,
      consent_health_data: consents.health,
      consent_declaration: consents.declaration,
    });
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setUser(false);
    }
  }, []);

  const loginWithGoogle = useCallback(async () => {
    const redirectUrl = window.location.origin + "/auth/callback";
    try {
      const { data } = await api.get("/auth/google/url", {
        params: { redirect_uri: redirectUrl }
      });
      if (data?.url) {
        window.location.href = data.url;
        return;
      }
    } catch {
      // Fallback if backend URL endpoint is unavailable
    }
    const clientId = process.env.REACT_APP_GOOGLE_CLIENT_ID;
    if (clientId) {
      const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUrl,
        response_type: "code",
        scope: "openid email profile",
        access_type: "online",
        prompt: "select_account"
      });
      window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
    } else {
      window.location.href = "/auth";
    }
  }, []);

  const value = useMemo(
    () => ({ user, setUser, login, register, logout, loginWithGoogle, checkAuth }),
    [user, login, register, logout, loginWithGoogle, checkAuth]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
