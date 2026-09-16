import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatApiError, PATIENT_STATUS_LABELS, STATUS_COLORS } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AppHeader } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { FolderOpen, Loader2, Plus, Trash2 } from "lucide-react";

const PatientDashboard = () => {
  const [dossiers, setDossiers] = useState(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ title: "", patient_name: "", relationship: "me" });
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteEmail, setDeleteEmail] = useState("");
  const [deleting, setDeleting] = useState(false);
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/dossiers");
      setDossiers(data);
    } catch {
      toast.error("Errore nel caricamento dei dossier");
      setDossiers([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const deleteAccount = async (e) => {
    e.preventDefault();
    setDeleting(true);
    try {
      await api.post("/auth/delete-account", {
        password: deletePassword,
        confirm_email: deleteEmail,
      });
      toast.success("Account eliminato. I tuoi dossier e referti sono stati rimossi.");
      setUser(false);
      navigate("/");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setDeleting(false);
    }
  };

  const create = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/dossiers", form);
      toast.success("Dossier creato. Ora carica i tuoi referti.");
      setOpen(false);
      setForm({ title: "", patient_name: "", relationship: "me" });
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background" data-testid="patient-dashboard">
      <AppHeader />
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-6 mb-12">
          <div>
            <h1 className="text-3xl sm:text-4xl text-primary mb-2" data-testid="dashboard-title">I tuoi dossier</h1>
            <p className="text-muted-foreground">
              Crea un dossier, carica i referti e richiedi il riassunto della storia clinica.
            </p>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="rounded-full" data-testid="create-dossier-button">
                <Plus className="h-4 w-4 mr-2" />
                Nuovo dossier
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle className="font-serif text-2xl">Nuovo dossier clinico</DialogTitle>
                <DialogDescription>
                  Inserisci i dati del paziente e una breve descrizione della situazione clinica.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={create} className="space-y-5 mt-4" data-testid="create-dossier-form">
                <div className="space-y-2">
                  <Label htmlFor="dossier-title">Titolo del dossier</Label>
                  <Input
                    id="dossier-title"
                    required
                    placeholder="Es. Storia clinica di Mario Rossi"
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    className="p-4 h-12 text-base"
                    data-testid="dossier-title-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dossier-patient">Nome e cognome del paziente</Label>
                  <Input
                    id="dossier-patient"
                    required
                    value={form.patient_name}
                    onChange={(e) => setForm({ ...form, patient_name: e.target.value })}
                    className="p-4 h-12 text-base"
                    data-testid="dossier-patient-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Il dossier è per</Label>
                  <Select
                    value={form.relationship}
                    onValueChange={(v) => setForm({ ...form, relationship: v })}
                  >
                    <SelectTrigger className="h-12 text-base" data-testid="dossier-relationship-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="me" data-testid="relationship-me">Me stesso</SelectItem>
                      <SelectItem value="familiare" data-testid="relationship-familiare">Un familiare che assisto</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed rounded-xl bg-muted/60 p-4" data-testid="questionnaire-hint">
                  Nella pagina successiva troverai un breve <strong className="text-foreground">questionario</strong> sulla
                  situazione clinica, da compilare prima di allegare foto e documenti.
                </p>
                <Button type="submit" className="w-full rounded-full py-6 text-base" disabled={loading} data-testid="dossier-submit-button">
                  {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Crea dossier
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {dossiers === null ? (
          <div className="flex justify-center py-24">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : dossiers.length === 0 ? (
          <div className="text-center py-24 border border-dashed border-border rounded-2xl" data-testid="empty-dossiers">
            <FolderOpen className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-lg text-muted-foreground">
              Non hai ancora nessun dossier. Creane uno per iniziare.
            </p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="dossiers-grid">
            {dossiers.map((d) => (
              <Link
                key={d.dossier_id}
                to={`/dossier/${d.dossier_id}`}
                className="bg-card border border-border rounded-2xl p-8 hover:shadow-sm hover:-translate-y-0.5 transition-all duration-200 block"
                data-testid={`dossier-card-${d.dossier_id}`}
              >
                <div className="flex items-start justify-between gap-4 mb-4">
                  <h3 className="font-serif text-xl text-primary leading-snug">{d.title}</h3>
                  <Badge className={`${STATUS_COLORS[d.status]} border-0 shrink-0`} data-testid={`dossier-status-${d.dossier_id}`}>
                    {d.integration_pending ? "Integrazione in corso" : PATIENT_STATUS_LABELS[d.status]}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground mb-2">Paziente: {d.patient_name}</p>
                <p className="text-sm text-muted-foreground mb-4">
                  {d.files?.length || 0} referti caricati
                </p>
                <p className="text-xs text-muted-foreground">
                  Creato il {new Date(d.created_at).toLocaleDateString("it-IT")}
                </p>
              </Link>
            ))}
          </div>
        )}

        <div className="mt-20 pt-6 border-t border-border flex flex-wrap items-center justify-between gap-4" data-testid="danger-zone">
          <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl" data-testid="delete-account-banner">
            Eliminando l'account rimuovi definitivamente profilo, dossier e referti caricati. I referti già copiati
            sull'archivio del medico restano disponibili al medico che ha redatto il dossier; ricevute di pagamento e
            consensi privacy sono conservati per obblighi fiscali e di legge.
          </p>
          <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" data-testid="delete-account-button">
                <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                Elimina account
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle className="font-serif text-2xl text-destructive">Eliminare definitivamente l'account?</DialogTitle>
                <DialogDescription>
                  L'operazione non è reversibile: account, dossier e referti caricati verranno eliminati.
                  I referti già copiati sul Drive del medico resteranno disponibili al medico che ha redatto il dossier.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={deleteAccount} className="space-y-5 mt-4" data-testid="delete-account-form">
                {user?.has_password ? (
                  <div className="space-y-2">
                    <Label htmlFor="delete-password">Conferma con la tua password</Label>
                    <Input
                      id="delete-password"
                      type="password"
                      required
                      value={deletePassword}
                      onChange={(e) => setDeletePassword(e.target.value)}
                      className="p-4 h-12 text-base"
                      data-testid="delete-account-password-input"
                    />
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label htmlFor="delete-email">Conferma con la tua email di registrazione</Label>
                    <p className="text-sm text-muted-foreground">
                      Hai effettuato l'accesso con Google, quindi non hai una password: digita la tua email per confermare.
                    </p>
                    <Input
                      id="delete-email"
                      type="email"
                      required
                      placeholder={user?.email || ""}
                      value={deleteEmail}
                      onChange={(e) => setDeleteEmail(e.target.value)}
                      className="p-4 h-12 text-base"
                      data-testid="delete-account-email-input"
                    />
                  </div>
                )}
                <Button type="submit" variant="destructive" className="w-full rounded-full py-6 text-base" disabled={deleting} data-testid="delete-account-confirm-button">
                  {deleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Elimina definitivamente
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </main>
    </div>
  );
};

export default PatientDashboard;
