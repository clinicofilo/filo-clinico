import { Link } from "react-router-dom";
import { FileText } from "lucide-react";

const Section = ({ title, testid, children }) => (
  <section className="mb-10" data-testid={testid}>
    <h2 className="font-serif text-2xl text-primary mb-4">{title}</h2>
    <div className="text-foreground/80 leading-relaxed space-y-3">{children}</div>
  </section>
);

const Privacy = () => (
  <div className="min-h-screen bg-background" data-testid="privacy-page">
    <header className="border-b border-border bg-background">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <Link to="/" className="flex items-center gap-2 text-primary w-fit" data-testid="privacy-logo-link">
          <FileText className="h-6 w-6" />
          <span className="font-serif text-xl font-semibold">FiloClinico</span>
        </Link>
      </div>
    </header>

    <main className="max-w-3xl mx-auto px-6 py-16">
      <h1 className="text-4xl text-primary mb-4" data-testid="privacy-title">Informativa sulla privacy</h1>
      <p className="text-muted-foreground mb-12">
        Informativa resa ai sensi degli artt. 13 e 14 del Regolamento (UE) 2016/679 ("GDPR").
        Ultimo aggiornamento: settembre 2026.
      </p>

      <Section title="1. Titolare del trattamento" testid="privacy-titolare">
        <p>
          Il titolare del trattamento è il <strong>Dott. Pietro Spitaleri Timpone</strong>,
          medico specializzando in Medicina Interna, contattabile all'indirizzo email{" "}
          <a href="mailto:dott.spitaleripietro@gmail.com" className="text-secondary underline">dott.spitaleripietro@gmail.com</a>.
        </p>
      </Section>

      <Section title="2. Dati trattati" testid="privacy-dati">
        <ul className="list-disc pl-6 space-y-2">
          <li><strong>Dati anagrafici e di contatto:</strong> nome, cognome, indirizzo email.</li>
          <li><strong>Dati di autenticazione:</strong> credenziali dell'account (conservate in forma cifrata) o identificativi del login Google.</li>
          <li><strong>Dati relativi alla salute:</strong> referti, esami, lettere di dimissione, immagini, PDF e ogni altra documentazione clinica caricata volontariamente, incluse le risposte al questionario anamnestico.</li>
          <li><strong>Dati di pagamento:</strong> gestiti direttamente da Stripe e PayPal; il Titolare non memorizza i dati della carta o del conto.</li>
          <li><strong>Dati tecnici:</strong> log di accesso, indirizzo IP e informazioni sul dispositivo, raccolti per sicurezza e prova del consenso.</li>
        </ul>
      </Section>

      <Section title="3. Finalità e base giuridica" testid="privacy-finalita">
        <ul className="list-disc pl-6 space-y-2">
          <li><strong>Registrazione ed erogazione del servizio</strong> (creazione account, gestione dossier, prenotazione consulto): esecuzione di un contratto, art. 6, par. 1, lett. b GDPR.</li>
          <li><strong>Trattamento dei dati sanitari</strong> per la redazione del riassunto della storia clinica: <strong>consenso esplicito</strong>, art. 9, par. 2, lett. a GDPR, raccolto in fase di registrazione e revocabile in qualsiasi momento.</li>
          <li><strong>Adempimenti fiscali e contabili</strong> connessi ai pagamenti: obbligo legale, art. 6, par. 1, lett. c GDPR.</li>
        </ul>
        <p>Il conferimento dei dati sanitari è facoltativo, ma in sua assenza il servizio di riassunto non può essere erogato.</p>
      </Section>

      <Section title="4. Modalità del trattamento e sicurezza" testid="privacy-sicurezza">
        <p>
          I dati sono trattati con strumenti informatici, nel rispetto delle misure tecniche e
          organizzative adeguate (art. 32 GDPR): connessioni cifrate (HTTPS), autenticazione
          protetta, archiviazione su storage cloud sicuro con accesso riservato al Titolare.
          I referti caricati sono inoltre archiviati in una cartella dedicata sul Google Drive
          del Titolare, accessibile esclusivamente a quest'ultimo.
        </p>
      </Section>

      <Section title="5. Destinatari e trasferimenti" testid="privacy-destinatari">
        <p>I dati non sono venduti né comunicati a terzi per finalità di marketing. Possono essere trattati, in qualità di responsabili o autonomi titolari, da fornitori tecnici:</p>
        <ul className="list-disc pl-6 space-y-2">
          <li><strong>Google</strong> (Drive, Moduli, login OAuth) — archiviazione documenti e questionario;</li>
          <li><strong>Stripe</strong> e <strong>PayPal</strong> — elaborazione dei pagamenti;</li>
          <li><strong>Fornitori di hosting e infrastruttura cloud</strong> della piattaforma.</li>
        </ul>
        <p>
          Alcuni di questi fornitori possono comportare il trasferimento di dati al di fuori
          dell'UE: tale trasferimento avviene nel rispetto del Capo V GDPR (es. Clausole
          Contrattuali Standard o EU-US Data Privacy Framework).
        </p>
      </Section>

      <Section title="6. Conservazione" testid="privacy-conservazione">
        <p>
          I dati dell'account e i documenti caricati sono conservati per la durata del rapporto
          e comunque fino a richiesta di cancellazione da parte dell'interessato. I dati fiscali
          connessi ai pagamenti sono conservati per 10 anni come previsto dalla normativa
          civilistica e fiscale. I consensi prestati sono registrati (data, ora, indirizzo IP)
          come prova dell'adempimento.
        </p>
      </Section>

      <Section title="7. Diritti dell'interessato" testid="privacy-diritti">
        <p>Puoi esercitare in qualsiasi momento i diritti previsti dagli artt. 15-22 GDPR:</p>
        <ul className="list-disc pl-6 space-y-2">
          <li>accesso, rettifica e cancellazione dei dati;</li>
          <li>limitazione e opposizione al trattamento;</li>
          <li>portabilità dei dati;</li>
          <li><strong>revoca del consenso</strong>, senza pregiudicare la liceità del trattamento basato sul consenso prestato prima della revoca.</li>
        </ul>
        <p>
          Per esercitare i diritti scrivi a{" "}
          <a href="mailto:dott.spitaleripietro@gmail.com" className="text-secondary underline">dott.spitaleripietro@gmail.com</a>.
          Hai inoltre diritto di proporre reclamo al <strong>Garante per la protezione dei dati
          personali</strong> (<a href="https://www.garanteprivacy.it" target="_blank" rel="noreferrer" className="text-secondary underline">www.garanteprivacy.it</a>).
        </p>
      </Section>

      <Section title="8. Natura del servizio" testid="privacy-natura">
        <p>
          Il riassunto della storia clinica è un servizio di riorganizzazione e divulgazione
          documentale: non costituisce visita medica, diagnosi o prescrizione e non sostituisce
          il rapporto con il medico curante. In caso di urgenza rivolgiti al 112 o al pronto soccorso.
        </p>
      </Section>
    </main>
  </div>
);

export default Privacy;
