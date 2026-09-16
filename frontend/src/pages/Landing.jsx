import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import {
  ArrowRight, ClipboardList, FileText, UploadCloud, Video, Check,
  UserRound, HeartHandshake, FolderOpen, FileDown,
} from "lucide-react";

const HERO_IMG = "/images/hero.png";
// TODO: sostituire con la foto reale del Dott. Spitaleri quando fornita
const DOCTOR_IMG = "/images/doctor-placeholder.png";
const RECORDS_IMG = "https://images.unsplash.com/photo-1758691461990-03b49d969495?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzR8MHwxfHNlYXJjaHwzfHxkb2N0b3IlMjBjb25zdWx0aW5nJTIwcGF0aWVudHxlbnwwfHx8fDE3ODY3OTEwOTZ8MA&ixlib=rb-4.1.0&q=85";

const fadeUp = {
  initial: { opacity: 0, y: 10 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.4 },
};

const Landing = () => {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-background" data-testid="landing-page">
      <header className="sticky top-0 z-40 bg-background border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-primary" data-testid="landing-logo">
            <FileText className="h-6 w-6" />
            <span className="font-serif text-xl font-semibold">FiloClinico</span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-foreground/80">
            <a href="#come-funziona" className="hover:text-primary transition-colors duration-200" data-testid="nav-how-link">Come funziona</a>
            <a href="#chi-sono" className="hover:text-primary transition-colors duration-200" data-testid="nav-about-link">Chi sono</a>
            <a href="#prezzi" className="hover:text-primary transition-colors duration-200" data-testid="nav-pricing-link">Prezzi</a>
          </nav>
          <Link to={user ? "/dashboard" : "/auth"}>
            <Button className="rounded-full" data-testid="nav-login-btn">
              {user ? "La mia area" : "Accedi"}
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </Link>
        </div>
      </header>

      <section className="noise-overlay py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6 grid md:grid-cols-2 gap-16 items-center">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl tracking-tight text-primary leading-[1.1] mb-8" data-testid="hero-title">
              La tua storia clinica, finalmente in ordine.
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed mb-10 max-w-xl" data-testid="hero-subtitle">
              Hai una storia clinica complessa e referti sparsi tra ospedali, specialisti e cassetti?
              Fatichi a ricordare date, esami e terapie ogni volta che te li chiedono? Carica le foto
              dei tuoi documenti: un medico specializzando in Medicina Interna ricostruisce la tua intera
              storia clinica in un unico dossier chiaro e ordinato, pronto da portare a ogni specialista.
              E se vuoi, ne parliamo insieme in videochiamata.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link to={user ? "/dashboard" : "/auth"}>
                <Button size="lg" className="rounded-full text-base px-8 transition-transform duration-200 hover:-translate-y-0.5" data-testid="hero-cta-btn">
                  Inizia ora
                  <ArrowRight className="h-5 w-5 ml-2" />
                </Button>
              </Link>
              <a href="#come-funziona">
                <Button size="lg" variant="outline" className="rounded-full text-base px-8" data-testid="hero-how-btn">
                  Come funziona
                </Button>
              </a>
            </div>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.15 }}>
            <img
              src={HERO_IMG}
              alt="Medico in consulto con un paziente"
              className="rounded-3xl w-full object-cover max-h-[80vh] md:max-h-[560px]"
              data-testid="hero-image"
            />
          </motion.div>
        </div>
      </section>

      <section id="come-funziona" className="py-24 bg-muted/60">
        <div className="max-w-7xl mx-auto px-6">
          <motion.div {...fadeUp}>
            <p className="uppercase text-sm tracking-[0.15em] text-secondary font-semibold mb-4">Come funziona</p>
            <h2 className="text-3xl sm:text-4xl text-primary mb-16" data-testid="how-title">Tre passaggi semplici</h2>
          </motion.div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: UserRound,
                title: "1. Registrati e racconta",
                text: "Crea il tuo account in un minuto — per te o per un tuo familiare — e descrivi la situazione clinica compilando un breve questionario.",
                testid: "step-register",
              },
              {
                icon: UploadCloud,
                title: "2. Carica i referti",
                text: "Fotografa o scansiona esami, lettere di dimissione e referti: caricali tutti nel tuo dossier, in totale sicurezza.",
                testid: "step-upload",
              },
              {
                icon: FileDown,
                title: "3. Ricevi il tuo dossier",
                text: "Rivedo ogni documento e tiro le fila della tua storia clinica in un unico documento facilmente leggibile ed interpretabile da tutti i professionisti del settore. Su richiesta, ne discutiamo in videochiamata.",
                testid: "step-receive",
              },
            ].map((s, i) => (
              <motion.div
                key={s.title}
                {...fadeUp}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                className="bg-card border border-border rounded-2xl p-8 hover:shadow-sm hover:-translate-y-0.5 transition-all duration-200"
                data-testid={s.testid}
              >
                <s.icon className="h-10 w-10 text-secondary mb-6" />
                <h3 className="text-xl text-primary mb-4">{s.title}</h3>
                <p className="text-muted-foreground leading-relaxed">{s.text}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-24 md:py-32 noise-overlay">
        <div className="max-w-7xl mx-auto px-6 grid md:grid-cols-2 gap-16 items-center">
          <motion.div {...fadeUp} className="order-2 md:order-1">
            <p className="uppercase text-sm tracking-[0.15em] text-secondary font-semibold mb-4">Un esempio concreto</p>
            <h2 className="text-3xl sm:text-4xl text-primary mb-6" data-testid="example-title">Ecco come sarà il tuo dossier</h2>
            <p className="text-lg text-muted-foreground leading-relaxed mb-6">
              Questo è un esempio reale di ciò che riceverai: anamnesi ricostruita, esami ed eventi
              clinici in ordine cronologico, terapie in corso e valutazione conclusiva di Medicina
              Interna. Un unico documento PDF, pronto da portare a ogni specialista.
            </p>
            <ul className="space-y-3 text-muted-foreground mb-10">
              {[
                "Storia clinica completa, riordinata e leggibile in pochi minuti",
                "Consegnato in PDF entro 72 ore dalla richiesta",
                "Pensato per essere capito da ogni professionista sanitario",
              ].map((f) => (
                <li key={f} className="flex items-start gap-3">
                  <Check className="h-5 w-5 text-success shrink-0 mt-0.5" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <a href="/docs/Esempio_Dossier_Clinico.pdf" target="_blank" rel="noreferrer">
              <Button size="lg" className="rounded-full px-8" data-testid="example-dossier-button">
                <FileDown className="h-5 w-5 mr-2" />
                Apri l'esempio (PDF)
              </Button>
            </a>
          </motion.div>
          <motion.div {...fadeUp} transition={{ duration: 0.4, delay: 0.1 }} className="order-1 md:order-2">
            <a href="/docs/Esempio_Dossier_Clinico.pdf" target="_blank" rel="noreferrer" data-testid="example-dossier-preview-link">
              <img
                src="/images/esempio_dossier.png"
                alt="Anteprima di un dossier clinico di esempio"
                className="rounded-3xl w-full border border-border shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-200"
                data-testid="example-dossier-image"
              />
            </a>
          </motion.div>
        </div>
      </section>

      <section id="chi-sono" className="py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6 grid md:grid-cols-5 gap-16 items-center">
          <motion.div {...fadeUp} className="md:col-span-2">
            <img
              src={DOCTOR_IMG}
              alt="Il medico del progetto"
              className="rounded-3xl w-full object-cover max-h-[80vh] md:max-h-none"
              data-testid="about-doctor-image"
            />
          </motion.div>
          <motion.div {...fadeUp} className="md:col-span-3">
            <p className="uppercase text-sm tracking-[0.15em] text-secondary font-semibold mb-4">Chi sono</p>
            <h2 className="text-3xl sm:text-4xl text-primary mb-8" data-testid="about-title">
              Un medico, dalla parte dei pazienti — e dei colleghi.
            </h2>
            <blockquote className="font-serif italic text-xl text-foreground/90 border-l-4 border-secondary pl-6 mb-8" data-testid="about-quote">
              "Ogni paziente arriva in ambulatorio con una borsa piena di referti sparsi.
              Il mio lavoro è trasformarla in una storia chiara."
            </blockquote>
            <div className="space-y-6 text-lg text-muted-foreground leading-relaxed">
              <p data-testid="about-bio-1">
                Sono il <strong className="text-foreground">Dott. Pietro Spitaleri Timpone</strong>, medico
                specializzando all'ultimo anno di <strong className="text-foreground">Medicina Interna</strong>.
                L'idea di questo servizio nasce dalla mia curiosità personale e da ciò che vedo ogni
                giorno: pazienti con storie cliniche complesse e documenti disordinati, che rischiano
                di non essere compresi a pieno.
              </p>
              <p data-testid="about-bio-2">
                Riordinare la tua storia clinica non aiuta solo te: il dossier che riceverai è pensato
                per <strong className="text-foreground">avvantaggiare i colleghi</strong> a cui lo porterai.
                Un medico che legge un quadro completo e ordinato può visitarti meglio, più in fretta
                e con meno esami ripetuti.
              </p>
            </div>
            <a href="/docs/CV_Pietro_Spitaleri_Timpone.pdf" target="_blank" rel="noreferrer">
              <Button variant="outline" className="rounded-full mt-8 px-8" data-testid="cv-download-button">
                <FileDown className="h-4 w-4 mr-2" />
                Visualizza e scarica il mio CV
              </Button>
            </a>
          </motion.div>
        </div>
      </section>

      <section id="prezzi" className="py-24 bg-muted/60 noise-overlay">
        <div className="max-w-7xl mx-auto px-6">
          <motion.div {...fadeUp}>
            <p className="uppercase text-sm tracking-[0.15em] text-secondary font-semibold mb-4">Prezzi</p>
            <h2 className="text-3xl sm:text-4xl text-primary mb-4" data-testid="pricing-title">Chiari e senza sorprese</h2>
            <p className="text-lg text-muted-foreground mb-16 max-w-2xl">
              Paghi solo quello che ti serve. Il consulto video è sempre facoltativo.
            </p>
          </motion.div>
          <div className="grid md:grid-cols-2 gap-8 max-w-4xl">
            <motion.div
              {...fadeUp}
              className="bg-card border border-border rounded-2xl p-10 hover:shadow-sm hover:-translate-y-0.5 transition-all duration-200"
              data-testid="pricing-review-card"
            >
              <ClipboardList className="h-10 w-10 text-primary mb-6" />
              <h3 className="text-2xl text-primary mb-2">Revisione referti + dossier</h3>
              <p className="font-serif text-5xl text-primary my-6" data-testid="pricing-review-price">50 € <span className="text-xl text-muted-foreground">+ IVA</span></p>
              <ul className="space-y-3 text-muted-foreground mb-8">
                {[
                  "Analisi completa di tutti i referti caricati",
                  "Riassunto scritto della tua storia clinica",
                  "Consegna entro 72 ore dalla richiesta",
                  "Dossier ordinato da portare ai tuoi specialisti",
                  "Scaricabile in PDF dalla tua area riservata",
                ].map((f) => (
                  <li key={f} className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-success shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link to={user ? "/dashboard" : "/auth"}>
                <Button className="w-full rounded-full" data-testid="pricing-review-cta">Richiedi la revisione</Button>
              </Link>
            </motion.div>
            <motion.div
              {...fadeUp}
              transition={{ duration: 0.4, delay: 0.1 }}
              className="bg-primary text-primary-foreground rounded-2xl p-10 hover:shadow-sm hover:-translate-y-0.5 transition-all duration-200"
              data-testid="pricing-video-card"
            >
              <Video className="h-10 w-10 text-secondary mb-6" />
              <h3 className="text-2xl mb-2">Consulto video online</h3>
              <p className="font-serif text-5xl my-6" data-testid="pricing-video-price">+ 50 € <span className="text-xl opacity-70">+ IVA</span></p>
              <ul className="space-y-3 text-primary-foreground/80 mb-8">
                {[
                  "Videochiamata di 30 minuti su Google Meet",
                  "Commentiamo insieme il dossier",
                  "Domande e chiarimenti a voce",
                  "Prenoti il giorno e l'ora che preferisci",
                ].map((f) => (
                  <li key={f} className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-secondary shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <p className="text-sm text-primary-foreground/70 mb-6">
                Facoltativo: puoi aggiungerlo dopo aver richiesto la revisione.
              </p>
              <Link to={user ? "/dashboard" : "/auth"}>
                <Button variant="secondary" className="w-full rounded-full" data-testid="pricing-video-cta">
                  Aggiungi il consulto video
                </Button>
              </Link>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="py-24">
        <div className="max-w-7xl mx-auto px-6 grid md:grid-cols-2 gap-16 items-center">
          <motion.div {...fadeUp}>
            <HeartHandshake className="h-10 w-10 text-secondary mb-6" />
            <h2 className="text-3xl sm:text-4xl text-primary mb-6">Per te o per chi assisti</h2>
            <p className="text-lg text-muted-foreground leading-relaxed mb-6">
              Puoi creare un dossier anche per un genitore o un familiare che assisti: basta indicarlo
              in fase di registrazione del dossier. Tutti i documenti restano nella tua area riservata
              e i referti vengono archiviati in una cartella dedicata.
            </p>
            <div className="flex items-center gap-3 text-foreground font-medium">
              <FolderOpen className="h-5 w-5 text-secondary" />
              <span>I tuoi documenti sono trattati con riservatezza e non condivisi con terzi.</span>
            </div>
          </motion.div>
          <motion.div {...fadeUp} transition={{ duration: 0.4, delay: 0.1 }}>
            <img
              src={RECORDS_IMG}
              alt="Medico che riordina una cartella clinica"
              className="rounded-3xl w-full object-cover max-h-[80vh] md:max-h-[440px]"
              data-testid="records-image"
            />
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-border py-12">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row justify-between gap-6 mb-8">
            <div className="flex items-center gap-2 text-primary">
              <FileText className="h-5 w-5" />
              <span className="font-serif text-lg font-semibold">FiloClinico</span>
            </div>
            <Link to={user ? "/dashboard" : "/auth"}>
              <Button className="rounded-full" data-testid="footer-cta-btn">Inizia ora</Button>
            </Link>
          </div>
          <p className="text-sm text-muted-foreground max-w-3xl leading-relaxed" data-testid="footer-disclaimer">
            Il riassunto della storia clinica è un supporto organizzativo e divulgativo: non sostituisce
            la visita medica, la diagnosi o la prescrizione, e non modifica il rapporto con il tuo medico
            curante. In caso di urgenza rivolgiti al 112 o al pronto soccorso.
          </p>
          <div className="mt-6">
            <Link to="/privacy" className="text-sm text-muted-foreground hover:text-primary transition-colors duration-200" data-testid="footer-privacy-link">
              Informativa privacy
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Landing;
