import type { ReactNode } from "react";
import { PROJECTS, REPO_URL, SITE_NAME } from "../projects";

/** Top bar shared by every page. */
export function Nav({ hash }: { hash: string }) {
  const active = (routes?: string[]) => !!routes?.some((r) => hash === r || hash.startsWith(`${r}/`));
  return (
    <nav className="site-nav" aria-label="Site">
      <a className="site-name" href="#/">{SITE_NAME}</a>
      <ul>
        {PROJECTS.filter((p) => p.nav).map((p) => (
          <li key={p.href}>
            <a href={p.href} aria-current={active(p.routes) ? "page" : undefined}>{p.nav}</a>
          </li>
        ))}
      </ul>
      <a className="site-gh" href={REPO_URL}>GitHub</a>
    </nav>
  );
}

export function Home() {
  return (
    <div className="app home">
      <header className="home-head">
        <h1>{SITE_NAME}</h1>
        <p className="lede">Maps, data and what-if experiments about elections and other things we found interesting.</p>
      </header>
      <ul className="cards">
        {PROJECTS.map((p) => (
          <li key={p.href} className="card" style={{ "--card-accent": p.accent } as React.CSSProperties}>
            <a href={p.href}>
              <h2>{p.title}</h2>
              <p>{p.blurb}</p>
              <Meta author={p.author} tags={p.tags} />
            </a>
          </li>
        ))}
      </ul>
      <footer className="foot">
        Open source: <a href={REPO_URL}>code and data on GitHub</a>. Each project lists its sources on its own page.
      </footer>
    </div>
  );
}

function Meta({ author, tags }: { author: string; tags: string[] }): ReactNode {
  return (
    <p className="card-meta">
      <span>{author}</span>
      {tags.map((t) => <span key={t} className="tag">{t}</span>)}
    </p>
  );
}
