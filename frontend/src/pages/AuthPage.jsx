import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { FileText, Loader2 } from "lucide-react";

const AuthPage = () => {
  const { login, register, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [consents, setConsents] = useState({ privacy: false, health: false, declaration: false });
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSent, setForgotSent] = useState(false);

  const goHome = (user) => navigate(user.role === "admin" ? "/admin" : "/dashboard", { replace: true });

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await login(email, password);
      goHome(user);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");
    if (!consents.privacy || !consents.health || !consents.declaration) {
      setError("Devi accettare tutti i consensi obbligatori per registrarti.");
      return;
    }
    setLoading(true);
    try {
      const user = await register(name, email, password, consents, recoveryEmail);
      goHome(user);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    setForgotLoading(true);
    try {
      await api.post("/auth/forgot-password", { email: forgotEmail });
    } catch {
      // non rivelare l'esistenza dell'account
    } finally {
      setForgotSent(true);
      setForgotLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col" data-testid="auth-page">
      <header className="border-b border-border bg-background">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <Link to="/" className="flex items-center gap-2 text-primary w-fit" data-testid="auth-logo-link">
            <FileText className="h-6 w-6" />
            <span className="font-serif text-xl font-semibold">FiloClinico</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-md">
          <h1 className="text-3xl text-primary mb-2" data-testid="auth-title">Area riservata</h1>
          <p className="text-muted-foreground mb-10">
            Accedi o crea un account per caricare i tuoi referti.
          </p>

          <Button
            variant="outline"
            className="w-full rounded-full py-6 text-base mb-8"
            onClick={loginWithGoogle}
            data-testid="google-login-button"
          >
            <svg className="h-5 w-5 mr-3" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Continua con Google
          </Button>

          <div className="flex items-center gap-4 mb-8">
            <div className="h-px bg-border flex-1" />
            <span className="text-sm text-muted-foreground">oppure con email</span>
            <div className="h-px bg-border flex-1" />
          </div>

          <Tabs defaultValue="login" data-testid="auth-tabs">
            <TabsList className="grid w-full grid-cols-2 mb-8">
              <TabsTrigger value="login" data-testid="tab-login">Accedi</TabsTrigger>
              <TabsTrigger value="register" data-testid="tab-register">Registrati</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <form onSubmit={handleLogin} className="space-y-6" data-testid="login-form">
                <div className="space-y-2">
                  <Label htmlFor="login-email">Email</Label>
                  <Input
                    id="login-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="auth-email-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="login-password">Password</Label>
                  <Input
                    id="login-password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="auth-password-input"
                  />
                </div>
                <div className="text-right">
                  <button
                    type="button"
                    onClick={() => { setForgotEmail(email); setForgotSent(false); setForgotOpen(true); }}
                    className="text-sm text-secondary hover:underline"
                    data-testid="forgot-password-link"
                  >
                    Hai dimenticato la password?
                  </button>
                </div>
                {error && <p className="text-destructive text-sm" data-testid="auth-error">{error}</p>}
                <Button type="submit" className="w-full rounded-full py-6 text-base" disabled={loading} data-testid="login-submit-button">
                  {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Accedi
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="register">
              <form onSubmit={handleRegister} className="space-y-6" data-testid="register-form">
                <div className="space-y-2">
                  <Label htmlFor="register-name">Nome e cognome</Label>
                  <Input
                    id="register-name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="auth-name-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-email">Email</Label>
                  <Input
                    id="register-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="auth-register-email-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-password">Password (min. 8 caratteri: almeno 6 lettere, un numero e un carattere speciale)</Label>
                  <Input
                    id="register-password"
                    type="password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="p-4 h-12 text-base"
                    data-testid="auth-register-password-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-recovery-email">Email di recupero password (facoltativa)</Label>
                  <Input
                    id="register-recovery-email"
                    type="email"
                    value={recoveryEmail}
                    onChange={(e) => setRecoveryEmail(e.target.value)}
                    placeholder="Una seconda email tua, per sicurezza"
                    className="p-4 h-12 text-base"
                    data-testid="auth-recovery-email-input"
                  />
                </div>
                <div className="space-y-4 rounded-xl border border-border p-5 bg-muted/40" data-testid="consents-section">
                  <p className="text-sm font-semibold text-foreground">Consensi obbligatori (GDPR)</p>
                  {[
                    {
                      key: "privacy",
                      testid: "consent-privacy-checkbox",
                      label: <>Dichiaro di aver letto e compreso la <a href="/privacy" target="_blank" rel="noreferrer" className="text-secondary underline">informativa privacy</a> e acconsento al trattamento dei miei dati personali per la registrazione e l'erogazione del servizio (art. 6 GDPR).</>,
                    },
                    {
                      key: "health",
                      testid: "consent-health-checkbox",
                      label: <>Acconsento esplicitamente al trattamento dei dati relativi alla salute — miei o del familiare per cui richiedo il servizio — inclusi referti e documentazione clinica caricata, necessari alla redazione del riassunto della storia clinica (art. 9, par. 2, lett. a GDPR).</>,
                    },
                    {
                      key: "declaration",
                      testid: "consent-declaration-checkbox",
                      label: <>Dichiaro di essere maggiorenne e, qualora carichi documentazione sanitaria di un familiare o di altra persona, di essere da questi espressamente autorizzato al trattamento dei suoi dati.</>,
                    },
                  ].map((c) => (
                    <label key={c.key} className="flex items-start gap-3 cursor-pointer text-sm text-foreground/80 leading-relaxed">
                      <input
                        type="checkbox"
                        checked={consents[c.key]}
                        onChange={(e) => setConsents({ ...consents, [c.key]: e.target.checked })}
                        className="h-5 w-5 mt-0.5 shrink-0 cursor-pointer accent-[#1A2942]"
                        data-testid={c.testid}
                      />
                      <span>{c.label}</span>
                    </label>
                  ))}
                </div>
                {error && <p className="text-destructive text-sm" data-testid="auth-register-error">{error}</p>}
                <Button type="submit" className="w-full rounded-full py-6 text-base" disabled={loading} data-testid="register-submit-button">
                  {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Crea account
                </Button>
              </form>
            </TabsContent>
          </Tabs>

          <Dialog open={forgotOpen} onOpenChange={setForgotOpen}>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle className="font-serif text-2xl">Recupero password</DialogTitle>
                <DialogDescription>
                  Inserisci la tua email: ti invieremo un link per reimpostare la password (valido 30 minuti, utilizzabile una sola volta).
                </DialogDescription>
              </DialogHeader>
              {forgotSent ? (
                <p className="text-success text-sm py-4" data-testid="forgot-sent-message">
                  Se l'email è registrata, riceverai a breve il link di ripristino. Controlla anche la cartella spam.
                </p>
              ) : (
                <form onSubmit={handleForgot} className="space-y-5 mt-2" data-testid="forgot-form">
                  <div className="space-y-2">
                    <Label htmlFor="forgot-email">Email</Label>
                    <Input
                      id="forgot-email"
                      type="email"
                      required
                      value={forgotEmail}
                      onChange={(e) => setForgotEmail(e.target.value)}
                      className="p-4 h-12 text-base"
                      data-testid="forgot-email-input"
                    />
                  </div>
                  <Button type="submit" className="w-full rounded-full" disabled={forgotLoading} data-testid="forgot-submit-button">
                    {forgotLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    Invia link di ripristino
                  </Button>
                </form>
              )}
            </DialogContent>
          </Dialog>
        </div>
      </main>
    </div>
  );
};

export default AuthPage;
