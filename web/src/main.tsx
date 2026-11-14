import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { CasePage } from "./features/CasePage";
import { LoginGate } from "./features/LoginGate";
import { QueuePage } from "./features/QueuePage";
import { SearchPage } from "./features/SearchPage";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Scenarios are static files on disk; investigations change only when one
      // is run. Neither benefits from refetching every time a window refocuses.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm transition duration-150 ${
    isActive ? "bg-raised font-medium text-text" : "text-dim hover:bg-raised/60 hover:text-text"
  }`;
}

function Shell({ children }: { children: React.ReactNode }) {
  const onCase = useLocation().pathname.startsWith("/cases/");
  return (
    <div className="flex min-h-full flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-ink"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-10 border-b border-edge bg-ink/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/favicon.svg" alt="" className="size-7" />
            <span className="text-[15px] font-semibold tracking-tight">alert2attack</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1">
            <NavLink to="/" end className={(s) => navClass({ isActive: s.isActive || onCase })}>
              Alert queue
            </NavLink>
            <NavLink to="/search" className={navClass}>
              Technique search
            </NavLink>
          </nav>
          <p className="ml-auto hidden text-xs text-dim md:block">The agent recommends. A person decides.</p>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 pt-8 pb-16 sm:px-6">
        {children}
      </main>
    </div>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <LoginGate>
          <Shell>
            <Routes>
              <Route path="/" element={<QueuePage />} />
              <Route path="/cases/:scenarioId" element={<CasePage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Shell>
        </LoginGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
