// The admin page's server side (a Vercel function at /api/admin).
//
// It checks the admin password, then saves changes straight into the GitHub repository, one commit per
// change: photos (overrides/photos/ and photos.csv), links on game pages (news_stories.csv, game_film.csv,
// hudl_video.csv), rosters (rosters.csv), season lines (season_history.csv), class years (grad_years.csv), and
// the news and film finders' review lists (data/stories_review.csv, data/film_review.csv). Each change is also written
// to overrides/admin_log.jsonl, which is what the page's "Recent changes" list and its Undo buttons use.
// Vercel rebuilds the site on every commit, so a change is live a few minutes later.
//
// Settings (Vercel → Project → Settings → Environment Variables):
//   ADMIN_PASSWORD  the password for /admin
//   GITHUB_TOKEN    a fine-grained GitHub token for this repository only, with Contents: Read and write
//   GITHUB_REPO     optional, default jparr021/bangor-basketball
//   GITHUB_BRANCH   optional, default main
const crypto = require("crypto");

const REPO = process.env.GITHUB_REPO || "jparr021/bangor-basketball";
const BRANCH = process.env.GITHUB_BRANCH || "main";
const PHOTO_DIR = "overrides/photos/";
const LOG_PATH = "overrides/admin_log.jsonl";
const LOG_KEEP = 300;
const MAX_BYTES = 3.5 * 1024 * 1024;

// ---------------------------------------------------------------- input checks
class Bad extends Error { constructor(msg, status = 400) { super(msg); this.status = status; this.user = true; } }
const clean = (s, n) => String(s == null ? "" : s).replace(/[\r\n]+/g, " ").trim().slice(0, n);
const DATE = /^\d{4}-\d{2}-\d{2}$/, SEASON = /^\d{4}-\d{2}$/, URL_RE = /^https?:\/\/\S+$/i;
const YT_RE = /(?:youtu\.be\/|youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|live\/|shorts\/))[A-Za-z0-9_-]{11}/;
const need = (v, what) => { if (!v) throw new Bad(`Fill in ${what}.`); return v; };
const match = (v, re, what) => { if (!re.test(v)) throw new Bad(`${what}`); return v; };
const oneOf = (v, list, what) => { if (!list.includes(v)) throw new Bad(`Choose ${what}.`); return v; };
const count = (v, what) => { v = clean(v, 3); if (v && !/^\d{1,3}$/.test(v)) throw new Bad(`${what} has to be a number.`); return v; };
const fmtDate = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const game = (r, dateKey) => `${fmtDate(r[dateKey])} ${r.opponent}`;

