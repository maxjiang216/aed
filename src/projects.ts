/** Everything the home page lists. Add a project here (and a route in main.tsx if it lives in
 *  this site; an external `href` works too). Keep blurbs to one or two sentences. */

export const SITE_NAME = "Election Lab";
export const REPO_URL = "https://github.com/maxjiang216/election-lab";

export interface Project {
  title: string;
  blurb: string;
  href: string;
  author: string;
  tags: string[];
  /** Card accent colour (any CSS colour). */
  accent: string;
  /** Short label for the top navigation; omit to keep it off the nav bar. */
  nav?: string;
  /** Hash prefixes that count as "inside" this project, for highlighting the nav link. */
  routes?: string[];
}

export const PROJECTS: Project[] = [
  {
    title: "Election maps",
    blurb: "U.S. president, Senate and governor results by state since 1828, counties since 2000 and House districts since 1976, with swing, flip and trend views.",
    href: "#/president/state/2024/result",
    author: "Max",
    tags: ["maps", "data"],
    accent: "#3b6fc4",
    nav: "Elections",
    routes: ["#/president", "#/senate", "#/governor", "#/house"],
  },
  {
    title: "Shortest-border districts",
    blurb: "What if every state drew equal-population House districts with the least total border? Algorithmic maps from census blocks, compared with the enacted ones.",
    href: "#/districts",
    author: "Max",
    tags: ["redistricting", "algorithms"],
    accent: "#2e8b6e",
    nav: "Districts",
    routes: ["#/districts/map"],
  },
  {
    title: "Citizen apportionment",
    blurb: "House seats and electoral votes if states were apportioned by citizens rather than residents.",
    href: "#/districts/citizen",
    author: "Max",
    tags: ["counterfactual"],
    accent: "#b07a1f",
    routes: ["#/districts/citizen"],
  },
  {
    title: "Party control of Congress",
    blurb: "Seats held by each party in the House and Senate, day by day, from the 1st Congress on.",
    href: "#/congress",
    author: "Max",
    tags: ["history", "chart"],
    accent: "#c8343f",
    nav: "Congress",
    routes: ["#/congress"],
  },
  {
    title: "The House under German rules",
    blurb: "Re-run U.S. House and Canadian elections with the Bundestag's mixed-member proportional system.",
    href: "#/germany",
    author: "Max",
    tags: ["counterfactual", "electoral systems"],
    accent: "#6e2e5b",
    nav: "German rules",
    routes: ["#/germany"],
  },
];
