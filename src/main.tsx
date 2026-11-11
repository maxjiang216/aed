import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { GermanRules } from "./components/GermanRules";
import { SeatsTimeline } from "./components/SeatsTimeline";
import "./styles.css";

type Page = "germany" | "congress" | "maps";
const pageOf = (): Page =>
  window.location.hash.startsWith("#/germany") ? "germany"
  : window.location.hash.startsWith("#/congress") ? "congress"
  : "maps";

function Root() {
  const [page, setPage] = useState(pageOf);
  useEffect(() => {
    const on = () => setPage(pageOf());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return page === "germany" ? <GermanRules /> : page === "congress" ? <SeatsTimeline /> : <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
