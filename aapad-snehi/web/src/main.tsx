import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { api } from "./lib/api";
import { flushCitizenReports } from "./lib/offline-queue";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

window.addEventListener("online", () => {
  void flushCitizenReports(api.submitReport);
});
