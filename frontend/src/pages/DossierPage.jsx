import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API, api, formatApiError, PATIENT_STATUS_LABELS, STATUS_COLORS } from "@/lib/api";
import { AppHeader } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  ArrowLeft, CheckCircle2, ClipboardList, CreditCard, Download, ExternalLink, FileText,
  ImageIcon, Info, Loader2, Trash2, UploadCloud, Video,
} from "lucide-react";
import { PayPalScriptProvider, PayPalButtons } from "@paypal/react-paypal-js";

const QUESTIONNAIRE_URL = "https://docs.google.com/forms/d/e/1FAIpQLScvWLwY2iF58To9LSwj9UN6bmSf8Jb3tNnSV2j0SmYvUgNiMQ/viewform";

const PayPalPay = ({ lookupKey, dossierId, slotId, integrationType, onPaid, testid }) => (
  <div data-testid={testid}>
    <PayPalButtons
      style={{ layout: "horizontal", shape: "pill", height: 45, label: "paypal", tagline: false }}
      forceReRender={[lookupKey, dossierId, slotId, integrationType]}
      createOrder={async () => {
        const { data } = await api.post("/paypal/orders", {
          lookup_key: lookupKey,
          dossier_id: dossierId,
          slot_id: slotId || undefined,
          integration_type: integrationType || undefined,
        });
        return data.order_id;
      }}
      onApprove={async (d) => {
        try {
          await api.post(`/paypal/orders/${d.orderID}/capture`);
          toast.success("Pagamento PayPal confermato");
          onPaid();
        } catch (err) {
          toast.error(formatApiError(err.response?.data?.detail));
        }
      }}
      onError={() => toast.error("Pagamento PayPal non riuscito. Riprova.")}
    />
  </div>
);

