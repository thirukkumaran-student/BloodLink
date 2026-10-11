/**
 * Browser-shaped boot smoke for the BloodLink SPA.
 *
 * The preview environment has no headless Chrome, so this script boots the real
 * client (bundled with esbuild in IIFE form) inside jsdom, resolves every API
 * call through the Vite dev server exactly like the browser does, and asserts
 * that the login screen renders and that an authenticated dashboard paints real
 * data from the API.
 *
 *   node scripts/web_boot_smoke.mjs [devServerUrl]
 *
 * Preconditions: the API is on :8000 (stop/restart it for a pristine demo seed)
 * and the Vite dev server is on :5173.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import * as esbuild from "esbuild";
import { JSDOM } from "jsdom";

const DEV_SERVER = process.argv[2] ?? "http://127.0.0.1:5173";
const REPO = resolve(new URL("..", import.meta.url).pathname);
const PASSWORD = "Bloodlink#2026";

let checks = 0;
const failures = [];

function check(condition, label, detail = "") {
  checks += 1;
  if (condition) {
    console.log(`  ok  ${label}`);
  } else {
    failures.push(`${label} ${detail}`.trim());
    console.log(`FAIL  ${label} ${detail}`.trimEnd());
  }
}

async function bundle() {
  // jsdom cannot execute ES modules, so the app is bundled to an IIFE. Vite's
  // own build stays the source of truth for production output; this is the same
  // entry point with `import.meta.env` pinned to the dev defaults.
  const out = join(mkdtempSync(join(tmpdir(), "bloodlink-web-")), "smoke.js");
  await esbuild.build({
    entryPoints: [join(REPO, "apps/web/src/main.jsx")],
    bundle: true,
    format: "iife",
    target: "es2022",
    jsx: "automatic",
    loader: { ".jsx": "jsx" },
    // `@bloodlink/ui` resolves through the workspace symlink and its exports map.
    alias: { "@": join(REPO, "apps/web/src") },
    define: {
      "import.meta.env": JSON.stringify({
        VITE_API_BASE_URL: "/api/v1",
        VITE_DEMO_MODE: "true",
      }),
    },
    outfile: out,
    logLevel: "warning",
  });
  return (await import("node:fs")).readFileSync(out, "utf8");
}

const SOURCE = await bundle();

async function boot({ tokens = null } = {}) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: `${DEV_SERVER}/`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  if (tokens) {
    for (const [key, value] of Object.entries(tokens)) window.localStorage.setItem(key, value);
  }
  // The browser resolves relative URLs against the page origin (the Vite dev
  // server), which proxies /api to FastAPI — jsdom needs the real network.
  window.fetch = (input, init) => {
    const raw = typeof input === "string" ? input : input.url;
    return fetch(new URL(raw, DEV_SERVER).href, init);
  };
  window.addEventListener("error", (event) => {
    failures.push(`runtime error: ${event.message}`);
  });
  window.eval(SOURCE);
  return window;
}

async function settle(window, predicate, { timeoutMs = 15000, label = "condition" } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (predicate(window)) return true;
    await new Promise((r) => setTimeout(r, 120));
  }
  failures.push(`timeout waiting for ${label}`);
  return false;
}

const text = (window) => window.document.getElementById("root").textContent ?? "";

async function loginThroughTheForm(window, accountName) {
  await settle(window, () => window.document.querySelector("input[type=password]"), {
    label: "the login form to mount",
  });
  const button = [...window.document.querySelectorAll("button")].find((node) =>
    node.textContent.includes(accountName),
  );
  check(Boolean(button), `login screen offers the demo account for ${accountName}`);
  button?.click();
  await settle(window, () => window.localStorage.getItem("bloodlink.accessToken"), {
    label: `login of ${accountName} to store an access token`,
  });
  return {
    "bloodlink.accessToken": window.localStorage.getItem("bloodlink.accessToken") ?? "",
    "bloodlink.refreshToken": window.localStorage.getItem("bloodlink.refreshToken") ?? "",
  };
}

async function session(credentials) {
  const response = await fetch(`${DEV_SERVER}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${credentials["bloodlink.accessToken"]}` },
  });
  const payload = await response.json();
  return payload.data;
}

console.log(`web boot smoke via ${DEV_SERVER}`);

// 1. anonymous boot renders the login screen
console.log("\n[anonymous] login screen");
const anonymous = await boot();
await settle(anonymous, () => text(anonymous).includes("BloodLink"), { label: "the app shell to mount" });
check(text(anonymous).includes("BloodLink"), "the SPA mounts and renders the brand");
if (process.env.BLOODLINK_SMOKE_DEBUG) console.log("--- login screen text ---\n" + text(anonymous) + "\n--- end ---");
check(Boolean(anonymous.document.querySelector("input[type=password]")), "the login form renders a password field");

// 2. sign in as the hospital through the real form, then boot authenticated
console.log("\n[hospital] login then authenticated dashboard");
const hospitalTokens = await loginThroughTheForm(anonymous, "Dr. Kavitha Rao");
check(Boolean(hospitalTokens["bloodlink.accessToken"]), "the form login stored an access token");
const hospitalUser = await session(hospitalTokens);
check(hospitalUser?.role === "HOSPITAL", "the token identifies a HOSPITAL user", `got ${hospitalUser?.role}`);
check(
  Array.isArray(hospitalUser?.capabilities) && hospitalUser.capabilities.length > 0,
  "the session carries server-side capabilities",
);

const dashboard = await boot({ tokens: hospitalTokens });
await settle(
  dashboard,
  () =>
    dashboard.document.querySelector("tbody tr") &&
    /review queue/i.test(dashboard.document.querySelector("h1")?.textContent ?? ""),
  { label: "the hospital review queue to render its rows" },
);
if (process.env.BLOODLINK_SMOKE_DEBUG) {
  console.log("--- hospital dashboard text ---\n" + text(dashboard) + "\n--- end ---");
}
check(
  /review queue/i.test(dashboard.document.querySelector("h1")?.textContent ?? ""),
  "the hospital lands on its review queue",
);
const rows = dashboard.document.querySelectorAll("tbody tr").length;
check(rows > 0, "the queue renders requirement rows", `rows=${rows}`);
check(text(dashboard).includes("Request board"), "role-aware navigation shows the hospital surfaces");
check(text(dashboard).includes("Approve") || text(dashboard).includes("Request created"),
  "each row offers its hospital decision or shows the outcome");

// 3. the donor role renders its own home with the seeded matched request
console.log("\n[donor] matched request discovery");
const donorFlow = await boot();
const donorTokens = await loginThroughTheForm(donorFlow, "Priya Raman");
const donorUser = await session(donorTokens);
check(donorUser?.role === "INDIVIDUAL" || donorUser?.role === "DONOR",
  "the token identifies the donor account", `got ${donorUser?.role}`);
const donorHome = await boot({ tokens: donorTokens });
await settle(donorHome, () => donorHome.document.querySelector("tbody tr, .bl-card"), {
  label: "the donor dashboard to paint",
});
check(
  /hello, priya/i.test(donorHome.document.querySelector("h1")?.textContent ?? ""),
  "the donor lands on their own dashboard",
);
check(
  text(donorHome).includes("Apollo General"),
  "the seeded emergency request is discoverable by the donor",
);
check(
  /my reaches|my commitments|availability/i.test(text(donorHome)) ||
    donorHome.document.querySelectorAll("nav a").length > 0,
  "the donor navigation renders",
);

// 4. a token the server rejects (DB reset, revoked session) must return the user
//    to sign-in instead of polling forever with a dead token
console.log("\n[expired session] a rejected token returns to sign-in");
const stale = await boot({
  tokens: {
    "bloodlink.accessToken": "stale-access-token",
    "bloodlink.refreshToken": "stale-refresh-token",
  },
});
await settle(stale, () => !stale.localStorage.getItem("bloodlink.accessToken"), {
  label: "the rejected session to be cleared from storage",
});
check(
  !stale.localStorage.getItem("bloodlink.accessToken"),
  "the rejected token is cleared from localStorage",
);
await settle(stale, () => stale.document.querySelector("input[type=password]"), {
  label: "the sign-in form to come back",
});
check(
  Boolean(stale.document.querySelector("input[type=password]")),
  "the app returns to the sign-in screen",
);

console.log(`\n${checks - failures.length}/${checks} checks passed`);
for (const failure of failures) console.log(`  - ${failure}`);
if (failures.length) {
  process.exit(1);
}
console.log("web boot smoke: all checks passed");
// jsdom keeps timers alive; exit explicitly once the assertions are done.
process.exit(0);
