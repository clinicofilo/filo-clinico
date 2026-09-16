import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API, api, formatApiError } from "@/lib/api";
import { AppHeader } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  ArrowLeft, ClipboardList, FileText, Loader2, Save, Upload,
} from "lucide-react";

const DoctorDossierPage = () => {
  const { id } = useParams();
  const [dossier, setDossier] = useState(null);
  const [status, setStatus] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editName, setEditName] = useState("");
  const [pdfFile, setPdfFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const pdfInput = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/dossiers/${id}`);
      setDossier(data);
      setStatus(data.status === "completato" ? "completato" : "pagato");
      setEditTitle(data.title || "");
      setEditName(data.patient_name || "");
    } catch {
      toast.error("Errore nel caricamento del dossier");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/dossiers/${id}`, { status, title: editTitle, patient_name: editName });
      if (pdfFile) {
        const fd = new FormData();
        fd.append("file", pdfFile);
        await api.post(`/dossiers/${id}/summary-file`, fd);
        setPdfFile(null);
        if (pdfInput.current) pdfInput.current.value = "";
      }
      toast.success("Dossier aggiornato");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
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

  return (
    <div className="min-h-screen bg-background" data-testid="doctor-dossier-page">
      <AppHeader />
      <main className="max-w-7xl mx-auto px-6 py-12">
        <Link to="/admin" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary transition-colors duration-200 mb-8" data-testid="back-to-admin-link">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Torna all'area medico
        </Link>

        <div className="grid lg:grid-cols-2 gap-10">
          <div>
            <div className="bg-muted/60 border border-border rounded-2xl p-6 mb-8 space-y-4" data-testid="dossier-edit-header">
              <div className="space-y-2">
                <Label htmlFor="edit-title">Titolo del dossier</Label>
                <Input
                  id="edit-title"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="h-12 text-base bg-card"
                  data-testid="edit-title-input"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-patient-name">Nome e cognome del paziente</Label>
                <Input
                  id="edit-patient-name"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="h-12 text-base bg-card"
                  data-testid="edit-patient-name-input"
                />
              </div>
              <p className="text-sm text-muted-foreground">
                Account: {dossier.patient_account_name} ({dossier.patient_email}) ·{" "}
                {dossier.relationship === "familiare" ? "Dossier per un familiare" : "Dossier personale"} ·{" "}
                Creato il {new Date(dossier.created_at).toLocaleDateString("it-IT")}
              </p>
              <div className="flex flex-wrap items-center gap-4 pt-2">
                <a
                  href="https://docs.google.com/forms/d/1O3Cp3GnFtW8cevhgm82jnwbSQRJ9gCclunzJoLReVjE/edit#responses"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Button variant="outline" className="rounded-full" data-testid="questionnaire-responses-button">
                    <ClipboardList className="h-4 w-4 mr-2" />
                    Risposte questionario
                  </Button>
                </a>
                <p className="text-xs text-muted-foreground max-w-md">
                  Si apre Google Moduli (serve il tuo account Google). La risposta di questo
                  paziente è abbinata alla sua email: <strong className="text-foreground">{dossier.patient_email}</strong>
                </p>
              </div>
            </div>

            {dossier.notes && (
              <div className="bg-muted rounded-2xl p-6 mb-8" data-testid="doctor-dossier-notes">
                <h2 className="font-serif text-lg text-primary mb-2">Note del paziente</h2>
                <p className="text-foreground/80 whitespace-pre-wrap leading-relaxed text-sm">{dossier.notes}</p>
              </div>
            )}

            {dossier.integration_pending && (
              <div className="bg-secondary/10 border border-secondary/30 rounded-2xl p-6 mb-8" data-testid="doctor-integration-notice">
                <h2 className="font-serif text-lg text-primary mb-2">Integrazione richiesta (25 € pagati)</h2>
                <p className="text-sm text-foreground/80 leading-relaxed">
                  Il paziente ha richiesto un'integrazione
                  {dossier.integrations?.length > 0 && (
                    <> — tipo: <strong>{dossier.integrations[dossier.integrations.length - 1].type === "nuovi" ? "nuovi referti (successivi al dossier)" : "referti dimenticati (precedenti al dossier)"}</strong></>
                  )}
                  . Carica il PDF aggiornato qui a fianco per completarla: il flag si chiuderà automaticamente.
                </p>
                {dossier.integration_note && (
                  <div className="mt-3 bg-card border border-border rounded-xl p-4" data-testid="doctor-integration-note">
                    <p className="text-xs font-semibold uppercase tracking-wide text-secondary mb-1">
                      Raccordo anamnestico del paziente
                    </p>
                    <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">{dossier.integration_note}</p>
                  </div>
                )}
              </div>
            )}

            <h2 className="font-serif text-lg text-primary mb-4">
              Referti caricati ({dossier.files?.length || 0})
            </h2>
            {dossier.files?.length === 0 ? (
              <p className="text-muted-foreground text-sm" data-testid="doctor-no-files">Il paziente non ha ancora caricato referti.</p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-8" data-testid="doctor-files-grid">
                {dossier.files.map((f) => (
                  <a
                    key={f.file_id}
                    href={`${API}/dossiers/${id}/files/${f.file_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="border border-border rounded-xl overflow-hidden bg-muted hover:shadow-sm transition-shadow duration-200 block"
                    data-testid={`doctor-file-${f.file_id}`}
                  >
                    {f.mime?.startsWith("image/") ? (
                      <img
                        src={`${API}/dossiers/${id}/files/${f.file_id}`}
                        alt={f.filename}
                        className="w-full h-36 object-cover"
                      />
                    ) : (
                      <div className="w-full h-36 flex flex-col items-center justify-center gap-2 text-muted-foreground">
                        <FileText className="h-8 w-8" />
                        <span className="text-xs px-2 truncate w-full text-center">{f.filename}</span>
                      </div>
                    )}
                  </a>
                ))}
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-2xl p-8 h-fit space-y-8" data-testid="summary-editor">
            <div className="space-y-3">
              <Label>Stato del dossier</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="h-12 text-base" data-testid="status-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pagato" data-testid="status-pagato">Pagato — In lavorazione</SelectItem>
                  <SelectItem value="completato" data-testid="status-completato">Pronto</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-3">
              <Label>PDF del dossier</Label>
              <div className="flex items-center gap-4">
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-full"
                  onClick={() => pdfInput.current?.click()}
                  data-testid="summary-file-select-button"
                >
                  <Upload className="h-4 w-4 mr-2" />
                  {pdfFile ? pdfFile.name : "Scegli PDF"}
                </Button>
                {dossier.summary_file && !pdfFile && (
                  <a
                    href={`${API}/dossiers/${id}/summary-file`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-secondary hover:underline"
                    data-testid="current-summary-file-link"
                  >
                    Attuale: {dossier.summary_file.filename}
                  </a>
                )}
              </div>
              <input
                ref={pdfInput}
                type="file"
                accept=".pdf,image/*"
                className="hidden"
                onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
                data-testid="summary-file-input"
              />
            </div>

            <Button onClick={save} className="w-full rounded-full py-6 text-base" disabled={saving} data-testid="save-summary-button">
              {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              Salva e aggiorna il paziente
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default DoctorDossierPage;
