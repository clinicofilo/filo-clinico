# PRD — FiloClinico

## Problem statement originale
Medico specializzando all'ultimo anno di Medicina Interna (Dott. Pietro Spitaleri) vuole un sito intuitivo dove pazienti (o familiari) si registrano, caricano foto/immagini dei referti, e lui redige un riassunto della storia clinica (visita di medicina interna) + eventuale consulto video. Landing con presentazione progetto e del medico. Prezzi: 50€ revisione referti + 50€ opzionale consulto video.

## Scelte utente
- Auth: email/password (JWT) + Google login (Emergent-managed)
- Pagamenti: Stripe (sandbox claimable, EUR, tax mode "full" — Stripe gestisce anche IVA/compliance)
- Storage referti: Google Drive del medico (cartella per paziente) — IN ATTESA credenziali OAuth Google del medico
- Consulto: prenotazione slot + link Google Meet/Zoom esterno
- Design: scelto dal designer (Warm Clinical: Playfair Display + Manrope, navy #1A2942 / terracotta #C86444 / crema #F9F8F6)

## Architettura
- Backend: FastAPI (server.py), MongoDB (motor), Object Storage Emergent per i file, Stripe SDK, Google Drive API (best-effort)
- Frontend: React + Tailwind + Shadcn, react-router, axios withCredentials
- Utenti: custom user_id UUID, ruoli patient/admin. Admin seed: spitaleri.pietro@gmail.com

## Personas
- Paziente (anche anziano/poco tech): registrazione semplice, upload multiplo, pagamento, download dossier
- Familiare/caregiver: crea dossier per un assistito
- Medico (admin): dashboard dossier, scrittura riassunto, upload PDF, gestione slot, collegamento Drive

## Implementato (2026-09-07)- Landing page italiana (hero illustrata, come funziona, chi sono, prezzi 50€/50€, footer disclaimer)
- Auth completa: register/login JWT + Google OAuth Emergent, cookie httpOnly, refresh token, brute-force protection
- Dossier: creazione, upload multiplo referti (img/pdf, max 15MB) su Object Storage, delete, serving autenticato
- Stripe: catalogo (revisione_referti, consulto_video — 50€), checkout, webhook /api/stripe/webhook, polling status, fulfil automatico
- PayPal (2026-09-08): credenziali LIVE, pulsanti PayPal accanto a Stripe (revisione + consulto), endpoint /api/paypal/orders + /capture con verifica importo e fulfil condiviso
- Slot consulto video: CRUD admin, prenotazione pagata paziente, data/link Meet salvati sul dossier
- Dashboard medico: tabella dossier, editor riassunto + upload PDF, gestione slot, pannello Drive
- Dashboard paziente: lista dossier, stato, upload, pagamento, prenotazione, download riassunto
- Test: 26/26 backend passati (pytest), flussi frontend chiave verificati

- GDPR/Garante (2026-09-10): 3 consensi obbligatori in registrazione (privacy art. 6, dati sanitari art. 9.2.a, dichiarazione maggiore età/autorizzazione familiare), prova consenso in DB (versione, timestamp, IP, user-agent), pagina /privacy (informativa art. 13-14 completa), pagina /consenso per utenti Google/esistenti senza consensi
- Integrazioni dossier 25€ (2026-09-10): Stripe lookup integrazione_dossier + PayPal 25€, due tipi (nuovi/dimenticati), integration_pending riapre upload, auto-clear al caricamento nuovo PDF, banner informativo sotto upload, badge "Integrazione richiesta" per il medico
- Registro consensi medico (2026-09-10): tab "Consensi" in /admin con tabella (email, versione, data/ora, IP) + export CSV (/api/admin/consents/export)
- Creazione dossier semplificata (2026-09-10): rimosso campo note, hint al questionario facoltativo
- UX pagamento/consulto (2026-09-10): sezione prenotazione slot video sempre visibile sotto il pagamento nella pagina dossier; nota che il link Meet arriva via email di registrazione; hero riscritta con domande engaging; CV scaricabile in "Chi sono" (/docs/CV_Pietro_Spitaleri_Timpone.pdf, pubblico per scelta del titolare)
- Stati ridotti a due ovunque (2026-09-10): "Pagato — In lavorazione" e "Pronto" (medico e paziente); editor medico solo PDF (rimossa textarea riassunto); dossier consegnato solo come PDF; pulsante slot arancione "Prenota e paga — 50 €" stile secondary + PayPal
- Gestione dossier medico (2026-09-10): DELETE /api/dossiers/{id} admin-only, pulsante elimina con conferma nella tabella, modifica titolo/paziente nel dettaglio; pulizia di tutti i dossier di test (30 eliminati)
- Mobile fix (2026-09-14): meta viewport con zoom/pan esplicitamente abilitati (user-scalable=yes, maximum-scale=5, viewport-fit=cover) per modalità "sito desktop" da cellulare; index.html: lang=it, title/description FiloClinico
- Switch account medico (2026-09-14): admin principale ora dott.spitaleripietro@gmail.com (Google Workspace); vecchio account spitaleri.pietro@gmail.com retrocesso a patient. Drive da ricollegare dal nuovo account (credenziali OAuth vecchie eliminate); il nuovo account va aggiunto come utente di test nella Google Auth Platform. PayPal invariato (credenziali API indipendenti dall'account sito)
- PRODUZIONE ONLINE (2026-09-15): URL definitivo https://clinical-summary-3.emergent.host — FRONTEND_URL/CORS_ORIGINS/GOOGLE_DRIVE_REDIRECT_URI aggiornati (CORS include anche preview). DA FARE: aggiungere redirect URI prod in Google Cloud Console per Drive
- DOMINIO ATTIVO (2026-09-15): https://filoclinico.org è il dominio definitivo. FRONTEND_URL/GOOGLE_DRIVE_REDIRECT_URI → filoclinico.org; CORS_ORIGINS include dominio + prod + preview; webhook Stripe spostato su https://filoclinico.org/api/stripe/webhook (nuovo whsec in .env, vecchio emergent.host eliminato). DA FARE DOPO MODIFICHE .env: Republish per propagare in produzione. DA FARE UTENTE: aggiungere https://filoclinico.org/api/drive/callback ai redirect URI in Google Cloud Console
- STRIPE LIVE (2026-09-15): chiavi live attive IN PRODUZIONE (verificato: sessioni cs_live_ su https://clinical-summary-3.emergent.host), 3 prodotti live (50/50/25€), webhook live registrato sul dominio prod. Sandbox di test non più in uso. NOTA: i secrets di produzione si propagano solo via Republish (build dal workspace .env)
- Questionario abbinato al paziente (2026-09-15): link Google Moduli precompilato con email paziente (entry.1846449771); pulsante "Risposte questionario" nel dettaglio dossier medico → /edit#responses. Modulo aggiornato 2026-09-15 (nuovo form ID 1FAIpQLScvWLwY2iF58To9LSwj9UN6bmSf8Jb3tNnSV2j0SmYvUgNiMQ, stesso entry email)
- Multiselezione dossier (2026-09-15): checkbox per riga + seleziona-tutti + barra "Elimina selezionati" con conferma nella dashboard medico
- Verifica questionario reale (2026-09-15): POST questionnaire-done verifica via Google Forms API (scope forms.responses.readonly aggiunto — serve ricollegare Drive) che esista una risposta con l'email del paziente
- IVA (2026-09-15): tutte le diciture prezzo ora "+ IVA"; PayPal addebita netto+IVA 22% con breakdown (Stripe SMP calcola già l'IVA da solo)
- Recupero password (2026-09-15): forgot/reset via email Resend gestita (token monouso 30 min, rate limit, sempre 200 anti account-enumeration — fix 502→200 su email non recapitabili), email di recupero facoltativa in registrazione, regole password rafforzate (8 char, 6 lettere, numero, speciale). Test: 18/18
- Esempio dossier in landing (2026-09-14): sezione "Ecco come sarà il tuo dossier" tra Come funziona e Chi sono, con anteprima immagine (/images/esempio_dossier.png) e PDF apribile (/docs/Esempio_Dossier_Clinico.pdf, pubblico per scelta del titolare)
- Questionario obbligatorio (2026-09-14): upload referti bloccato (400 backend + UI locked) finché il paziente non conferma la compilazione del questionario Google Moduli (POST /api/dossiers/{id}/questionnaire-done); badge "obbligatorio"
- Code review fixes (2026-09-14): segreti rimossi dai test (env via dotenv), hook deps sistemate (useCallback/useMemo in AuthContext, DossierPage, dashboards), localStorage→sessionStorage per pending_payment, suite test aggiornata al contratto API corrente — 63/63 pytest passati
- Documenti legali (2026-09-10): Registro trattamenti (art. 30) e DPIA (art. 35) generati in .docx compilati — scaricati dall'utente e rimossi dal sito (script di rigenerazione: /tmp/genera_documenti_gdpr.py, NON persistente)
- Questionario Google Moduli (facoltativo) integrato come "Passo 1" nella pagina dossier

- Disaccoppiamento Emergent (2026-09-16): rimosso lock-in proprietario Emergent; storage locale filesystem di default con supporto S3-compatibile; email via Resend diretto / SMTP standard con fallback sicuro mock-dev; Google OAuth standard con callback diretta; rimozione pacchetti e script proprietari (@emergentbase/visual-edits, emergentintegrations, litellm wheel, script tracker emergent); protezione credenziali con esclusione .env in .gitignore e creazione template .env.example.
- Eliminazione account (2026-09-15): paziente self-service da dashboard e medico da tab "Pazienti" in /admin; elimina account + tutti i dossier + file da Object Storage; mantiene pagamenti, consensi, slot e copie su Drive del medico (banner informativo). Conferma adattiva: password per account email/password, digitazione email per account Google (flag `has_password` in /auth/me, login, register, google/session; backend richiede `confirm_email` se non c'è password_hash). Endpoint: POST /api/auth/delete-account, GET/DELETE /api/admin/patients[/{user_id}]. Email automatica di conferma eliminazione via Resend (best-effort). Test: 13/13
- Email automatiche + tracciatura (2026-09-15): email "dossier pronto" all'upload del PDF finale, "conferma consulto" alla prenotazione pagata E all'aggiunta/modifica del link Meet su slot prenotato (PUT /api/slots/{id}, pulsante matita nella tab Disponibilità), "promemoria consulto" 24h prima via cron piattaforma (`.emergent/crons.yml` → POST /api/cron/consult-reminders, secret WEBHOOK_CRON_SECRET, idempotenza run_id). Ogni invio è tracciato in `email_log` e consultabile/esportabile dalla tab "Email" in /admin (GET /api/admin/emails + /export CSV)
- Consensi admin (2026-09-15): multiselezione con checkbox + eliminazione multipla (POST /api/admin/consents/delete, chiave user_id+created_at), export CSV invariato. Test: 103/103
- Riquadro "Il tuo consulto" (2026-09-15): nella pagina dossier del paziente, una volta prenotato il consulto si vedono data/ora in grande, countdown ("Mancano X giorni") e pulsante "Entra in videochiamata" con link Meet; sezione "Elimina account" resa piccola e discreta in fondo alla dashboard paziente. Test: 106/106
- Security audit + fix (2026-09-15): audit completo (verdetto CONDITIONAL PASS, nessuna critica). Fixati 4 MEDIUM: SEC-001 anti formula-injection nei CSV export (`_csv_safe`), SEC-002 messaggio registrazione generico anti-enumeration, SEC-003 revoca token al reset password (token_version in JWT access+refresh, cancellazione sessioni Google), SEC-004 race condition slot consulto (fulfil atomico, conflitto loggato con slot_conflict senza marcare pagato). Extra: verifica currency_code=EUR in capture PayPal. Hardening P3 rimandati: CSRF token, header CSP/X-Frame-Options. Test: /app/backend/tests/test_security_round2.py
- Integrazione 25€ con raccordo anamnestico (2026-09-15): textarea libera (senza questionario) nella sezione integrazione, salvata via POST /api/dossiers/{id}/integration-note (solo dossier completati/in integrazione) prima di Stripe o al click PayPal; il fulfil la archivia in integrations[].note; il medico la vede nel box "Integrazione richiesta" del dettaglio dossier. Test: test_integration_note.py
- Email revoca consensi corretta (2026-09-15): ConsentPage + Privacy ora indicano dott.spitaleripietro@gmail.com
- Modulo Google collegato correttamente (2026-09-15): pulsante "Risposte questionario" ora punta al form edit reale (ID 1O3Cp3GnFtW8cevhgm82jnwbSQRJ9gCclunzJoLReVjE); GOOGLE_FORM_ID backend aggiornato allo stesso ID per la Forms API (prima usava l'ID viewform 1FAIpQL... che causava errore 404). Link viewform paziente invariato. NOTA: nessuna credenziale Drive salvata in preview — la verifica API delle risposte va testata in produzione dopo ricollegamento Drive
- P0: verifica utente reset password/email in produzione + Republish per propagare ultime modifiche
- P0 SICUREZZA: ruotare chiavi esposte in chat (Stripe live secret+webhook, PayPal client secret, Google OAuth client secret) e aggiornare solo via secret manager
- ~~P0: credenziali Google OAuth~~ FATTO (2026-09-10): Drive collegato e verificato end-to-end (test 11/11). Bug PKCE risolto (autogenerate_code_verifier=False). Upload referti → Drive funzionante con drive_file_id confermato
- P1: notifiche email (dossier completato, promemoria consulto); paginazione dossier admin
- P2: reset password via email, fatturazione/ricevute, multilingua

## Prossimi task
1. Ricevere foto medico → sostituire /images/doctor-placeholder.png
2. Medico crea OAuth client su Google Cloud Console → inserire credenziali in backend/.env → collegare Drive da /admin
3. Claim account Stripe via onboarding_url per andare live
