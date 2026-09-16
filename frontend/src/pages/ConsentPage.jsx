import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AppHeader } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Loader2, ShieldCheck } from "lucide-react";

const ConsentPage = () => {
  const [consents, setConsents] = useState({ privacy: false, health: false, declaration: false });
  const [loading, setLoading] = useState(false);
  const { checkAuth } = useAuth();
  const navigate = useNavigate();

  const submit = async () => {
    if (!consents.privacy || !consents.health || !consents.declaration) {
      toast.error("Devi accettare tutti i consensi obbligatori per continuare.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/consents", {
        consent_privacy: consents.privacy,
        consent_health_data: consents.health,
        consent_declaration: consents.declaration,
      });
      await checkAuth();
      toast.success("Consensi registrati. Benvenuto!");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background" data-testid="consent-page">
      <AppHeader />
      <main className="max-w-2xl mx-auto px-6 py-16">
        <ShieldCheck className="h-12 w-12 text-secondary mb-6" />
        <h1 className="text-3xl text-primary mb-4" data-testid="consent-title">Consenso al trattamento dei dati</h1>
        <p className="text-muted-foreground leading-relaxed mb-10">
          Prima di utilizzare il servizio è necessario il tuo consenso al trattamento dei dati
          personali e sanitari, come richiesto dal GDPR e dal Garante per la protezione dei dati
          personali. Leggi l'<a href="/privacy" target="_blank" rel="noreferrer" className="text-secondary underline">informativa privacy completa</a>.
        </p>

        <div className="space-y-5 bg-card border border-border rounded-2xl p-8 mb-8" data-testid="consent-form-section">
          {[
            {
              key: "privacy",
              testid: "consent-page-privacy-checkbox",
              label: <>Dichiaro di aver letto e compreso la <a href="/privacy" target="_blank" rel="noreferrer" className="text-secondary underline">informativa privacy</a> e acconsento al trattamento dei miei dati personali per l'erogazione del servizio (art. 6 GDPR).</>,
            },
            {
              key: "health",
              testid: "consent-page-health-checkbox",
              label: <>Acconsento esplicitamente al trattamento dei dati relativi alla salute — miei o del familiare per cui richiedo il servizio — inclusi referti e documentazione clinica caricata, necessari alla redazione del riassunto della storia clinica (art. 9, par. 2, lett. a GDPR).</>,
            },
            {
              key: "declaration",
              testid: "consent-page-declaration-checkbox",
              label: <>Dichiaro di essere maggiorenne e, qualora carichi documentazione sanitaria di un familiare o di altra persona, di essere da questi espressamente autorizzato al trattamento dei suoi dati.</>,
            },
          ].map((c) => (
            <label key={c.key} className="flex items-start gap-3 cursor-pointer text-foreground/80 leading-relaxed">
              <input
                type="checkbox"
                checked={consents[c.key]}
                onChange={(e) => setConsents({ ...consents, [c.key]: e.target.checked })}
                className="h-5 w-5 mt-1 shrink-0 cursor-pointer accent-[#1A2942]"
                data-testid={c.testid}
              />
              <span>{c.label}</span>
            </label>
          ))}
        </div>

        <Button onClick={submit} className="w-full rounded-full py-6 text-base" disabled={loading} data-testid="consent-submit-button">
          {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Conferma e continua
        </Button>
        <p className="text-xs text-muted-foreground mt-6 leading-relaxed">
          Puoi revocare il consenso in qualsiasi momento scrivendo a dott.spitaleripietro@gmail.com.
          La revoca non pregiudica la liceità del trattamento effettuato prima della revoca.
        </p>
      </main>
    </div>
  );
};

export default ConsentPage;
