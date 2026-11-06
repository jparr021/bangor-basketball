// The admin page's server side (api/admin.js), against a fake GitHub seeded with the real overrides/ files.
// Run:  node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { install } = require("./fake_github");

const ROOT = path.join(__dirname, "..");
const FILES = ["photos.csv", "news_stories.csv", "game_film.csv", "hudl_video.csv", "rosters.csv", "season_history.csv",
               "grad_years.csv"].map((f) => "overrides/" + f).concat(["data/stories_review.csv", "data/film_review.csv"]);
process.env.ADMIN_PASSWORD = "test-password";
process.env.GITHUB_TOKEN = "test-token";
const admin = require("../api/admin.js");

function call(body, password = "test-password") {
  return new Promise((resolve) => {
    const res = {
      statusCode: 200, headers: {},
      setHeader(k, v) { this.headers[k] = v; },
      status(c) { this.statusCode = c; return this; },
      json(j) { resolve({ status: this.statusCode, body: j }); },
    };
    admin({ method: "POST", headers: { "x-admin-password": password }, body }, res);
  });
}
const original = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const lastLog = async () => (await call({ action: "log" })).body.entries[0];

test("CSV files come back byte for byte after a read and write", () => {
  for (const f of FILES) {
    const text = original(f);
    const cols = text.split("\n")[0].replace(/\r$/, "").split(",");
    const eol = text.includes("\r\n") ? "\r\n" : "\n";
    assert.equal(admin.toCsv(admin.parseCsv(text), cols, eol), text, f);
  }
});

test("a wrong password is refused", async () => {
  install(ROOT, FILES);
  const r = await call({ action: "check" }, "nope");
  assert.equal(r.status, 401);
});

test("a game link can be added, edited, removed and undone", async () => {
  const gh = install(ROOT, FILES);
  const story = { published: "2025-12-03", outlet: "WXOW 19", kind: "article", title: "Arcadia edges Bangor",
                  url: "https://www.wxow.com/sports/x", access: "free", game_date: "2025-12-02", opponent: "Arcadia",
                  player: "", matched_by: "manual" };
  let r = await call({ action: "save", table: "news", before: null, after: story });
  assert.equal(r.status, 200);
  assert.match(gh.message(), /^Add news story “Arcadia edges Bangor”/);
  r = await call({ action: "rows", table: "news", where: { game_date: "2025-12-02" } });
  assert.deepEqual(r.body.rows.map((x) => x.title), ["Arcadia edges Bangor"]);

  const edited = { ...story, title: "Arcadia edges Bangor in the opener" };
  assert.equal((await call({ action: "save", table: "news", before: story, after: edited })).status, 200);
  // editing from a stale copy is refused, not applied twice
  assert.equal((await call({ action: "save", table: "news", before: story, after: edited })).status, 409);

  // removing keeps the line, marked removed, so the story finder doesn't add it back
  assert.equal((await call({ action: "save", table: "news", before: edited, after: null })).status, 200);
  assert.equal((await call({ action: "rows", table: "news", where: { game_date: "2025-12-02" } })).body.rows.length, 0);
  assert.match(gh.text("overrides/news_stories.csv"), /in the opener,https:\/\/www\.wxow\.com\/sports\/x,free,2025-12-02,Arcadia,,removed\r\n/);

  // undo everything, newest first: the file is exactly as it started
  for (const e of (await call({ action: "log" })).body.entries) {
    if (e.undo) assert.equal((await call({ action: "undo", id: e.id })).status, 200, e.label);
  }
  assert.equal(gh.text("overrides/news_stories.csv"), original("overrides/news_stories.csv"));
  // an undo can't be undone, and a change can't be undone twice
  const entries = (await call({ action: "log" })).body.entries;
  assert.ok(entries.every((e) => !e.undo));
});

