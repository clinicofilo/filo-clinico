import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

const AuthCallback = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const hashParams = new URLSearchParams(location.hash.replace(/^#/, ""));
    const searchParams = new URLSearchParams(location.search);
    const sessionId = hashParams.get("session_id") || searchParams.get("session_id");
    const code = searchParams.get("code") || hashParams.get("code");
    const redirectUri = window.location.origin + "/auth/callback";

    (async () => {
      try {
        const payload = {};
        if (code) {
          payload.code = code;
          payload.redirect_uri = redirectUri;
        } else if (sessionId) {
          payload.session_id = sessionId;
        } else {
          throw new Error("Nessun parametro di autenticazione");
        }

        const { data } = await api.post("/auth/google/session", payload);
        window.history.replaceState(null, "", window.location.pathname);
        setUser(data);
        navigate(data.role === "admin" ? "/admin" : "/dashboard", { replace: true, state: { user: data } });
      } catch {
        toast.error("Accesso con Google non riuscito. Riprova.");
        navigate("/auth", { replace: true });
      }
    })();
  }, [location.hash, location.search, navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background" data-testid="auth-callback-loading">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
};

export default AuthCallback;
