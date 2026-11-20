import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import { AppShell } from "@/components/AppShell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PeriodProvider } from "@/lib/period";
import { ExposurePage } from "@/pages/ExposurePage";
import { InboxPage } from "@/pages/InboxPage";
import { RulesPage } from "@/pages/RulesPage";
import { SentinelPage } from "@/pages/SentinelPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <InboxPage /> },
      { path: "exposure", element: <ExposurePage /> },
      { path: "sentinel", element: <SentinelPage /> },
      { path: "rules", element: <RulesPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <PeriodProvider>
          <RouterProvider router={router} />
        </PeriodProvider>
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
);
