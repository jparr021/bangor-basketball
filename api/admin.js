// The admin page's server side (a Vercel function at /api/admin).
//
// It checks the admin password, then saves changes straight into the GitHub repository: the photo file
// in overrides/photos/ and its line in overrides/photos.csv, together in one commit. Vercel rebuilds the
// site on every commit, so a change is live a few minutes later.
//
// Settings (Vercel → Project → Settings → Environment Variables):
//   ADMIN_PASSWORD  the password for /admin
//   GITHUB_TOKEN    a fine-grained GitHub token for this repository only, with Contents: Read and write
//   GITHUB_REPO     optional, default jparr021/bangor-basketball
//   GITHUB_BRANCH   optional, default main
const crypto = require("crypto");

const REPO = process.env.GITHUB_REPO || "jparr021/bangor-basketball";
const BRANCH = process.env.GITHUB_BRANCH || "main";
const CSV_PATH = "overrides/photos.csv";
const PHOTO_DIR = "overrides/photos/";
const COLS = ["kind", "season", "player", "image", "caption", "credit"];
const MAX_BYTES = 3.5 * 1024 * 1024;

// ---------------------------------------------------------------- CSV (quoted fields, as Python's csv module writes)
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') q = false;
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const head = (rows.shift() || COLS).map((h) => h.trim());
  return rows.filter((r) => r.some((v) => v.trim() !== ""))
    .map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] || ""])));
}

function csvField(v) {
  v = String(v == null ? "" : v);
  return /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function toCsv(rows) {
  return [COLS.join(","), ...rows.map((r) => COLS.map((k) => csvField(r[k])).join(","))].join("\n") + "\n";
}

// ---------------------------------------------------------------- GitHub
async function gh(path, opts = {}) {
  const r = await fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "bangor-bb-admin",
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  const body = r.status === 204 ? {} : await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(`GitHub ${r.status}: ${body.message || "request failed"}`);
    err.status = r.status;
    throw err;
  }
  return body;
}

async function readPhotos() {
  const ref = await gh(`/git/ref/heads/${BRANCH}`);
  const head = ref.object.sha;
  let rows = [];
  try {
    const f = await gh(`/contents/${CSV_PATH}?ref=${head}`);
    rows = parseCsv(Buffer.from(f.content, "base64").toString("utf8"));
  } catch (e) {
    if (e.status !== 404) throw e;
  }
  return { head, rows };
}

// One commit with every change: files is a list of {path, base64} to write, or {path, remove: true}.
async function commit(head, files, message) {
  const base = await gh(`/git/commits/${head}`);
  const tree = [];
  for (const f of files) {
    if (f.remove) {
      tree.push({ path: f.path, mode: "100644", type: "blob", sha: null });
    } else {
      const blob = await gh("/git/blobs", { method: "POST", body: JSON.stringify({ content: f.base64, encoding: "base64" }) });
      tree.push({ path: f.path, mode: "100644", type: "blob", sha: blob.sha });
    }
  }
  const t = await gh("/git/trees", { method: "POST", body: JSON.stringify({ base_tree: base.tree.sha, tree }) });
  const c = await gh("/git/commits", { method: "POST", body: JSON.stringify({ message, tree: t.sha, parents: [head] }) });
  await gh(`/git/refs/heads/${BRANCH}`, { method: "PATCH", body: JSON.stringify({ sha: c.sha }) });
  return c.sha;
}

// Read, change and commit; if someone else committed in between (the ref moved), start over once.
async function change(fn) {
  for (let attempt = 0; ; attempt++) {
    const { head, rows } = await readPhotos();
    const { files, message, result } = fn(rows);
    try {
      await commit(head, files, message);
      return result;
    } catch (e) {
      if (attempt === 0 && (e.status === 422 || e.status === 409)) continue;
      throw e;
    }
  }
}

// ---------------------------------------------------------------- helpers
function sameSecret(a, b) {
  const h = (s) => crypto.createHash("sha256").update(String(s)).digest();
  return crypto.timingSafeEqual(h(a), h(b));
}