test("bad input is refused with a reason", async () => {
  install(ROOT, FILES);
  const cases = [
    [{ table: "film", after: { date: "2025-12-02", opponent: "Arcadia", youtube_url: "https://example.com/x" } }, /YouTube/],
    [{ table: "hudl", after: { date: "2025-12-02", opponent: "Arcadia", kind: "full", access: "free", url: "https://hudl.com.evil.example/x" } }, /Hudl/],
    [{ table: "news", after: { published: "2025-12-03", outlet: "X", kind: "article", title: "T", url: "javascript:alert(1)", access: "free", game_date: "2025-12-02", opponent: "A" } }, /https/],
    [{ table: "roster", after: { season: "1999-00", name: "Test Player", grade: "13" } }, /Grade/],
    [{ table: "season", after: { season: "2025-26", w: "1" } }, /already a line/],
    [{ table: "grad", after: { name: "Test Player", grad_year: "20x5" } }, /year/],
    [{ table: "nope", after: {} }, /Unknown list/],
  ];
  for (const [b, re] of cases) {
    const r = await call({ action: "save", before: null, ...b });
    assert.ok(r.status === 400 || r.status === 409, `${b.table}: ${r.status}`);
    assert.match(r.body.error, re);
  }
});

test("a change made while someone else committed is retried, not lost", async () => {
  const gh = install(ROOT, FILES);
  const rp = { season: "1999-00", number: "44", name: "Retry Test", position: "", height: "", grade: "", source: "" };
  let bumped = false;
  const realFetch = global.fetch;
  global.fetch = async (url, opts = {}) => {
    if (!bumped && (opts.method || "GET") === "PATCH") { bumped = true; gh.otherCommit("overrides/hudl_video.csv", "bot change\n"); }
    return realFetch(url, opts);
  };
  assert.equal((await call({ action: "save", table: "roster", before: null, after: rp })).status, 200);
  assert.match(gh.text("overrides/rosters.csv"), /Retry Test/);
  assert.equal(gh.text("overrides/hudl_video.csv"), "bot change\n"); // the other commit survives
});

test("undo refuses when the line was changed again afterward", async () => {
  install(ROOT, FILES);
  const rp = { season: "1999-00", number: "45", name: "Conflict Test", position: "", height: "", grade: "", source: "" };
  await call({ action: "save", table: "roster", before: null, after: rp });
  const added = await lastLog();
  await call({ action: "save", table: "roster", before: rp, after: { ...rp, number: "46" } });
  const r = await call({ action: "undo", id: added.id });
  assert.equal(r.status, 409);
  assert.match(r.body.error, /changed again/);
});

test("photos: add, remove, and undo the removal brings the file back", async () => {
  const gh = install(ROOT, FILES);
  // a tiny but real JPEG header is enough for the check
  const jpg = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(200, 1)]).toString("base64");
  let r = await call({ action: "add", kind: "team", season: "1925-26", image: jpg, caption: "", credit: "" });
  assert.equal(r.status, 200);
  const img = r.body.photo.image, file = "overrides/photos/" + img;
  assert.ok(gh.files().includes(file));
  assert.equal((await call({ action: "remove", image: img })).status, 200);
  assert.ok(!gh.files().includes(file));
  assert.equal((await call({ action: "undo", id: (await lastLog()).id })).status, 200);
  assert.ok(gh.files().includes(file));
  assert.equal(gh.text(file), Buffer.from(jpg, "base64").toString());
  assert.equal((await call({ action: "add", kind: "team", season: "1925-26", image: "bm90IGEganBlZw==" })).status, 400);
});

test("class years: one correction per player, saved, edited, removed", async () => {
  const gh = install(ROOT, FILES);
  const row = { name: "Hayden Massman", grad_year: "2026", note: "test" };
  assert.equal((await call({ action: "save", table: "grad", before: null, after: row })).status, 200);
  assert.match(gh.text("overrides/grad_years.csv"), /Hayden Massman,2026,test\n$/);
  // a second line for the same player is refused: edit the first one instead
  assert.equal((await call({ action: "save", table: "grad", before: null, after: { ...row, grad_year: "2027" } })).status, 409);
  assert.equal((await call({ action: "save", table: "grad", before: row, after: { ...row, grad_year: "2027" } })).status, 200);
  assert.equal((await call({ action: "save", table: "grad", before: { ...row, grad_year: "2027" }, after: null })).status, 200);
  assert.equal(gh.text("overrides/grad_years.csv"), original("overrides/grad_years.csv"));
});

