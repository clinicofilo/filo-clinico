import axios from "axios";

const backendUrl = (process.env.REACT_APP_BACKEND_URL || "").trim().replace(/\/+$/, "");
export const API = backendUrl ? (backendUrl.endsWith("/api") ? backendUrl : `${backendUrl}/api`) : "/api";

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

export function formatApiError(detail) {
  if (detail == null) return "Qualcosa è andato storto. Riprova.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export const STATUS_LABELS = {
  bozza: "In attesa di pagamento",
  pagato: "Pagato — In lavorazione",
  in_lavorazione: "Pagato — In lavorazione",
  completato: "Pronto",
};

export const PATIENT_STATUS_LABELS = {
  bozza: "In attesa di pagamento",
  pagato: "Pagato — In lavorazione",
  in_lavorazione: "Pagato — In lavorazione",
  completato: "Pronto",
};

export const STATUS_COLORS = {
  bozza: "bg-accent text-accent-foreground",
  pagato: "bg-secondary/10 text-secondary",
  in_lavorazione: "bg-primary/10 text-primary",
  completato: "bg-success/10 text-success",
};
