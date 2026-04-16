/**
 * MooseGlove — application entry point.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import { Providers } from "@/app/providers";
import { logger } from "@/lib/logger";
import "@/styles/globals.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found. Check index.html.");
}

logger.info("app.bootstrap", {
  env: import.meta.env.MODE,
  api: import.meta.env.VITE_API_URL,
});

createRoot(rootElement).render(
  <StrictMode>
    <Providers>
      <App />
    </Providers>
  </StrictMode>,
);