// ---------------------------------------------------------------- the files the admin page can change
const TABLES = {
  photos: {
    path: "overrides/photos.csv", cols: ["kind", "season", "player", "image", "caption", "credit"],
    label: (r) => (r.kind === "team" ? `${r.season} team photo` : `headshot of ${r.player}`),
  },
  news: {
    path: "overrides/news_stories.csv",
    cols: ["published", "outlet", "kind", "title", "url", "access", "game_date", "opponent", "player", "matched_by"],
    soft: true, // a removed row stays (marked removed) so the news-finder doesn't add it back
    label: (r) => `${r.kind === "photos" ? "photo gallery" : r.kind === "video" ? "news video" : "news story"} “${r.title}”` +
                  (r.game_date ? ` (${game(r, "game_date")})` : r.player ? ` (about ${r.player})` : ""),
    check: (r) => {
      // a game story, or a feature about one player (Play of the Week and the like) with no game
      const feature = !clean(r.game_date, 10) && clean(r.player, 80);
      return {
        published: match(clean(r.published, 10), DATE, "Fill in the date it was published."),
        outlet: need(clean(r.outlet, 60), "who published it"),
        kind: oneOf(clean(r.kind, 10), ["article", "video", "photos"], "story, video or photos"),
        title: need(clean(r.title, 200), "the headline"),
        url: match(clean(r.url, 600), URL_RE, "The link has to start with https://"),
        access: oneOf(clean(r.access, 12), ["free", "subscriber"], "free or subscriber-only"),
        game_date: feature ? "" : match(clean(r.game_date, 10), DATE, "Choose the game."),
        opponent: feature ? "" : need(clean(r.opponent, 60), "the opponent"),
        player: clean(r.player, 80),
        matched_by: "manual",
      };
    },
  },
  film: {
    path: "overrides/game_film.csv", cols: ["date", "opponent", "youtube_url", "title", "matched_by"], soft: true,
    label: (r) => `YouTube film (${game(r, "date")})`,
    check: (r) => ({
      date: match(clean(r.date, 10), DATE, "Choose the game."),
      opponent: need(clean(r.opponent, 60), "the opponent"),
      youtube_url: match(clean(r.youtube_url, 300), YT_RE, "That doesn't look like a YouTube video link."),
      title: clean(r.title, 200),
      matched_by: "manual",
    }),
  },
  hudl: {
    path: "overrides/hudl_video.csv", cols: ["date", "opponent", "kind", "access", "url", "title"],
    label: (r) => `Hudl ${r.kind === "recap" ? "recap" : "full game"} (${game(r, "date")})`,
    check: (r) => ({
      date: match(clean(r.date, 10), DATE, "Choose the game."),
      opponent: need(clean(r.opponent, 60), "the opponent"),
      kind: oneOf(clean(r.kind, 10), ["full", "recap"], "full game or recap"),
      access: oneOf(clean(r.access, 10), ["free", "login", "paid"], "who can watch it"),
      url: match(clean(r.url, 600), /^https:\/\/([a-z0-9-]+\.)*hudl\.com\/\S+$/i, "That doesn't look like a Hudl link."),
      title: clean(r.title, 200),
    }),
  },
  roster: {
    path: "overrides/rosters.csv", cols: ["season", "number", "name", "position", "height", "grade", "source"],
    label: (r) => `${r.name} on the ${r.season} roster`,
    check: (r) => {
      const grade = clean(r.grade, 2);
      if (grade && !/^(7|8|9|10|11|12)$/.test(grade)) throw new Bad("Grade has to be 9 to 12 (or blank).");
      return {
        season: match(clean(r.season, 7), SEASON, "Choose a season."),
        number: clean(r.number, 6),
        name: need(clean(r.name, 80), "the player's name"),
        position: clean(r.position, 12), height: clean(r.height, 10), grade, source: clean(r.source, 200),
      };
    },
  },
  season: {
    path: "overrides/season_history.csv", cols: ["season", "w", "l", "t", "coach", "notes"], key: "season",
    label: (r) => `${r.season} season line`,
    check: (r) => ({
      season: match(clean(r.season, 7), SEASON, "Choose a season."),
      w: count(r.w, "Wins"), l: count(r.l, "Losses"), t: count(r.t, "Ties"),
      coach: clean(r.coach, 80), notes: clean(r.notes, 500),
    }),
  },
  grad: {
    path: "overrides/grad_years.csv", cols: ["name", "grad_year", "note"], key: "name",
    label: (r) => `class year for ${r.name}`,
    check: (r) => ({
      name: need(clean(r.name, 80), "the player's name"),
      grad_year: match(clean(r.grad_year, 4), /^(19|20)\d\d$/, "The class year has to be a year, like 2027."),
      note: clean(r.note, 200),
    }),
  },
  // what the news and film finders weren't sure about (scripts/match_stories.py, scripts/match_film.py)
  storyReview: {
    path: "data/stories_review.csv", cols: ["published", "outlet", "kind", "title", "url", "reason", "candidates"],
  },
  filmReview: {
    path: "data/film_review.csv", cols: ["title", "youtube_url", "upload_date", "reason", "candidates"],
  },
};
const EDITABLE = ["news", "film", "hudl", "roster", "season", "grad"];

// ---------------------------------------------------------------- CSV (quoted fields, as Python's csv module writes)
function parseCsv(text, defaultCols = []) {
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
  const head = (rows.shift() || defaultCols).map((h) => h.trim());
  return rows.filter((r) => r.some((v) => v.trim() !== ""))
    .map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] || ""])));
}

