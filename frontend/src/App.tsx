import { useState } from "react";
import RunsPage from "./pages/RunsPage";
import SubmitPage from "./pages/SubmitPage";
import RunDetailPage from "./pages/RunDetailPage";
import "./App.css";

export type Page =
  | { id: "runs" }
  | { id: "submit" }
  | { id: "detail"; runId: string };

export default function App() {
  const [page, setPage] = useState<Page>({ id: "runs" });

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <button className="logo" onClick={() => setPage({ id: "runs" })}>
            <div className="logo-mark">AP</div>
            <span className="logo-name">AutoPaper</span>
          </button>
          <nav className="nav">
            <NavBtn active={page.id === "runs"} onClick={() => setPage({ id: "runs" })}>
              Runs
            </NavBtn>
            <NavBtn active={page.id === "submit"} onClick={() => setPage({ id: "submit" })}>
              + New Run
            </NavBtn>
          </nav>
        </div>
      </header>

      <main className="main">
        {page.id === "runs" && (
          <RunsPage
            onOpen={(id) => setPage({ id: "detail", runId: id })}
            onNew={() => setPage({ id: "submit" })}
          />
        )}
        {page.id === "submit" && (
          <SubmitPage onStarted={(id) => setPage({ id: "detail", runId: id })} />
        )}
        {page.id === "detail" && (
          <RunDetailPage
            runId={page.runId}
            onBack={() => setPage({ id: "runs" })}
          />
        )}
      </main>
    </div>
  );
}

function NavBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button className={`nav-btn${active ? " active" : ""}`} onClick={onClick}>
      {children}
    </button>
  );
}
