import { useCallback, useEffect, useState } from "react";
import { Shell } from "./components/Shell";
import { useAppData } from "./hooks/useAppData";
import { AdminPage } from "./pages/AdminPage";
import { BlueskyHelpersPage } from "./pages/BlueskyHelpersPage";
import { MapPage } from "./pages/MapPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PipelinePage } from "./pages/PipelinePage";
import { SafetyPage } from "./pages/SafetyPage";
import { VolunteerPage } from "./pages/VolunteerPage";
import { EdgeEarlyWarningPage } from "./pages/EdgeEarlyWarningPage";
import { APP_ROUTES, normalizeAppPath } from "./routes";
import { FloodOperationsPage } from "./pages/FloodOperationsPage";
import { FloodReportPage } from "./pages/FloodReportPage";
import { MLPredictionsPage } from "./pages/MLPredictionsPage";
import "./flood.css";

function AppContent() {
  const [path, setPath] = useState(() => normalizeAppPath(window.location.pathname));
  const data = useAppData();

  useEffect(() => {
    const syncPath = () => {
      const canonicalPath = normalizeAppPath(window.location.pathname);
      if (canonicalPath !== window.location.pathname) {
        window.history.replaceState({}, "", canonicalPath);
      }
      setPath(canonicalPath);
    };
    syncPath();
    const onPopState = () => syncPath();
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((next: string) => {
    const canonicalPath = normalizeAppPath(next);
    if (window.location.pathname !== canonicalPath) window.history.pushState({}, "", canonicalPath);
    setPath(canonicalPath);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const page = (() => {
    switch (path) {
      case APP_ROUTES.flood: return <FloodOperationsPage />;
      case APP_ROUTES.floodReport: return <FloodReportPage />;
      case APP_ROUTES.map: return <MapPage data={data} />;
      case APP_ROUTES.volunteers: return <VolunteerPage data={data} />;
      case APP_ROUTES.safety: return <SafetyPage />;
      case APP_ROUTES.admin: return <AdminPage data={data} />;
      case APP_ROUTES.blueskyHelpers: return <BlueskyHelpersPage />;
      case APP_ROUTES.pipeline: return <PipelinePage data={data} />;
      case APP_ROUTES.edgeEarlyWarning: return <EdgeEarlyWarningPage />;
      case APP_ROUTES.mlPredictions: return <MLPredictionsPage />;
      default: return <OverviewPage data={data} navigate={navigate} />;
    }
  })();

  return <Shell path={path} navigate={navigate} connection={data.connection} loading={data.loading}>{page}</Shell>;
}

export default function App() {
  return <AppContent />;
}