function csvField(v) {
  v = String(v == null ? "" : v);
  return /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function toCsv(rows, cols = TABLES.photos.cols, eol = "\n") {
  return [cols.join(","), ...rows.map((r) => cols.map((k) => csvField(r[k])).join(","))].join(eol) + eol;
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

async function headSha() {
  return (await gh(`/git/ref/heads/${BRANCH}`)).object.sha;
}

// A file at a commit: its text and blob sha, or null if it isn't there.
async function getFile(head, path) {
  try {
    const f = await gh(`/contents/${path}?ref=${head}`);
    let content = f.content;
    if (!content && f.sha) content = (await gh(`/git/blobs/${f.sha}`)).content; // files over 1 MB
    return { text: Buffer.from(content || "", "base64").toString("utf8"), sha: f.sha };
  } catch (e) {
    if (e.status === 404) return null;
    throw e;
  }
}

async function readTable(head, name) {
  const t = TABLES[name], f = await getFile(head, t.path);
  const text = f ? f.text : "";
  const firstLine = text.split("\n")[0] || "";
  return {
    name, rows: parseCsv(text, t.cols),
    cols: firstLine ? firstLine.replace(/\r$/, "").split(",").map((h) => h.trim()) : t.cols,
    eol: firstLine.endsWith("\r") ? "\r\n" : "\n",
  };
}

const tableFile = (tb) => ({ path: TABLES[tb.name].path, text: toCsv(tb.rows, tb.cols, tb.eol) });

// One commit with every change. files: {path, text} or {path, base64} to write, {path, sha} to point at a
// blob that's already in the repository, or {path, remove: true}. Returns the blob sha of each written file.
async function commit(head, files, message) {
  const base = await gh(`/git/commits/${head}`);
  const tree = [], shas = {};
  for (const f of files) {
    let sha = f.remove ? null : f.sha;
    if (!f.remove && !sha) {
      const content = f.base64 || Buffer.from(f.text, "utf8").toString("base64");
      sha = (await gh("/git/blobs", { method: "POST", body: JSON.stringify({ content, encoding: "base64" }) })).sha;
    }
    shas[f.path] = sha;
    tree.push({ path: f.path, mode: "100644", type: "blob", sha });
  }
  const t = await gh("/git/trees", { method: "POST", body: JSON.stringify({ base_tree: base.tree.sha, tree }) });
  const c = await gh("/git/commits", { method: "POST", body: JSON.stringify({ message, tree: t.sha, parents: [head] }) });
  await gh(`/git/refs/heads/${BRANCH}`, { method: "PATCH", body: JSON.stringify({ sha: c.sha }) });
  return shas;
}

// Read, change and commit, with a line added to the change log in the same commit. fn(ctx) gets
// {head, tables} and returns {files, message, entry, result}.
// If someone else committed in between (the ref moved), start over once.
async function change(tableNames, fn) {
  for (let attempt = 0; ; attempt++) {
    const head = await headSha();
    const tables = {};
    for (const n of tableNames) tables[n] = await readTable(head, n);
    const out = await fn({ head, tables });
    const logFile = await getFile(head, LOG_PATH);
    const log = logFile ? logFile.text.split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
    const entry = { id: crypto.randomBytes(6).toString("hex"), at: new Date().toISOString(), ...out.entry };
    try {
      await commit(head, [...out.files, { path: LOG_PATH, text: logText([...log, entry]) }], out.message);
      return { ...out.result, entry };
    } catch (e) {
      if (attempt === 0 && (e.status === 422 || e.status === 409)) continue;
      throw e;
    }
  }
}
const logText = (log) => log.slice(-LOG_KEEP).map((e) => JSON.stringify(e)).join("\n") + "\n";

// ---------------------------------------------------------------- row changes, and undoing them
const sameRow = (a, b, cols) => cols.every((k) => (a[k] || "") === (b[k] || ""));

// Apply one change to a table: before → after (before null = add, after null = remove). A removal
// returns where the line was, and an add with `at` puts it back there (so an undo leaves the file as it was).
function applyOp(tb, before, after, cols, at) {
  const t = TABLES[tb.name];
  if (before) {
    const i = tb.rows.findIndex((r) => sameRow(r, before, cols));
    if (i < 0) throw new Bad("That line has changed since this page loaded (or was already removed). Refresh and try again.", 409);
    if (after) tb.rows[i] = after; else tb.rows.splice(i, 1);
    return i;
  } else if (after) {
    if (t.key && tb.rows.some((r) => r[t.key] === after[t.key])) throw new Bad(`There's already a line for ${after[t.key]}. Edit that one instead.`, 409);
    if (at != null && at >= 0 && at < tb.rows.length) tb.rows.splice(at, 0, after); else tb.rows.push(after);
  }
  return null;
}

const live = (r) => r.matched_by !== "removed";

async function saveRow(b) {
  const name = String(b.table || "");
  if (!EDITABLE.includes(name)) throw new Bad("Unknown list.");
  const t = TABLES[name];
  const before = b.before ? Object.fromEntries(t.cols.map((k) => [k, String(b.before[k] == null ? "" : b.before[k])])) : null;
  let after = b.after ? t.check(b.after) : null;
  if (!before && !after) throw new Bad("Nothing to save.");
  let verb = before ? (after ? "Edit" : "Remove") : "Add";
  if (!after && t.soft) after = { ...before, matched_by: "removed" };
  if (before && after && sameRow(before, after, t.cols)) throw new Bad("Nothing changed.");
  const label = t.label(b.after ? after : before);
  return change([name], ({ tables }) => {
    const tb = tables[name];
    const at = applyOp(tb, before, after, tb.cols);
    return {
      files: [tableFile(tb)],
      message: `${verb} ${label} (from the admin page)`,
      entry: { label: `${verb === "Edit" ? "Edited" : verb === "Add" ? "Added" : "Removed"} ${label}`,
               ops: [{ table: name, before, after, ...(after ? {} : { at }) }] },
      result: { ok: true, row: after },
    };
  });
}

async function undo(id) {
  const head = await headSha();
  const logFile = await getFile(head, LOG_PATH);
  const log = logFile ? logFile.text.split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
  const e = log.find((x) => x.id === id);
  if (!e) throw new Bad("That change isn't in the list any more.", 404);
  if (e.undoes) throw new Bad("An undo can't be undone. Make the change again instead.");
  if (log.some((x) => x.undoes === id)) throw new Bad("That change was already undone.", 409);
  const names = [...new Set((e.ops || []).map((o) => o.table))];
  return change(names, ({ tables }) => {
    try {
      for (const o of [...(e.ops || [])].reverse()) applyOp(tables[o.table], o.after, o.before, tables[o.table].cols, o.at);
    } catch (err) {
      if (err.status === 409) throw new Bad("That line was changed again after this, so it can't be undone here. Edit it directly instead (or undo the later change first).", 409);
      throw err;
    }
    const files = names.map((n) => tableFile(tables[n]));
    for (const f of e.files || []) files.push(f.before ? { path: f.path, sha: f.before } : { path: f.path, remove: true });
    return {
      files, message: `Undo: ${e.label} (from the admin page)`,
      entry: { label: `Undid: ${e.label}`, undoes: id },
      result: { ok: true },
    };
  });
}

// ---------------------------------------------------------------- review queues
// An item is linked to a game (a manual line in news_stories.csv or game_film.csv), or dismissed (a line
// marked removed, which the finders skip from then on, so it never comes back), or, for a video the film
// finder already linked, confirmed as it is. Either way it leaves the review list, in the same commit.
const ytId = (u) => ((String(u || "").match(YT_RE) || [""])[0].match(/[A-Za-z0-9_-]{11}$/) || [""])[0];
const QUEUES = {
  story: {
    review: "storyReview", target: "news", same: (a, b) => a.url === b.url, what: "news story",
    row: (item, g) => ({ published: item.published, outlet: item.outlet, kind: item.kind || "article", title: item.title,
                         url: item.url, access: item.outlet === "La Crosse Tribune" ? "subscriber" : "free",
                         game_date: g.date || "", opponent: g.opponent || "", player: g.player || "", matched_by: "" }),
  },
  film: {
    review: "filmReview", target: "film", same: (a, b) => ytId(a.youtube_url) && ytId(a.youtube_url) === ytId(b.youtube_url),
    what: "YouTube video",
    row: (item, g) => ({ date: g.date || "", opponent: g.opponent || "", youtube_url: item.youtube_url, title: item.title, matched_by: "" }),
  },
};

async function queues() {
  const head = await headSha();
  const out = {};
  for (const [kind, q] of Object.entries(QUEUES)) {
    const [rv, tg] = [await readTable(head, q.review), await readTable(head, q.target)];
    out[kind] = rv.rows.flatMap((item) => {
      const have = tg.rows.find((r) => q.same(r, item));
      if (have && (!live(have) || kind === "story")) return []; // dismissed, or a story the finder will drop next run
      return [{ item: Object.fromEntries(TABLES[q.review].cols.map((k) => [k, item[k] || ""])),
                linked: have ? Object.fromEntries(TABLES[q.target].cols.map((k) => [k, have[k] || ""])) : null }];
    });
  }
  return out;
}

async function review(b) {
  const q = QUEUES[b.kind];
  if (!q) throw new Bad("Unknown list.");
  const verdict = oneOf(String(b.verdict || ""), ["link", "dismiss", "ok"], "link, not this, or looks right");
  const item = Object.fromEntries(TABLES[q.review].cols.map((k) => [k, String((b.item || {})[k] == null ? "" : b.item[k])]));
  const t = TABLES[q.target];
  const g = b.game || {};
  return change([q.review, q.target], ({ tables }) => {
    const rv = tables[q.review], tg = tables[q.target];
    const have = tg.rows.find((r) => q.same(r, item)) || null;
    const before = have && Object.fromEntries(tg.cols.map((k) => [k, have[k] || ""]));
    let after, label;
    if (verdict === "link") {
      after = t.check(q.row(item, g));
      label = `Linked ${t.label(after)}`;
    } else if (verdict === "dismiss") {
      after = have ? { ...before, matched_by: "removed" } : { ...q.row(item, {}), matched_by: "removed" };
      label = `Dismissed ${q.what} “${clean(item.title, 200)}”`;
    } else {
      if (!have || !live(have)) throw new Bad("That one isn't linked to a game yet. Choose the game instead.");
      after = null;
      label = `Confirmed ${t.label(before)}`;
    }
    const ops = [{ table: q.review, before: item, after: null }];
    if (after) ops.push({ table: q.target, before, after });
    for (const o of ops) { const at = applyOp(tables[o.table], o.before, o.after, tables[o.table].cols); if (!o.after) o.at = at; }
    const files = [tableFile(rv), ...(after ? [tableFile(tg)] : [])];
    return { files, message: `${label} (from the admin page's review list)`, entry: { label, ops }, result: { ok: true } };
  });
}

// ---------------------------------------------------------------- photos
function slug(s) {
  return String(s).toLowerCase().replace(/['.]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

// git's blob sha for some bytes, so the log can point at a photo file before it's committed
const blobSha = (buf) => crypto.createHash("sha1").update(`blob ${buf.length}\0`).update(buf).digest("hex");

async function addPhoto(b) {
  const kind = b.kind === "team" ? "team" : b.kind === "player" ? "player" : "";
  const season = clean(b.season, 7);
  const player = clean(b.player, 80);
  if (!kind) throw new Bad("Choose team photo or player headshot.");
  if (kind === "team" && !SEASON.test(season)) throw new Bad("Choose a season.");
  if (kind === "player" && !player) throw new Bad("Choose a player.");
  const img = Buffer.from(String(b.image || ""), "base64");
  if (img.length < 100 || img[0] !== 0xff || img[1] !== 0xd8) throw new Bad("That photo didn't come through as a JPEG. Try again.");
  if (img.length > MAX_BYTES) throw new Bad("That photo is too big. Try a smaller one.");
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const image = `${kind}-${kind === "team" ? season : slug(player)}-${stamp}.jpg`;
  const row = { kind, season: kind === "team" ? season : "", player: kind === "player" ? player : "", image,
                caption: clean(b.caption, 300), credit: clean(b.credit, 120) };
  const label = TABLES.photos.label(row);
  return change(["photos"], ({ tables }) => {
    tables.photos.rows.push(row);
    return {
      files: [{ path: PHOTO_DIR + image, base64: img.toString("base64") }, tableFile(tables.photos)],
      message: `Add ${label} (from the admin page)`,
      entry: { label: `Added ${label}`, ops: [{ table: "photos", before: null, after: row }],
               files: [{ path: PHOTO_DIR + image, before: null, after: blobSha(img) }] },
      result: { ok: true, photo: row },
    };
  });
}

async function removePhoto(b) {
  const image = clean(b.image, 200);
  return change(["photos"], async ({ head, tables }) => {
    const found = tables.photos.rows.find((r) => r.image === image);
    if (!found) throw new Bad("That photo is already gone.", 404);
    const local = !/^https?:\/\//.test(image) && !image.includes("/") && !image.includes("..");
    const file = local ? await getFile(head, PHOTO_DIR + image) : null;
    const at = tables.photos.rows.indexOf(found);
    tables.photos.rows.splice(at, 1);
    const label = TABLES.photos.label(found);
    return {
      files: [...(file ? [{ path: PHOTO_DIR + image, remove: true }] : []), tableFile(tables.photos)],
      message: `Remove ${label} (from the admin page)`,
      entry: { label: `Removed ${label}`, ops: [{ table: "photos", before: found, after: null, at }],
               files: file ? [{ path: PHOTO_DIR + image, before: file.sha, after: null }] : [] },
      result: { ok: true },
    };
  });
}

// ---------------------------------------------------------------- the handler
function sameSecret(a, b) {
  const h = (s) => crypto.createHash("sha256").update(String(s)).digest();
  return crypto.timingSafeEqual(h(a), h(b));
}

// A device sign-in key, so the site's own pages can show edit buttons without keeping the password in the browser:
// "<expiry ms>.<HMAC of it, keyed with the password>". It works until it expires, and changing ADMIN_PASSWORD
// cancels every key at once.
const TOKEN_DAYS = 30;
const tokenSig = (exp) => crypto.createHmac("sha256", process.env.ADMIN_PASSWORD).update("admin-edit:" + exp).digest("hex");
const makeToken = (now = Date.now()) => { const exp = now + TOKEN_DAYS * 864e5; return `${exp}.${tokenSig(exp)}`; };
function goodToken(t, now = Date.now()) {
  const m = /^(\d{13})\.([0-9a-f]{64})$/.exec(String(t || ""));
  return !!m && Number(m[1]) > now && sameSecret(m[2], tokenSig(m[1]));
}

const fail = (res, code, error) => res.status(code).json({ error });

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return fail(res, 405, "Use POST.");
  if (!process.env.ADMIN_PASSWORD || !process.env.GITHUB_TOKEN) {
    return fail(res, 503, "The admin page isn't set up yet: add ADMIN_PASSWORD and GITHUB_TOKEN in Vercel (see the README).");
  }
  const byPassword = sameSecret(req.headers["x-admin-password"] || "", process.env.ADMIN_PASSWORD);
  if (!byPassword && !goodToken(req.headers["x-admin-token"])) {
    await new Promise((r) => setTimeout(r, 1500)); // slows down password guessing
    return fail(res, 401, req.headers["x-admin-token"] ? "This device's admin sign-in has run out. Sign in again on the admin page." : "Wrong password.");
  }
  const b = req.body || {};
  try {
    // signing in with the password hands back a device key for the edit buttons on the site's pages
    if (b.action === "check") return res.json(byPassword ? { ok: true, token: makeToken(), days: TOKEN_DAYS } : { ok: true });

    if (b.action === "list") { // photos
      const tb = await readTable(await headSha(), "photos");
      return res.json({ photos: tb.rows });
    }
    if (b.action === "add") return res.json(await addPhoto(b));
    if (b.action === "remove") return res.json(await removePhoto(b));

    if (b.action === "rows") { // the lines of one list that match every field in `where`
      const name = String(b.table || "");
      if (!EDITABLE.includes(name)) throw new Bad("Unknown list.");
      const where = b.where && typeof b.where === "object" ? b.where : {};
      const tb = await readTable(await headSha(), name);
      const rows = tb.rows.filter(live).filter((r) => Object.entries(where).every(([k, v]) => (r[k] || "") === String(v)));
      return res.json({ rows: rows.map((r) => Object.fromEntries(TABLES[name].cols.map((k) => [k, r[k] || ""]))) });
    }
    if (b.action === "save") return res.json(await saveRow(b));

    if (b.action === "log") {
      const f = await getFile(await headSha(), LOG_PATH);
      const log = f ? f.text.split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
      const undone = new Set(log.filter((e) => e.undoes).map((e) => e.undoes));
      return res.json({ entries: log.slice(-60).reverse().map((e) => ({ id: e.id, at: e.at, label: e.label,
        undo: !e.undoes && !undone.has(e.id) && !!(e.ops || e.files) })) });
    }
    if (b.action === "undo") return res.json(await undo(clean(b.id, 20)));

    if (b.action === "queue") return res.json(await queues());
    if (b.action === "review") return res.json(await review(b));

    return fail(res, 400, "Unknown action.");
  } catch (e) {
    if (e.user) return fail(res, e.status, e.message);
    if (e.status === 401 || e.status === 403) {
      return fail(res, 502, "GitHub refused the change. Check that GITHUB_TOKEN is current and has Contents: Read and write on this repository.");
    }
    console.error(e);
    return fail(res, 502, `Couldn't save to GitHub (${e.message}). Nothing was changed. Try again in a minute.`);
  }
};

module.exports.parseCsv = parseCsv;
module.exports.toCsv = toCsv;
module.exports.blobSha = blobSha;
module.exports.slug = slug;
module.exports.makeToken = makeToken;