function slug(s) {
  return String(s).toLowerCase().replace(/['.]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

const clean = (s, n) => String(s || "").replace(/[\r\n]+/g, " ").trim().slice(0, n);
const fail = (res, code, error) => res.status(code).json({ error });

// ---------------------------------------------------------------- the handler
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return fail(res, 405, "Use POST.");
  if (!process.env.ADMIN_PASSWORD || !process.env.GITHUB_TOKEN) {
    return fail(res, 503, "The admin page isn't set up yet: add ADMIN_PASSWORD and GITHUB_TOKEN in Vercel (see the README).");
  }
  if (!sameSecret(req.headers["x-admin-password"] || "", process.env.ADMIN_PASSWORD)) {
    await new Promise((r) => setTimeout(r, 1500)); // slows down password guessing
    return fail(res, 401, "Wrong password.");
  }
  const b = req.body || {};
  try {
    if (b.action === "check") return res.json({ ok: true });

    if (b.action === "list") {
      const { rows } = await readPhotos();
      return res.json({ photos: rows });
    }

    if (b.action === "add") {
      const kind = b.kind === "team" ? "team" : b.kind === "player" ? "player" : "";
      const season = clean(b.season, 7);
      const player = clean(b.player, 80);
      if (!kind) return fail(res, 400, "Choose team photo or player headshot.");
      if (kind === "team" && !/^\d{4}-\d{2}$/.test(season)) return fail(res, 400, "Choose a season.");
      if (kind === "player" && !player) return fail(res, 400, "Choose a player.");
      const img = Buffer.from(String(b.image || ""), "base64");
      if (img.length < 100 || img[0] !== 0xff || img[1] !== 0xd8) return fail(res, 400, "That photo didn't come through as a JPEG. Try again.");
      if (img.length > MAX_BYTES) return fail(res, 400, "That photo is too big. Try a smaller one.");
      const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
      const image = `${kind}-${kind === "team" ? season : slug(player)}-${stamp}.jpg`;
      const row = { kind, season: kind === "team" ? season : "", player: kind === "player" ? player : "", image,
                    caption: clean(b.caption, 300), credit: clean(b.credit, 120) };
      const what = kind === "team" ? `${season} team photo` : `headshot of ${player}`;
      await change((rows) => ({
        files: [{ path: PHOTO_DIR + image, base64: img.toString("base64") },
                { path: CSV_PATH, base64: Buffer.from(toCsv([...rows, row])).toString("base64") }],
        message: `Add ${what} (from the admin page)`,
      }));
      return res.json({ ok: true, photo: row });
    }

    if (b.action === "remove") {
      const image = clean(b.image, 200);
      let found = null;
      await change((rows) => {
        found = rows.find((r) => r.image === image);
        if (!found) { const e = new Error("That photo is already gone."); e.status = 404; throw e; }
        const local = !/^https?:\/\//.test(image) && !image.includes("/") && !image.includes("..");
        return {
          files: [...(local ? [{ path: PHOTO_DIR + image, remove: true }] : []),
                  { path: CSV_PATH, base64: Buffer.from(toCsv(rows.filter((r) => r !== found))).toString("base64") }],
          message: `Remove ${found.kind === "team" ? found.season + " team photo" : "headshot of " + found.player} (from the admin page)`,
        };
      });
      return res.json({ ok: true });
    }

    return fail(res, 400, "Unknown action.");
  } catch (e) {
    if (e.status === 404 && e.message === "That photo is already gone.") return fail(res, 404, e.message);
    if (e.status === 401 || e.status === 403) {
      return fail(res, 502, "GitHub refused the change. Check that GITHUB_TOKEN is current and has Contents: Read and write on this repository.");
    }
    console.error(e);
    return fail(res, 502, `Couldn't save to GitHub (${e.message}). Nothing was changed. Try again in a minute.`);
  }
};

module.exports.parseCsv = parseCsv;
module.exports.toCsv = toCsv;
