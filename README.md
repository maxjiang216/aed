# Election Lab

One repo, one website for a collection of election maps, data projects and what-if experiments.
Live at https://aed-ruby.vercel.app/.

| project | what | code | on the site |
|---|---|---|---|
| American Elections Database | U.S. results by state since 1828, counties since 2000, House districts since 1976; party control of Congress; Bundestag-rules what-if | [`projects/aed`](projects/aed) | `#/president/...`, `#/congress`, `#/germany` |
| Shortest-border districts | equal-population House districts from census blocks minimising total border length; 2020-vote projections; citizen apportionment | [`projects/districting`](projects/districting) | `#/districts`, `#/districts/citizen` |

## Layout

```
index.html, src/, public/   the website (Vite + React + TypeScript), deployed by Vercel
  src/main.tsx              hash router: "#/" home, "#/<project>/..." per project
  src/projects.ts           home-page cards + top-nav links: add new projects here
  src/site/                 shared shell (nav bar, home page)
  src/aed/, src/districting/  each project's pages
  public/<project>/         each project's pre-built data (committed; the site only reads these)
projects/<name>/            each project's pipeline (Python, C++, notebooks, ...), with its own README
```

The site never runs a pipeline. Each project builds its own data into `public/` and that output is
committed, so a deploy is just `npm run build`.

## Run the site

```bash
npm install
npm run dev      # http://localhost:5173
npm test
npm run build    # static site in dist/ (what Vercel runs)
```

## Adding a project

1. Put the code in `projects/<name>/` with a README (how to rebuild its data, sources, licence notes).
2. Write whatever the page needs into `public/<name>/` (small, pre-computed JSON/TopoJSON; keep the
   whole folder to a few MB).
3. Add a page under `src/<name>/`, a case in `src/main.tsx`, and a card in `src/projects.ts`.
   A project hosted elsewhere only needs the card (`href` can be any URL).

Raw downloads, caches and run output stay out of git (`raw/`, `data/`, `output/`, `runs/` are
ignored inside the projects).
