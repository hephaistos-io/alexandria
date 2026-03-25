import { BrowserRouter, Routes, Route } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { GlobalOverviewPage } from "./pages/GlobalOverviewPage";
import { InfrastructurePage } from "./pages/InfrastructurePage";
import { LabellingPage } from "./pages/LabellingPage";
import { MonitorPage } from "./pages/MonitorPage";
import { ArchivePage } from "./pages/ArchivePage";
import { ArticleDetailPage } from "./pages/ArticleDetailPage";
import { TerminalPage } from "./pages/TerminalPage";
import { AttributionPage } from "./pages/AttributionPage";
import { AffiliationGraphPage } from "./pages/AffiliationGraphPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<GlobalOverviewPage />} />
          <Route path="monitor" element={<MonitorPage />} />
          <Route path="infrastructure" element={<InfrastructurePage />} />
          <Route path="labelling" element={<LabellingPage />} />
          <Route path="attribution" element={<AttributionPage />} />
          <Route path="graph" element={<AffiliationGraphPage />} />
          <Route path="archive" element={<ArchivePage />} />
          <Route path="archive/:id" element={<ArticleDetailPage />} />
          <Route path="terminal" element={<TerminalPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