const DossierPage = () => {
  const { id } = useParams();
  const [dossier, setDossier] = useState(null);
  const [slots, setSlots] = useState([]);
  const [integrationNote, setIntegrationNote] = useState("");
  const [uploading, setUploading] = useState(false);
  const [paying, setPaying] = useState("");
  const [integrationType, setIntegrationType] = useState("nuovi");
  const fileInput = useRef(null);

  const load = useCallback(async () => {
    try {
      const [{ data: d }, { data: s }] = await Promise.all([
        api.get(`/dossiers/${id}`),
        api.get("/slots"),
      ]);
      setDossier(d);
      setSlots(s);
    } catch {
      toast.error("Errore nel caricamento del dossier");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const onFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    setUploading(true);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    try {
      await api.post(`/dossiers/${id}/files`, fd);
      toast.success("Referti caricati con successo");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setUploading(false);
    }
  };

  const deleteFile = async (fileId) => {
    try {
      await api.delete(`/dossiers/${id}/files/${fileId}`);
      toast.success("Referto eliminato");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const startPayment = async (lookupKey, slotId = null, integrationType = null) => {
    if (lookupKey === "integrazione_dossier") {
      try {
        await api.post(`/dossiers/${id}/integration-note`, { note: integrationNote });
      } catch { /* la nota non blocca il pagamento */ }
    }
    setPaying(lookupKey);
    try {
      const { data } = await api.post("/payments/checkout", {
        lookup_key: lookupKey,
        origin_url: window.location.origin,
        dossier_id: id,
        slot_id: slotId,
        integration_type: integrationType,
      });
      sessionStorage.setItem("pending_payment", JSON.stringify({ dossier_id: id, type: lookupKey }));
      window.location.href = data.checkout_url;
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setPaying("");
    }
  };

  if (!dossier) {
    return (
      <div className="min-h-screen bg-background">
        <AppHeader />
        <div className="flex justify-center py-32">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </div>
    );
  }

  const bookedSlot = dossier.consult_slot_id
    ? slots.find((s) => s.slot_id === dossier.consult_slot_id)
    : null;
  const completed = dossier.status === "completato";
  const canUpload = !completed || dossier.integration_pending;
  const questionnaireDone = !!dossier.questionnaire_done;
  const questionnaireUrl = `${QUESTIONNAIRE_URL}?usp=pp_url&entry.1846449771=${encodeURIComponent(dossier?.patient_email || "")}`;

  const confirmQuestionnaire = async () => {
    try {
      await api.post(`/dossiers/${id}/questionnaire-done`);
      toast.success("Questionario confermato. Ora puoi caricare i referti.");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  return (
    <PayPalScriptProvider options={{ clientId: process.env.REACT_APP_PAYPAL_CLIENT_ID, currency: "EUR", intent: "capture" }}>
    <div className="min-h-screen bg-background" data-testid="dossier-page">
      <AppHeader />
      <main className="max-w-5xl mx-auto px-6 py-12">
        <Link to="/dashboard" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary transition-colors duration-200 mb-8" data-testid="back-to-dashboard-link">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Torna ai dossier
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-6 mb-12">
          <div>
            <h1 className="text-3xl sm:text-4xl text-primary mb-3" data-testid="dossier-title">{dossier.title}</h1>
            <p className="text-muted-foreground">Paziente: {dossier.patient_name}</p>
          </div>
          <Badge className={`${STATUS_COLORS[dossier.status]} border-0 text-sm px-4 py-1.5`} data-testid="dossier-status-badge">
            {dossier.integration_pending ? "Integrazione in corso" : PATIENT_STATUS_LABELS[dossier.status]}
          </Badge>
        </div>

        {dossier.notes && (
          <div className="bg-muted rounded-2xl p-8 mb-10" data-testid="dossier-notes">
            <h2 className="font-serif text-xl text-primary mb-3">La tua descrizione</h2>
            <p className="text-foreground/80 whitespace-pre-wrap leading-relaxed">{dossier.notes}</p>
          </div>
        )}

        <section className="bg-card border border-border rounded-2xl p-8 mb-10" data-testid="questionnaire-section">
          <div className="flex flex-wrap items-center justify-between gap-6">
            <div className="max-w-2xl">
              <h2 className="font-serif text-xl text-primary mb-2 flex items-center gap-3 flex-wrap">
                <ClipboardList className="h-6 w-6 text-secondary" />
                Passo 1 — Questionario anamnestico
                <Badge className="bg-secondary/10 text-secondary border-0">obbligatorio</Badge>
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Prima di caricare i referti è necessario compilare il breve questionario sulla tua
                storia clinica (Google Moduli, si apre in una nuova scheda): serve al medico per
                preparare un dossier accurato. Dopo averlo inviato, conferma qui sotto per
                sbloccare il caricamento dei documenti.
              </p>
            </div>
            <div className="flex flex-col gap-3 shrink-0">
              <a href={questionnaireUrl} target="_blank" rel="noreferrer">
                <Button variant="outline" size="lg" className="rounded-full px-8 w-full" data-testid="questionnaire-button">
                  Compila il questionario
                  <ExternalLink className="h-4 w-4 ml-2" />
                </Button>
              </a>
              {questionnaireDone ? (
                <p className="text-sm font-medium text-success flex items-center gap-2" data-testid="questionnaire-done-label">
                  <CheckCircle2 className="h-4 w-4" />
                  Questionario compilato
                </p>
              ) : (
                <Button size="lg" className="rounded-full px-8" onClick={confirmQuestionnaire} data-testid="questionnaire-confirm-button">
                  Ho compilato il questionario
                </Button>
              )}
            </div>
          </div>
        </section>

        <section className="bg-card border border-border rounded-2xl p-8 mb-10" data-testid="upload-section">
          <h2 className="font-serif text-xl text-primary mb-2">Passo 2 — Referti caricati ({dossier.files?.length || 0})</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Immagini (JPG, PNG, WEBP, HEIC) o PDF, max 15MB per file.
          </p>

          {canUpload && !questionnaireDone && (
            <div className="border-2 border-dashed border-border rounded-2xl p-12 flex flex-col items-center gap-4 text-center mb-8" data-testid="upload-locked">
              <ClipboardList className="h-10 w-10 text-muted-foreground" />
              <p className="text-lg font-medium text-foreground">Caricamento bloccato</p>
              <p className="text-sm text-muted-foreground max-w-md">
                Per caricare i referti devi prima compilare il questionario anamnestico
                (Passo 1 qui sopra) e confermarlo con il pulsante "Ho compilato il questionario".
              </p>
            </div>
          )}

          {canUpload && questionnaireDone && (
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={uploading}
              className="w-full border-2 border-dashed border-border rounded-2xl p-12 flex flex-col items-center gap-4 hover:border-secondary hover:bg-muted/50 transition-colors duration-200 mb-8"
              data-testid="upload-dropzone"
            >
              {uploading ? (
                <Loader2 className="h-10 w-10 animate-spin text-secondary" />
              ) : (
                <UploadCloud className="h-10 w-10 text-secondary" />
              )}
              <span className="text-lg font-medium text-foreground">
                {uploading ? "Caricamento in corso..." : "Tocca qui per caricare i referti"}
              </span>
              <span className="text-sm text-muted-foreground">
                Puoi selezionare più file insieme, anche direttamente dalla fotocamera del telefono.
              </span>
            </button>
          )}
          <input
            ref={fileInput}
            type="file"
            multiple
            accept="image/*,.pdf,.heic"
            className="hidden"
            onChange={onFiles}
            data-testid="upload-referti-input"
          />

          {dossier.files?.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="files-grid">
              {dossier.files.map((f) => (
                <div key={f.file_id} className="relative group border border-border rounded-xl overflow-hidden bg-muted" data-testid={`file-item-${f.file_id}`}>
                  {f.mime?.startsWith("image/") ? (
                    <a href={`${API}/dossiers/${id}/files/${f.file_id}`} target="_blank" rel="noreferrer">
                      <img
                        src={`${API}/dossiers/${id}/files/${f.file_id}`}
                        alt={f.filename}
                        className="w-full h-32 object-cover"
                      />
                    </a>
                  ) : (
                    <a
                      href={`${API}/dossiers/${id}/files/${f.file_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="w-full h-32 flex flex-col items-center justify-center gap-2 text-muted-foreground"
                    >
                      <FileText className="h-8 w-8" />
                      <span className="text-xs px-2 truncate w-full text-center">{f.filename}</span>
                    </a>
                  )}
                  {canUpload && (
                    <button
                      type="button"
                      onClick={() => deleteFile(f.file_id)}
                      className="absolute top-2 right-2 bg-destructive text-destructive-foreground rounded-full p-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                      data-testid={`file-delete-${f.file_id}`}
                      aria-label={`Elimina ${f.filename}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="bg-accent/60 border border-border rounded-2xl p-6 mb-10 flex gap-4" data-testid="integration-info-banner">
          <Info className="h-6 w-6 text-secondary shrink-0 mt-0.5" />
          <p className="text-sm text-foreground/80 leading-relaxed">
            <strong className="text-foreground">Importante:</strong> allega fin da subito tutti i
            documenti rilevanti della storia clinica. Le integrazioni successive al dossier — per
            nuovi referti datati dopo l'ultima versione o per referti dimenticati in prima
            istanza — hanno un costo di 25 € + IVA e sono redatte entro 72 ore dalla richiesta.
          </p>
        </div>

        {!dossier.revisione_paid && (
          <section className="bg-primary text-primary-foreground rounded-2xl p-8 mb-10" data-testid="payment-section">
            <div className="flex flex-wrap items-center justify-between gap-6">
              <div>
                <h2 className="font-serif text-xl mb-2">Revisione referti + dossier — 50 € + IVA</h2>
                <p className="text-primary-foreground/75 max-w-xl">
                  Con il pagamento confermi l'invio dei referti al medico. Riceverai il riassunto
                  della storia clinica direttamente qui, nella tua area riservata.
                </p>
              </div>
              <Button
                variant="secondary"
                size="lg"
                className="rounded-full px-8"
                onClick={() => startPayment("revisione_referti")}
                disabled={paying !== "" || !(dossier.files?.length > 0)}
                data-testid="pay-review-button"
              >
                {paying === "revisione_referti" ? (
                  <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                ) : (
                  <CreditCard className="h-5 w-5 mr-2" />
                )}
                Paga 50 € + IVA con carta
              </Button>
            </div>
            {dossier.files?.length > 0 && (
              <div className="mt-6 pt-6 border-t border-primary-foreground/20">
                <p className="text-sm text-primary-foreground/60 mb-3">oppure paga con</p>
                <div className="max-w-xs">
                  <PayPalPay lookupKey="revisione_referti" dossierId={id} onPaid={load} testid="paypal-review-button" />
                </div>
              </div>
            )}
            {!(dossier.files?.length > 0) && (
              <p className="text-sm text-primary-foreground/60 mt-4" data-testid="pay-needs-files">
                Carica almeno un referto prima di procedere al pagamento.
              </p>
            )}
          </section>
        )}

        {(
          <section className="bg-card border border-border rounded-2xl p-8 mb-10" data-testid="consult-section">
            <h2 className="font-serif text-xl text-primary mb-2 flex items-center gap-3">
              <Video className="h-6 w-6 text-secondary" />
              Consulto video online — 50 € + IVA (facoltativo)
            </h2>
            {dossier.consult_slot_id ? (
              (() => {
                const dt = dossier.consult_datetime ? new Date(dossier.consult_datetime) : null;
                const diffMs = dt ? dt.getTime() - Date.now() : null;
                const days = diffMs !== null ? Math.floor(diffMs / 86400000) : null;
                const hours = diffMs !== null ? Math.round((diffMs % 86400000) / 3600000) : null;
                return (
                  <div className="rounded-xl border border-secondary/40 bg-secondary/5 p-6" data-testid="consult-booked-message">
                    <p className="text-xs font-semibold uppercase tracking-wide text-secondary mb-3">Il tuo consulto</p>
                    {dt && (
                      <p className="font-serif text-2xl text-primary capitalize" data-testid="consult-datetime">
                        {dt.toLocaleString("it-IT", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}
                      </p>
                    )}
                    {diffMs !== null && diffMs > 0 && (
                      <p className="text-sm text-muted-foreground mt-1" data-testid="consult-countdown">
                        {days > 0
                          ? `Mancano ${days} ${days === 1 ? "giorno" : "giorni"}${hours > 0 ? ` e circa ${hours} ore` : ""}`
                          : "Manca meno di un giorno"}
                      </p>
                    )}
                    {dossier.consult_meet_link ? (
                      <a href={dossier.consult_meet_link} target="_blank" rel="noreferrer" data-testid="consult-meet-link">
                        <Button variant="secondary" className="rounded-full mt-4">
                          <Video className="h-4 w-4 mr-2" />
                          Entra in videochiamata
                        </Button>
                      </a>
                    ) : (
                      <p className="text-sm text-muted-foreground mt-4" data-testid="consult-link-pending">
                        Il link di Google Meet arriverà all'email con cui ti sei registrato.
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground mt-4">
                      Questi dettagli ti sono stati inviati anche via email.
                    </p>
                  </div>
                );
              })()
            ) : slots.length === 0 ? (
              <p className="text-muted-foreground" data-testid="no-slots-message">
                Nessuno slot disponibile al momento: riprova nei prossimi giorni. Quando prenoterai,
                il link di Google Meet arriverà all'email con cui ti sei registrato.
              </p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-6">
                  Scegli giorno e ora: la videochiamata dura 30 minuti su Google Meet. Lo slot è
                  confermato solo dopo il pagamento; il link di Google Meet arriverà all'email
                  con cui ti sei registrato.
                </p>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="slots-grid">
                  {slots.map((s) => (
                    <div key={s.slot_id} className="border border-border rounded-xl p-5 flex flex-col gap-4" data-testid={`slot-card-${s.slot_id}`}>
                      <p className="font-medium text-foreground">
                        {new Date(s.datetime).toLocaleString("it-IT", {
                          weekday: "long", day: "numeric", month: "long",
                          hour: "2-digit", minute: "2-digit",
                        })}
                      </p>
                      <Button
                        variant="secondary"
                        className="rounded-full"
                        onClick={() => startPayment("consulto_video", s.slot_id)}
                        disabled={paying !== ""}
                        data-testid={`slot-book-button-${s.slot_id}`}
                      >
                        {paying === "consulto_video" ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <CreditCard className="h-4 w-4 mr-2" />
                        )}
                        Prenota e paga — 50 € + IVA
                      </Button>
                      <PayPalPay lookupKey="consulto_video" dossierId={id} slotId={s.slot_id} onPaid={load} testid={`paypal-slot-button-${s.slot_id}`} />
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>
        )}

        {completed && (
          <section className="bg-card border border-border rounded-2xl p-8" data-testid="summary-section">
            <h2 className="font-serif text-xl text-primary mb-6">Il tuo dossier è pronto</h2>
            {dossier.summary_file ? (
              <a href={`${API}/dossiers/${id}/summary-file`} target="_blank" rel="noreferrer">
                <Button className="rounded-full" data-testid="download-summary-button">
                  <Download className="h-4 w-4 mr-2" />
                  Scarica il dossier ({dossier.summary_file.filename})
                </Button>
              </a>
            ) : (
              <p className="text-muted-foreground" data-testid="summary-pending-message">
                Il documento sarà disponibile a breve in formato PDF.
              </p>
            )}
          </section>
        )}

        {completed && !dossier.integration_pending && (
          <section className="bg-card border border-border rounded-2xl p-8" data-testid="integration-section">
            <h2 className="font-serif text-xl text-primary mb-3">Integrazione del dossier — 25 € + IVA</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-6">
              Puoi richiedere l'aggiornamento del dossier in due casi: <strong className="text-foreground">nuovi
              referti</strong> con data successiva all'ultima versione del dossier, oppure
              <strong className="text-foreground"> referti dimenticati</strong> non allegati in prima istanza.
              L'integrazione è redatta entro 72 ore dalla richiesta.
            </p>
            <div className="mb-6 space-y-2">
              <label htmlFor="integration-note" className="text-sm font-medium text-foreground">
                Breve raccordo anamnestico (facoltativo)
              </label>
              <textarea
                id="integration-note"
                value={integrationNote}
                onChange={(e) => setIntegrationNote(e.target.value)}
                placeholder="Descrivi brevemente cosa è cambiato dalla redazione del dossier: nuovi sintomi, esami fatti, terapie iniziate... Non serve compilare di nuovo il questionario."
                className="w-full min-h-28 rounded-md border border-input bg-background px-4 py-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                data-testid="integration-note-input"
              />
              <p className="text-xs text-muted-foreground">
                Il medico leggerà questa nota insieme ai nuovi referti che caricherai dopo il pagamento.
              </p>
            </div>
            <div className="mb-6">
              <Select value={integrationType} onValueChange={setIntegrationType}>
                <SelectTrigger className="w-full sm:w-96 h-12 text-base" data-testid="integration-type-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="nuovi" data-testid="integration-type-nuovi">Nuovi referti (successivi al dossier)</SelectItem>
                  <SelectItem value="dimenticati" data-testid="integration-type-dimenticati">Referti dimenticati (precedenti al dossier)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-wrap items-center gap-6">
              <Button
                onClick={() => startPayment("integrazione_dossier", null, integrationType)}
                disabled={paying !== ""}
                className="rounded-full"
                data-testid="pay-integration-button"
              >
                {paying === "integrazione_dossier" ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <CreditCard className="h-4 w-4 mr-2" />
                )}
                Paga 25 € + IVA con carta
              </Button>
              <div className="w-full sm:w-72" onClickCapture={() => { if (integrationNote.trim()) api.post(`/dossiers/${id}/integration-note`, { note: integrationNote }).catch(() => {}); }}>
                <PayPalPay lookupKey="integrazione_dossier" dossierId={id} integrationType={integrationType} onPaid={load} testid="paypal-integration-button" />
              </div>
            </div>
          </section>
        )}

        {completed && dossier.integration_pending && (
          <section className="bg-secondary/10 border border-secondary/30 rounded-2xl p-8" data-testid="integration-pending-section">
            <h2 className="font-serif text-xl text-primary mb-2">Integrazione in corso</h2>
            <p className="text-foreground/80 leading-relaxed">
              Il medico sta aggiornando il tuo dossier: riceverai l'integrazione entro 72 ore.
              Puoi già caricare i nuovi referti nella sezione qui sopra.
            </p>
          </section>
        )}

        {dossier.revisione_paid && !completed && (
          <p className="text-sm text-muted-foreground flex items-center gap-2" data-testid="waiting-summary-message">
            <ImageIcon className="h-4 w-4" />
            Il medico sta lavorando al tuo dossier: il riassunto apparirà qui appena pronto.
          </p>
        )}
      </main>
    </div>
    </PayPalScriptProvider>
  );
};

export default DossierPage;
