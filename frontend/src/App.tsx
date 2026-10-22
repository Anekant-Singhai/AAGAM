import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import HomePage from "./pages/HomePage";
import LibraryPage from "./pages/LibraryPage";
import DocumentPage from "./pages/DocumentPage";
import SearchPage from "./pages/SearchPage";
import PrecedentsPage from "./pages/PrecedentsPage";
import CalculatorsPage from "./pages/CalculatorsPage";
import DueDatesPage from "./pages/DueDatesPage";
import WorkPage from "./pages/WorkPage";
import WorkDetailPage from "./pages/WorkDetailPage";
import FinancialsPage from "./pages/FinancialsPage";
import FinancialDetailPage from "./pages/FinancialDetailPage";
import EntitiesPage from "./pages/EntitiesPage";
import DossierPage from "./pages/DossierPage";
import NotesPage from "./pages/NotesPage";
import HelpPage from "./pages/HelpPage";
import CompaniesPage from "./pages/CompaniesPage";
import CompanyPage from "./pages/CompanyPage";
import InsightsPage from "./pages/InsightsPage";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/work" element={<WorkPage />} />
          <Route path="/work/:id" element={<WorkDetailPage />} />
          <Route path="/notes" element={<NotesPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/documents/:id" element={<DocumentPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/precedents" element={<PrecedentsPage />} />
          <Route path="/entities" element={<EntitiesPage />} />
          <Route path="/entities/:kind/:key" element={<DossierPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/insights/:kind" element={<InsightsPage />} />
          <Route path="/financials" element={<FinancialsPage />} />
          <Route path="/financials/:id" element={<FinancialDetailPage />} />
          <Route path="/calculators" element={<CalculatorsPage />} />
          <Route path="/due" element={<DueDatesPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/companies/:id" element={<CompanyPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