test("review: link a story, dismiss one, and undo puts both back", async () => {
  const gh = install(ROOT, FILES);
  let q = (await call({ action: "queue" })).body;
  assert.ok(q.story.length > 10, "stories to review");
  const [a, b] = q.story;
  const g = { date: "2025-12-02", opponent: "Arcadia" };
  let r = await call({ action: "review", kind: "story", item: a.item, verdict: "link", game: g });
  assert.equal(r.status, 200, r.body.error);
  const news = admin.parseCsv(gh.text("overrides/news_stories.csv"));
  const linked = news.find((x) => x.url === a.item.url);
  assert.equal(linked.game_date, "2025-12-02");
  assert.equal(linked.matched_by, "manual");
  assert.equal(linked.access, a.item.outlet === "La Crosse Tribune" ? "subscriber" : "free");

  assert.equal((await call({ action: "review", kind: "story", item: b.item, verdict: "dismiss" })).status, 200);
  assert.equal(admin.parseCsv(gh.text("overrides/news_stories.csv")).find((x) => x.url === b.item.url).matched_by, "removed");
  // both are gone from the list, and the review file lost exactly those two lines
  q = (await call({ action: "queue" })).body;
  assert.ok(!q.story.some((x) => x.item.url === a.item.url || x.item.url === b.item.url));
  assert.equal(admin.parseCsv(gh.text("data/stories_review.csv")).length, admin.parseCsv(original("data/stories_review.csv")).length - 2);
  // the same item twice is refused (someone else already handled it)
  assert.equal((await call({ action: "review", kind: "story", item: b.item, verdict: "dismiss" })).status, 409);

  for (const e of (await call({ action: "log" })).body.entries) if (e.undo) await call({ action: "undo", id: e.id });
  assert.equal(gh.text("overrides/news_stories.csv"), original("overrides/news_stories.csv"));
  assert.equal(gh.text("data/stories_review.csv"), original("data/stories_review.csv"));
});

test("review: a story about a player needs no game", async () => {
  const gh = install(ROOT, FILES);
  const item = (await call({ action: "queue" })).body.story[0].item;
  assert.equal((await call({ action: "review", kind: "story", item, verdict: "link", game: { player: "Hayden Massman" } })).status, 200);
  const row = admin.parseCsv(gh.text("overrides/news_stories.csv")).find((x) => x.url === item.url);
  assert.equal(row.player, "Hayden Massman");
  assert.equal(row.game_date, "");
  assert.equal((await call({ action: "review", kind: "story", item: (await call({ action: "queue" })).body.story[0].item,
                              verdict: "link", game: {} })).status, 400);
});

test("review: film already linked can be confirmed, moved or dismissed", async () => {
  const gh = install(ROOT, FILES);
  const vid = "https://www.youtube.com/watch?v=abcdefghijk";
  // what the film finder leaves when a title's date is a day off: linked, and in the review list
  gh.otherCommit("overrides/game_film.csv", original("overrides/game_film.csv") + `2025-12-02,Arcadia,${vid},Bangor vs Arcadia 12-3-25,"opponent, title date off by a day or two"\n`);
  gh.otherCommit("data/film_review.csv", "title,youtube_url,upload_date,reason,candidates\n" +
    `Bangor vs Arcadia 12-3-25,${vid},20251204,"matched, but off",2025-12-02 Arcadia\nRandom clip,https://youtu.be/zzzzzzzzzzz,,no date or opponent in title,\n`);
  const q = (await call({ action: "queue" })).body.film;
  assert.equal(q.length, 2);
  assert.equal(q[0].linked.date, "2025-12-02");
  assert.equal(q[1].linked, null);
  assert.equal((await call({ action: "review", kind: "film", item: q[1].item, verdict: "ok" })).status, 400); // nothing to confirm
  assert.equal((await call({ action: "review", kind: "film", item: q[0].item, verdict: "ok" })).status, 200);
  assert.match(gh.text("overrides/game_film.csv"), /abcdefghijk,Bangor vs Arcadia 12-3-25,"opponent, title date off/); // unchanged
  assert.equal((await call({ action: "review", kind: "film", item: q[1].item, verdict: "dismiss" })).status, 200);
  assert.match(gh.text("overrides/game_film.csv"), /^,,https:\/\/youtu\.be\/zzzzzzzzzzz,Random clip,removed$/m);
  assert.deepEqual((await call({ action: "queue" })).body.film, []);
  assert.equal(gh.text("data/film_review.csv"), "title,youtube_url,upload_date,reason,candidates\n");
});
