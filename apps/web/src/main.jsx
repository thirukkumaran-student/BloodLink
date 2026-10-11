import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@bloodlink/ui";
import "@bloodlink/ui/styles/tokens.css";
import "@bloodlink/ui/styles/components.css";
import { App } from "./app/App";
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15e3
    }
  }
});
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><ToastProvider><App /></ToastProvider></BrowserRouter></QueryClientProvider></React.StrictMode>
);
