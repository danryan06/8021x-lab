import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./api/AuthContext";
import { Layout } from "./components/Layout";
import { AuthTestPage } from "./pages/AuthTestPage";
import { CertificatesPage } from "./pages/CertificatesPage";
import { ClientsPage } from "./pages/ClientsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EndpointsPage } from "./pages/EndpointsPage";
import { EventsPage } from "./pages/EventsPage";
import { LoginPage } from "./pages/LoginPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { UsersPage } from "./pages/UsersPage";
import { WizardPage } from "./pages/WizardPage";

function Protected({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="test" element={<AuthTestPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="endpoints" element={<EndpointsPage />} />
        <Route path="policies" element={<PoliciesPage />} />
        <Route path="clients" element={<ClientsPage />} />
        <Route path="certificates" element={<CertificatesPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="wizard" element={<WizardPage />} />
      </Route>
    </Routes>
  );
}
