import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API, api, formatApiError, STATUS_COLORS, STATUS_LABELS } from "@/lib/api";
import { AppHeader } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  CalendarPlus, CheckCircle2, Download, FolderOpen, HardDrive, Loader2, Mail, Pencil, ShieldCheck, Trash2, Video,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

const EMAIL_TEMPLATE_LABELS = {
  dossier_pronto: "Dossier pronto",
  consulto_conferma: "Conferma consulto",
  consulto_promemoria: "Promemoria consulto",
  account_eliminato: "Eliminazione account",
  reset_password: "Reset password",
  generica: "Generica",
};

const DoctorDashboard = () => {
  const [dossiers, setDossiers] = useState(null);
  const [slots, setSlots] = useState([]);
  const [drive, setDrive] = useState(null);
  const [consents, setConsents] = useState([]);
  const [patients, setPatients] = useState([]);
  const [emails, setEmails] = useState([]);
  const [selectedConsents, setSelectedConsents] = useState([]);
  const [editSlot, setEditSlot] = useState(null);
  const [editLink, setEditLink] = useState("");
  const [selected, setSelected] = useState([]);
  const [slotForm, setSlotForm] = useState({ datetime: "", meet_link: "" });
  const [saving, setSaving] = useState(false);
  const [searchParams] = useSearchParams();

  const load = useCallback(async () => {
    try {
      const [{ data: d }, { data: s }, { data: dr }, { data: c }, { data: p }, { data: e }] = await Promise.all([
        api.get("/dossiers"),
        api.get("/slots"),
        api.get("/drive/status"),
        api.get("/admin/consents"),
        api.get("/admin/patients"),
        api.get("/admin/emails"),
      ]);
      setDossiers(d);
      setSlots(s);
      setDrive(dr);
      setConsents(c);
      setPatients(p);
      setEmails(e);
    } catch {
      toast.error("Errore nel caricamento");
      setDossiers([]);
    }
  }, []);

  useEffect(() => {
    load();
    if (searchParams.get("drive") === "ok") {
      toast.success("Google Drive collegato con successo");
    }
    if (searchParams.get("drive") === "error") {
      toast.error("Collegamento a Google Drive non riuscito. Riprova.");
    }
  }, [load, searchParams]);

  const addSlot = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/slots", {
        datetime: new Date(slotForm.datetime).toISOString(),
        meet_link: slotForm.meet_link,
      });
      toast.success("Slot aggiunto");
      setSlotForm({ datetime: "", meet_link: "" });
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const deleteSlot = async (slotId) => {
    try {
      await api.delete(`/slots/${slotId}`);
      toast.success("Slot eliminato");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const deleteDossier = async (dossierId, title) => {
    if (!window.confirm(`Eliminare definitivamente il dossier "${title}"? L'operazione non è reversibile.`)) return;
    try {
      await api.delete(`/dossiers/${dossierId}`);
      toast.success("Dossier eliminato");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const deletePatient = async (patient) => {
    if (!window.confirm(`Eliminare definitivamente l'account di ${patient.name || patient.email} e tutti i suoi dossier e referti? L'operazione non è reversibile. I file già copiati sul tuo Drive non verranno rimossi.`)) return;
    try {
      await api.delete(`/admin/patients/${patient.user_id}`);
      toast.success("Account paziente eliminato");
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const consentKey = (c) => `${c.user_id}|${c.created_at}`;

  const toggleConsent = (c) =>
    setSelectedConsents((prev) => (prev.includes(consentKey(c)) ? prev.filter((x) => x !== consentKey(c)) : [...prev, consentKey(c)]));

  const allConsentsSelected = !!(consents.length > 0 && selectedConsents.length === consents.length);

  const toggleAllConsents = () => setSelectedConsents(allConsentsSelected ? [] : consents.map(consentKey));

  const deleteSelectedConsents = async () => {
    if (!window.confirm(`Eliminare definitivamente ${selectedConsents.length} consensi selezionati dal registro? L'operazione non è reversibile.`)) return;
    try {
      const items = selectedConsents.map((k) => {
        const [user_id, created_at] = k.split("|");
        return { user_id, created_at };
      });
      await api.post("/admin/consents/delete", { items });
      toast.success(`${selectedConsents.length} consensi eliminati`);
      setSelectedConsents([]);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const saveSlotLink = async (e) => {
    e.preventDefault();
    try {
      await api.put(`/slots/${editSlot.slot_id}`, { meet_link: editLink });
      toast.success(editSlot.status === "booked" && editLink
        ? "Link salvato: email di conferma inviata al paziente"
        : "Link aggiornato");
      setEditSlot(null);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const toggleSelect = (dossierId) =>
    setSelected((prev) => (prev.includes(dossierId) ? prev.filter((x) => x !== dossierId) : [...prev, dossierId]));

  const allSelected = !!(dossiers && dossiers.length > 0 && selected.length === dossiers.length);

  const toggleAll = () => setSelected(allSelected ? [] : dossiers.map((d) => d.dossier_id));

  const deleteSelected = async () => {
    if (!window.confirm(`Eliminare definitivamente i ${selected.length} dossier selezionati? L'operazione non è reversibile.`)) return;
    try {
      await Promise.all(selected.map((did) => api.delete(`/dossiers/${did}`)));
      toast.success(`${selected.length} dossier eliminati`);
      setSelected([]);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const connectDrive = async () => {
    try {
      const { data } = await api.get("/drive/connect");
      window.location.href = data.authorization_url;
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const stats = dossiers
    ? {
        totale: dossiers.length,
        in_lavorazione: dossiers.filter((d) => ["pagato", "in_lavorazione"].includes(d.status)).length,
        completati: dossiers.filter((d) => d.status === "completato").length,
      }
    : null;

  return (
    <div className="min-h-screen bg-background" data-testid="doctor-dashboard">
      <AppHeader />
      <main className="max-w-7xl mx-auto px-6 py-12">
        <h1 className="text-3xl sm:text-4xl text-primary mb-2" data-testid="doctor-title">Area medico</h1>
        <p className="text-muted-foreground mb-10">Gestisci dossier, disponibilità e archivio Drive.</p>

        {stats && (
          <div className="grid grid-cols-3 gap-4 mb-12" data-testid="doctor-stats">
            {[
              { label: "Dossier totali", value: stats.totale, testid: "stat-total" },
              { label: "Da revisionare", value: stats.in_lavorazione, testid: "stat-pending" },
              { label: "Completati", value: stats.completati, testid: "stat-completed" },
            ].map((s) => (
              <div key={s.label} className="bg-card border border-border rounded-2xl p-6" data-testid={s.testid}>
                <p className="font-serif text-3xl text-primary">{s.value}</p>
                <p className="text-sm text-muted-foreground mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        )}

        <Tabs defaultValue="dossier" data-testid="doctor-tabs">
          <TabsList className="mb-8">
            <TabsTrigger value="dossier" data-testid="tab-dossier">Dossier pazienti</TabsTrigger>
            <TabsTrigger value="slot" data-testid="tab-slots">Disponibilità video</TabsTrigger>
            <TabsTrigger value="drive" data-testid="tab-drive">Google Drive</TabsTrigger>
            <TabsTrigger value="consensi" data-testid="tab-consents">Consensi</TabsTrigger>
            <TabsTrigger value="pazienti" data-testid="tab-patients">Pazienti</TabsTrigger>
            <TabsTrigger value="email" data-testid="tab-emails">Email</TabsTrigger>
          </TabsList>

          <TabsContent value="dossier">
            {dossiers === null ? (
              <div className="flex justify-center py-16">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : dossiers.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-border rounded-2xl" data-testid="doctor-empty-dossiers">
                <FolderOpen className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">Nessun dossier ricevuto finora.</p>
              </div>
            ) : (
              <>
              {selected.length > 0 && (
                <div className="flex items-center justify-between mb-4 bg-secondary/10 border border-secondary/30 rounded-xl px-6 py-3" data-testid="bulk-actions-bar">
                  <span className="text-sm font-medium text-foreground" data-testid="selected-count">
                    {selected.length} dossier selezionati
                  </span>
                  <Button variant="destructive" size="sm" className="rounded-full" onClick={deleteSelected} data-testid="delete-selected-button">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Elimina selezionati
                  </Button>
                </div>
              )}
              <div className="bg-card border border-border rounded-2xl overflow-hidden" data-testid="doctor-dossiers-table">
                <table className="w-full text-left">
                  <thead className="bg-muted text-sm text-muted-foreground">
                    <tr>
                      <th className="px-6 py-4 w-10">
                        <input
                          type="checkbox"
                          checked={allSelected}
                          onChange={toggleAll}
                          className="h-5 w-5 cursor-pointer accent-[#1A2942]"
                          data-testid="select-all-checkbox"
                          aria-label="Seleziona tutti i dossier"
                        />
                      </th>
                      <th className="px-6 py-4 font-medium">Paziente</th>
                      <th className="px-6 py-4 font-medium hidden md:table-cell">Dossier</th>
                      <th className="px-6 py-4 font-medium hidden sm:table-cell">Referti</th>
                      <th className="px-6 py-4 font-medium">Stato</th>
                      <th className="px-6 py-4 font-medium hidden lg:table-cell">Data</th>
                      <th className="px-6 py-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {dossiers.map((d) => (
                      <tr key={d.dossier_id} className="hover:bg-muted/50 transition-colors duration-200" data-testid={`doctor-dossier-row-${d.dossier_id}`}>
                        <td className="px-6 py-4">
                          <input
                            type="checkbox"
                            checked={selected.includes(d.dossier_id)}
                            onChange={() => toggleSelect(d.dossier_id)}
                            className="h-5 w-5 cursor-pointer accent-[#1A2942]"
                            data-testid={`select-dossier-${d.dossier_id}`}
                            aria-label={`Seleziona dossier ${d.title}`}
                          />
                        </td>
                        <td className="px-6 py-4">
                          <p className="font-medium text-foreground">{d.patient_name}</p>
                          <p className="text-xs text-muted-foreground">{d.patient_email}</p>
                        </td>
                        <td className="px-6 py-4 hidden md:table-cell text-sm text-foreground/80">{d.title}</td>
                        <td className="px-6 py-4 hidden sm:table-cell text-sm">{d.files?.length || 0}</td>
                        <td className="px-6 py-4">
                          <Badge className={`${STATUS_COLORS[d.status]} border-0`}>{STATUS_LABELS[d.status]}</Badge>
                          {d.integration_pending && (
                            <Badge className="bg-secondary/10 text-secondary border-0 ml-2" data-testid={`integration-badge-${d.dossier_id}`}>
                              Integrazione richiesta
                            </Badge>
                          )}
                        </td>
                        <td className="px-6 py-4 hidden lg:table-cell text-sm text-muted-foreground">
                          {new Date(d.created_at).toLocaleDateString("it-IT")}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Link to={`/admin/dossier/${d.dossier_id}`}>
                              <Button variant="outline" size="sm" className="rounded-full" data-testid={`open-dossier-${d.dossier_id}`}>
                                Apri
                              </Button>
                            </Link>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => deleteDossier(d.dossier_id, d.title)}
                              data-testid={`delete-dossier-${d.dossier_id}`}
                              aria-label={`Elimina dossier ${d.title}`}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </>
            )}
          </TabsContent>

          <TabsContent value="slot">
            <div className="grid lg:grid-cols-3 gap-8">
              <form onSubmit={addSlot} className="bg-card border border-border rounded-2xl p-8 space-y-5 h-fit" data-testid="add-slot-form">
                <h2 className="font-serif text-xl text-primary flex items-center gap-2">
                  <CalendarPlus className="h-5 w-5 text-secondary" />
                  Nuovo slot
                </h2>
                <div className="space-y-2">
                  <Label htmlFor="slot-datetime">Data e ora</Label>
                  <Input
                    id="slot-datetime"
                    type="datetime-local"
                    required
                    value={slotForm.datetime}
                    onChange={(e) => setSlotForm({ ...slotForm, datetime: e.target.value })}
                    className="h-12 text-base"
                    data-testid="slot-datetime-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="slot-link">Link Google Meet / Zoom</Label>
                  <Input
                    id="slot-link"
                    type="url"
                    placeholder="https://meet.google.com/..."
                    value={slotForm.meet_link}
                    onChange={(e) => setSlotForm({ ...slotForm, meet_link: e.target.value })}
                    className="h-12 text-base"
                    data-testid="slot-link-input"
                  />
                </div>
                <Button type="submit" className="w-full rounded-full" disabled={saving} data-testid="add-slot-button">
                  {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Aggiungi slot
                </Button>
              </form>

              <div className="lg:col-span-2 space-y-4" data-testid="slots-list">
                {slots.length === 0 ? (
                  <p className="text-muted-foreground py-8">Nessuno slot creato.</p>
                ) : (
                  slots.map((s) => (
                    <div
                      key={s.slot_id}
                      className="bg-card border border-border rounded-xl p-6 flex flex-wrap items-center justify-between gap-4"
                      data-testid={`slot-row-${s.slot_id}`}
                    >
                      <div>
                        <p className="font-medium text-foreground flex items-center gap-2">
                          <Video className="h-4 w-4 text-secondary" />
                          {new Date(s.datetime).toLocaleString("it-IT", {
                            weekday: "long", day: "numeric", month: "long", year: "numeric",
                            hour: "2-digit", minute: "2-digit",
                          })}
                        </p>
                        {s.meet_link && (
                          <a href={s.meet_link} target="_blank" rel="noreferrer" className="text-xs text-secondary hover:underline">
                            {s.meet_link}
                          </a>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge className={s.status === "booked" ? "bg-success/10 text-success border-0" : "bg-accent text-accent-foreground border-0"}>
                          {s.status === "booked" ? "Prenotato" : "Disponibile"}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => { setEditSlot(s); setEditLink(s.meet_link || ""); }}
                          data-testid={`edit-slot-${s.slot_id}`}
                          aria-label="Modifica link Meet"
                        >
                          <Pencil className="h-4 w-4 text-primary" />
                        </Button>
                        {s.status !== "booked" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => deleteSlot(s.slot_id)}
                            data-testid={`delete-slot-${s.slot_id}`}
                            aria-label="Elimina slot"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </TabsContent>

          <Dialog open={!!editSlot} onOpenChange={(o) => !o && setEditSlot(null)}>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle className="font-serif text-2xl">Link Google Meet</DialogTitle>
                <DialogDescription>
                  {editSlot?.status === "booked"
                    ? "Salvando, il paziente riceve subito un'email di conferma con link, giorno e ora del consulto."
                    : "Lo slot non è ancora prenotato: il link verrà incluso automaticamente nell'email di conferma alla prenotazione."}
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={saveSlotLink} className="space-y-5 mt-4" data-testid="edit-slot-form">
                <div className="space-y-2">
                  <Label htmlFor="edit-slot-link">Link Google Meet / Zoom</Label>
                  <Input
                    id="edit-slot-link"
                    type="url"
                    placeholder="https://meet.google.com/..."
                    value={editLink}
                    onChange={(e) => setEditLink(e.target.value)}
                    className="h-12 text-base"
                    data-testid="edit-slot-link-input"
                  />
                </div>
                <Button type="submit" className="w-full rounded-full" data-testid="edit-slot-save-button">
                  Salva link
                </Button>
              </form>
            </DialogContent>
          </Dialog>

          <TabsContent value="drive">
            <div className="bg-card border border-border rounded-2xl p-10 max-w-2xl" data-testid="drive-panel">
              <HardDrive className="h-10 w-10 text-primary mb-6" />
              <h2 className="font-serif text-2xl text-primary mb-4">Archivio Google Drive</h2>
              {drive?.connected ? (
                <div className="flex items-center gap-3 text-success font-medium" data-testid="drive-connected">
                  <CheckCircle2 className="h-5 w-5" />
                  Google Drive collegato. I referti dei pazienti vengono salvati automaticamente
                  nella cartella "Dossier Pazienti", con una sottocartella per ciascun paziente.
                </div>
              ) : (
                <>
                  <p className="text-muted-foreground mb-8 leading-relaxed">
                    Collega il tuo account Google: ogni volta che un paziente carica un referto,
                    il file verrà copiato automaticamente in una cartella dedicata sul tuo Drive
                    ("Dossier Pazienti / Nome Paziente").
                  </p>
                  <Button onClick={connectDrive} className="rounded-full" data-testid="drive-connect-button">
                    Collega Google Drive
                  </Button>
                  {drive && !drive.configured && (
                    <p className="text-sm text-destructive mt-4" data-testid="drive-not-configured">
                      Le credenziali Google OAuth non sono ancora configurate sul server.
                    </p>
                  )}
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="consensi">
            <div className="bg-card border border-border rounded-2xl overflow-hidden" data-testid="consents-panel">
              <div className="flex flex-wrap items-center justify-between gap-4 p-6 border-b border-border">
                <div>
                  <h2 className="font-serif text-xl text-primary flex items-center gap-2">
                    <ShieldCheck className="h-5 w-5 text-secondary" />
                    Consensi informati registrati
                  </h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    Prova dei consensi GDPR di ogni utente: data, ora, indirizzo IP e versione dell'informativa accettata. Esibibili in caso di controllo.
                  </p>
                </div>
                <a href={`${API}/admin/consents/export`}>
                  <Button variant="outline" className="rounded-full" data-testid="export-consents-button">
                    <Download className="h-4 w-4 mr-2" />
                    Esporta CSV
                  </Button>
                </a>
              </div>
              {consents.length === 0 ? (
                <p className="text-muted-foreground p-6" data-testid="consents-empty">Nessun consenso registrato finora.</p>
              ) : (
                <>
                {selectedConsents.length > 0 && (
                  <div className="flex items-center justify-between m-4 bg-secondary/10 border border-secondary/30 rounded-xl px-6 py-3" data-testid="consents-bulk-bar">
                    <span className="text-sm font-medium text-foreground" data-testid="selected-consents-count">
                      {selectedConsents.length} consensi selezionati
                    </span>
                    <Button variant="destructive" size="sm" className="rounded-full" onClick={deleteSelectedConsents} data-testid="delete-selected-consents-button">
                      <Trash2 className="h-4 w-4 mr-2" />
                      Elimina selezionati
                    </Button>
                  </div>
                )}
                <table className="w-full text-left" data-testid="consents-table">
                  <thead className="bg-muted text-sm text-muted-foreground">
                    <tr>
                      <th className="px-6 py-4 w-10">
                        <input
                          type="checkbox"
                          checked={allConsentsSelected}
                          onChange={toggleAllConsents}
                          className="h-5 w-5 cursor-pointer accent-[#1A2942]"
                          data-testid="select-all-consents-checkbox"
                          aria-label="Seleziona tutti i consensi"
                        />
                      </th>
                      <th className="px-6 py-4 font-medium">Email</th>
                      <th className="px-6 py-4 font-medium">Versione</th>
                      <th className="px-6 py-4 font-medium">Data e ora</th>
                      <th className="px-6 py-4 font-medium hidden md:table-cell">IP</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {consents.map((c, i) => (
                      <tr key={consentKey(c)} className="hover:bg-muted/50 transition-colors duration-200" data-testid={`consent-row-${c.user_id}`}>
                        <td className="px-6 py-4">
                          <input
                            type="checkbox"
                            checked={selectedConsents.includes(consentKey(c))}
                            onChange={() => toggleConsent(c)}
                            className="h-5 w-5 cursor-pointer accent-[#1A2942]"
                            data-testid={`select-consent-${i}`}
                            aria-label={`Seleziona consenso ${c.email}`}
                          />
                        </td>
                        <td className="px-6 py-4 text-sm font-medium text-foreground">{c.email}</td>
                        <td className="px-6 py-4 text-sm">{c.version}</td>
                        <td className="px-6 py-4 text-sm">{new Date(c.created_at).toLocaleString("it-IT")}</td>
                        <td className="px-6 py-4 text-sm text-muted-foreground hidden md:table-cell">{c.ip || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="pazienti">
            <div className="bg-card border border-border rounded-2xl overflow-hidden" data-testid="patients-panel">
              <div className="p-6 border-b border-border">
                <h2 className="font-serif text-xl text-primary">Account pazienti</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Eliminando un paziente vengono rimossi account, dossier e referti caricati. I file già copiati sul tuo Drive, i pagamenti e i consensi vengono conservati.
                </p>
              </div>
              {patients.length === 0 ? (
                <p className="text-muted-foreground p-6" data-testid="patients-empty">Nessun paziente registrato.</p>
              ) : (
                <table className="w-full text-left" data-testid="patients-table">
                  <thead className="bg-muted text-sm text-muted-foreground">
                    <tr>
                      <th className="px-6 py-4 font-medium">Paziente</th>
                      <th className="px-6 py-4 font-medium hidden sm:table-cell">Dossier</th>
                      <th className="px-6 py-4 font-medium hidden md:table-cell">Registrato il</th>
                      <th className="px-6 py-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {patients.map((p) => (
                      <tr key={p.user_id} className="hover:bg-muted/50 transition-colors duration-200" data-testid={`patient-row-${p.user_id}`}>
                        <td className="px-6 py-4">
                          <p className="font-medium text-foreground">{p.name || "—"}</p>
                          <p className="text-xs text-muted-foreground">{p.email}</p>
                        </td>
                        <td className="px-6 py-4 hidden sm:table-cell text-sm">{p.dossier_count}</td>
                        <td className="px-6 py-4 hidden md:table-cell text-sm text-muted-foreground">
                          {p.created_at ? new Date(p.created_at).toLocaleDateString("it-IT") : "—"}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => deletePatient(p)}
                            data-testid={`delete-patient-${p.user_id}`}
                            aria-label={`Elimina paziente ${p.email}`}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </TabsContent>

          <TabsContent value="email">
            <div className="bg-card border border-border rounded-2xl overflow-hidden" data-testid="emails-panel">
              <div className="flex flex-wrap items-center justify-between gap-4 p-6 border-b border-border">
                <div>
                  <h2 className="font-serif text-xl text-primary flex items-center gap-2">
                    <Mail className="h-5 w-5 text-secondary" />
                    Registro email inviate
                  </h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    Traccia di tutte le email automatiche (dossier pronto, conferme e promemoria consulto, reset password): destinatario, data e esito dell'invio.
                  </p>
                </div>
                <a href={`${API}/admin/emails/export`}>
                  <Button variant="outline" className="rounded-full" data-testid="export-emails-button">
                    <Download className="h-4 w-4 mr-2" />
                    Esporta CSV
                  </Button>
                </a>
              </div>
              {emails.length === 0 ? (
                <p className="text-muted-foreground p-6" data-testid="emails-empty">Nessuna email registrata finora.</p>
              ) : (
                <table className="w-full text-left" data-testid="emails-table">
                  <thead className="bg-muted text-sm text-muted-foreground">
                    <tr>
                      <th className="px-6 py-4 font-medium">Data e ora</th>
                      <th className="px-6 py-4 font-medium">Destinatario</th>
                      <th className="px-6 py-4 font-medium hidden md:table-cell">Tipo</th>
                      <th className="px-6 py-4 font-medium">Esito</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {emails.map((em, i) => (
                      <tr key={`${em.created_at}-${i}`} data-testid={`email-row-${i}`}>
                        <td className="px-6 py-4 text-sm">{new Date(em.created_at).toLocaleString("it-IT")}</td>
                        <td className="px-6 py-4 text-sm font-medium text-foreground">{em.to}</td>
                        <td className="px-6 py-4 text-sm hidden md:table-cell">{EMAIL_TEMPLATE_LABELS[em.template] || em.template}</td>
                        <td className="px-6 py-4">
                          <Badge className={em.status === "inviata" ? "bg-success/10 text-success border-0" : "bg-destructive/10 text-destructive border-0"} data-testid={`email-status-${i}`}>
                            {em.status === "inviata" ? "Inviata" : "Non recapitata"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
};

export default DoctorDashboard;
