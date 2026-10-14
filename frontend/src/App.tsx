import { useCallback, useEffect, useState } from "react";
import { Navbar, type PageKey } from "./components/Navbar";
import Analytics from "./pages/Analytics";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import Evaluation from "./pages/Evaluation";
import Models from "./pages/Models";
import Requests from "./pages/Requests";
import { API_BASE_URL, getMetrics, getModels, getRequests } from "./services/api";
import type { GatewayMetrics, ModelInfo, RequestRecord } from "./types";
import "./styles.css";

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>("Dashboard");
  const [metrics, setMetrics] = useState<GatewayMetrics | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [requests, setRequests] = useState<RequestRecord[]>([]);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [requestsError, setRequestsError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refreshData = useCallback(async () => {
    setIsRefreshing(true);
    const [metricsResult, modelsResult, requestsResult] = await Promise.allSettled([
      getMetrics(),
      getModels(),
      getRequests(),
    ]);

    if (metricsResult.status === "fulfilled") {
      setMetrics(metricsResult.value);
      setMetricsError(null);
    } else {
      setMetricsError(errorMessage(metricsResult.reason));
    }

    if (modelsResult.status === "fulfilled") {
      setModels(modelsResult.value);
      setModelsError(null);
    } else {
      setModelsError(errorMessage(modelsResult.reason));
    }

    if (requestsResult.status === "fulfilled") {
      setRequests(requestsResult.value);
      setRequestsError(null);
    } else {
      setRequestsError(errorMessage(requestsResult.reason));
    }

    setIsLoading(false);
    setIsRefreshing(false);
  }, []);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  return (
    <div className="app-shell">
      <Navbar activePage={activePage} onNavigate={setActivePage} onRefresh={() => void refreshData()} isRefreshing={isRefreshing} endpoint={API_BASE_URL} />
      <main className={`main-content${activePage === "Chat" ? " main-content--chat" : ""}`}>
        {activePage === "Dashboard" && <Dashboard metrics={metrics} models={models} requests={requests} isLoading={isLoading} metricsError={metricsError} requestsError={requestsError} onOpenRequests={() => setActivePage("Requests")} />}
        {activePage === "Models" && <Models models={models} isLoading={isLoading} error={modelsError} />}
        {activePage === "Requests" && <Requests requests={requests} isLoading={isLoading} error={requestsError} />}
        {activePage === "Analytics" && <Analytics />}
        {activePage === "Evaluation" && <Evaluation />}
        {activePage === "Chat" && <Chat />}
        {activePage !== "Chat" && <footer className="app-footer"><span>SWITCHBOARD AI</span><span>INTELLIGENT LLM ROUTING</span></footer>}
      </main>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected API error occurred.";
}