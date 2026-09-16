import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { AppHeader } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

export const PaymentSuccess = () => {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState("polling"); // polling | paid | timeout
  const tries = useRef(0);

  useEffect(() => {
    const sessionId = searchParams.get("session_id");
    if (!sessionId) {
      setState("timeout");
      return;
    }
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          setState("paid");
          return;
        }
      } catch {
        // keep polling
      }
      tries.current += 1;
      if (tries.current < 15) {
        setTimeout(poll, 2000);
      } else {
        setState("timeout");
      }
    };
    poll();
  }, [searchParams]);

  const pending = JSON.parse(sessionStorage.getItem("pending_payment") || "null");
  const dossierLink = pending?.dossier_id ? `/dossier/${pending.dossier_id}` : "/dashboard";

  return (
    <div className="min-h-screen bg-background" data-testid="payment-success-page">
      <AppHeader />
      <main className="max-w-xl mx-auto px-6 py-24 text-center">
        {state === "polling" && (
          <>
            <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-6" />
            <h1 className="text-3xl text-primary mb-4">Verifica del pagamento...</h1>
            <p className="text-muted-foreground">Stiamo confermando il tuo pagamento con Stripe.</p>
          </>
        )}
        {state === "paid" && (
          <>
            <CheckCircle2 className="h-12 w-12 text-success mx-auto mb-6" />
            <h1 className="text-3xl text-primary mb-4" data-testid="payment-success-message">Pagamento confermato</h1>
            <p className="text-muted-foreground mb-10">
              Grazie! Il pagamento è andato a buon fine. Il medico inizierà a lavorare sulla tua richiesta.
            </p>
            <Link to={dossierLink}>
              <Button className="rounded-full px-8" data-testid="back-to-dossier-button">Vai al tuo dossier</Button>
            </Link>
          </>
        )}
        {state === "timeout" && (
          <>
            <XCircle className="h-12 w-12 text-muted-foreground mx-auto mb-6" />
            <h1 className="text-3xl text-primary mb-4" data-testid="payment-pending-message">Verifica in corso</h1>
            <p className="text-muted-foreground mb-10">
              Non siamo riusciti a confermare subito il pagamento. Se l'addebito è avvenuto,
              lo stato del dossier si aggiornerà a breve.
            </p>
            <Link to={dossierLink}>
              <Button variant="outline" className="rounded-full px-8" data-testid="back-to-dossier-timeout-button">
                Vai al tuo dossier
              </Button>
            </Link>
          </>
        )}
      </main>
    </div>
  );
};

export const PaymentCancel = () => {
  const pending = JSON.parse(sessionStorage.getItem("pending_payment") || "null");
  const dossierLink = pending?.dossier_id ? `/dossier/${pending.dossier_id}` : "/dashboard";

  return (
    <div className="min-h-screen bg-background" data-testid="payment-cancel-page">
      <AppHeader />
      <main className="max-w-xl mx-auto px-6 py-24 text-center">
        <XCircle className="h-12 w-12 text-muted-foreground mx-auto mb-6" />
        <h1 className="text-3xl text-primary mb-4" data-testid="payment-cancel-message">Pagamento annullato</h1>
        <p className="text-muted-foreground mb-10">
          Nessun addebito è stato effettuato. Puoi riprendere da dove avevi lasciato.
        </p>
        <Link to={dossierLink}>
          <Button className="rounded-full px-8" data-testid="cancel-back-button">Torna al dossier</Button>
        </Link>
      </main>
    </div>
  );
};
