import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./aed/App";
import { GermanRules } from "./aed/components/GermanRules";
import { SeatsTimeline } from "./aed/components/SeatsTimeline";
import { DistrictsPage } from "./districting/DistrictsPage";
import { Home, Nav } from "./site/Shell";
import "./styles.css";

/** Hash routes: "#/" home, "#/<project>/..." for each project. The election maps keep their
 *  original routes ("#/president/state/2024/result", ...). */
const PAGES = {
  home: Home,
  germany: GermanRules,
  congress: SeatsTimeline,
  districts: DistrictsPage,
  elections: App,
};

function pageKey(hash: string): keyof typeof PAGES {
  const first = hash.replace(/^#\/?/, "").split("/")[0];
  if (first === "") return "home";
  return first in PAGES && first !== "elections" && first !== "home" ? (first as keyof typeof PAGES) : "elections";
}

function Root() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const key = pageKey(hash);
  const Page = PAGES[key];
  return (
    <>
      <Nav hash={hash} />
      {/* key: remount when switching project so each page reads its own hash state fresh */}
      <Page key={key} />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
