import { Outlet } from "react-router";
import { ScanlineOverlay } from "./ScanlineOverlay";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { ErrorBoundary } from "../shared/ErrorBoundary";

export function AppShell() {
  return (
    <>
      <ScanlineOverlay />
      <Header />
      <Sidebar />
      <main className="ml-64 pt-16 h-screen overflow-auto">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </>
  );
}
