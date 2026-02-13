import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { api } from "./api/client.js";
import "./styles.css";

function sendClientError(payload) {
  api.clientLog({
    path: window.location.pathname,
    ...payload,
  });
}

window.addEventListener("error", (event) => {
  sendClientError({
    message: event.message || "window_error",
    stack: event.error?.stack || "",
    details: {
      filename: event.filename || "",
      lineno: event.lineno || 0,
      colno: event.colno || 0,
    },
  });
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  sendClientError({
    message: reason?.message || String(reason || "unhandled_rejection"),
    stack: reason?.stack || "",
    details: {
      type: "unhandledrejection",
      requestId: reason?.requestId || "",
      status: reason?.status || 0,
    },
  });
});

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
