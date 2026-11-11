import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { GermanRules } from "./components/GermanRules";
import "./styles.css";

const isGermany = () => window.location.hash.startsWith("#/germany");

function Root() {
  const [germany, setGermany] = useState(isGermany);
  useEffect(() => {
    const on = () => setGermany(isGermany());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return germany ? <GermanRules /> : <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
