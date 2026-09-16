# Auth Testing Playbook (FiloClinico)

Leggi prima `/app/memory/test_credentials.md` per admin e paziente di test.

## Step 1: Verifica MongoDB
```
mongosh
use test_database
db.users.find({role: "admin"}).pretty()
db.users.findOne({role: "admin"}, {password_hash: 1})
```
Verifica: hash bcrypt inizia con `$2b$`, indici su users.email (unique), users.user_id (unique), login_attempts.identifier, dossiers.dossier_id (unique), slots.slot_id (unique), payment_transactions.session_id (unique).

## Step 2: Test API auth email/password
```
curl -c cookies.txt -X POST <BACKEND_URL>/api/auth/login -H "Content-Type: application/json" -d '{"email":"spitaleri.pietro@gmail.com","password":"DossierMedico2026!"}'
curl -b cookies.txt <BACKEND_URL>/api/auth/me
```
Il login restituisce l'utente e imposta i cookie `access_token` + `refresh_token` (httpOnly). `/me` restituisce lo stesso utente.

## Step 3: Test Google OAuth (Emergent)
Il login Google usa Emergent Auth: bottone "Continua con Google" → redirect a auth.emergentagent.com → ritorno con `#session_id=...` nel fragment → `AuthCallback` chiama `POST /api/auth/google/session` dal backend → cookie `session_token` httpOnly (7 giorni).

Per testare senza browser OAuth, crea una sessione manuale:
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({user_id: userId, email: 'test.user.' + Date.now() + '@example.com', name: 'Test User', role: 'patient', auth_provider: 'google', created_at: new Date().toISOString()});
db.user_sessions.insertOne({user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString(), created_at: new Date().toISOString()});
print('Session token: ' + sessionToken);
"
```
Poi: `curl -X GET "<BACKEND_URL>/api/auth/me" -H "Authorization: Bearer <sessionToken>"`

## Checklist
- Documento utente ha `user_id` custom (non `_id` esposto)
- Le query escludono `_id`
- `/api/auth/me` funziona sia con cookie JWT che con session_token Google
- Callback OAuth rilevato via `useLocation().hash` in App.js (non window.location.hash)
