import "./styles/global.css";

import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1
    }
  }
});

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#176b87" },
    secondary: { main: "#b45309" },
    background: { default: "#f4f6f8", paper: "#ffffff" }
  },
  shape: { borderRadius: 6 },
  typography: {
    fontFamily: ["Inter", "system-ui", "Segoe UI", "sans-serif"].join(",")
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>
);
