import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileText, Loader2, CheckCircle2 } from "lucide-react";

const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Le due password non coincidono.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, password });
      setDone(true);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col" data-testid="reset-password-page">
      <header className="border-b border-border bg-background">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <Link to="/" className="flex items-center gap-2 text-primary w-fit" data-testid="reset-logo-link">
            <FileText className="h-6 w-6" />
            <span className="font-serif text-xl font-semibold">FiloClinico</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-md">
          {done ? (
            <div className="text-center" data-testid="reset-success">
              <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-6" />
              <h1 className="text-3xl text-primary mb-4">Password aggiornata</h1>
              <p className="text-muted-foreground mb-8">
                La tua password è stata reimpostata con successo. Ora puoi accedere.
              </p>
              <Button className="rounded-full px-8" onClick={() => navigate("/auth")} data-testid="reset-go-login-button">
                Vai al login
              </Button>
            </div>
          ) : (
            <>
              <h1 className="text-3xl text-primary mb-2" data-testid="reset-title">Nuova password</h1>
              <p className="text-muted-foreground mb-10">
                Scegli una nuova password: almeno 8 caratteri, di cui almeno 6 lettere,
                un numero e un carattere speciale.
              </p>
              {!token && (
                <p className="text-destructive text-sm mb-6" data-testid="reset-no-token">
                  Link non valido: manca il token. Richiedi una nuova email di ripristino.
                </p>
              )}
              <form onSubmit={submit} className="space-y-6" data-testid="reset-form">
                <div className="space-y-2">
                  <Label htmlFor="new-password">Nuova password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="reset-password-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Conferma password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="reset-confirm-input"
                  />
                </div>
                {error && <p className="text-destructive text-sm" data-testid="reset-error">{error}</p>}
                <Button type="submit" className="w-full rounded-full py-6 text-base" disabled={loading || !token} data-testid="reset-submit-button">
                  {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Reimposta password
                </Button>
              </form>
            </>
          )}
        </div>
      </main>
    </div>
  );
};

export default ResetPassword;
