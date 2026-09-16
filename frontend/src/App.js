import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import Landing from "@/pages/Landing";
import AuthPage from "@/pages/AuthPage";
import AuthCallback from "@/pages/AuthCallback";
import PatientDashboard from "@/pages/PatientDashboard";
import DossierPage from "@/pages/DossierPage";
import DoctorDashboard from "@/pages/DoctorDashboard";
import DoctorDossierPage from "@/pages/DoctorDossierPage";
import { PaymentCancel, PaymentSuccess } from "@/pages/PaymentResult";
import Privacy from "@/pages/Privacy";
import ConsentPage from "@/pages/ConsentPage";
import ResetPassword from "@/pages/ResetPassword";
import { Loader2 } from "lucide-react";

const LoadingScreen = () => (
  <div className="min-h-screen flex items-center justify-center bg-background" data-testid="loading-screen">
    <Loader2 className="h-8 w-8 animate-spin text-primary" />
  </div>
);

const Protected = ({ children, admin = false }) => {
  const { user } = useAuth();
  if (user === null) return <LoadingScreen />;
  if (!user) return <Navigate to="/auth" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  if (user.role !== "admin" && !user.consents_version) return <Navigate to="/consenso" replace />;
  return children;
};

const ConsentRoute = () => {
  const { user } = useAuth();
  if (user === null) return <LoadingScreen />;
  if (!user) return <Navigate to="/auth" replace />;
  if (user.consents_version || user.role === "admin") {
    return <Navigate to={user.role === "admin" ? "/admin" : "/dashboard"} replace />;
  }
  return <ConsentPage />;
};

const DashboardRouter = () => {
  const { user } = useAuth();
  if (user?.role === "admin") return <Navigate to="/admin" replace />;
  return <PatientDashboard />;
};

function AppRouter() {
  const location = useLocation();
  if (
    location.hash?.includes("session_id=") ||
    location.search?.includes("session_id=") ||
    location.pathname === "/auth/callback"
  ) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/consenso" element={<ConsentRoute />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/dashboard" element={<Protected><DashboardRouter /></Protected>} />
      <Route path="/dossier/:id" element={<Protected><DossierPage /></Protected>} />
      <Route path="/admin" element={<Protected admin><DoctorDashboard /></Protected>} />
      <Route path="/admin/dossier/:id" element={<Protected admin><DoctorDossierPage /></Protected>} />
      <Route path="/payment/success" element={<Protected><PaymentSuccess /></Protected>} />
      <Route path="/payment/cancel" element={<Protected><PaymentCancel /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
        <Toaster position="top-center" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
