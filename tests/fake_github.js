// A stand-in for the parts of GitHub's API that api/admin.js uses: one branch, a tree of files by path,
// blobs, commits, and a ref that only moves forward (like the real one). install() replaces global fetch.
const fs = require("fs");
const path = require("path");

function install(repoDir, files) {
  let n = 0;
  const id = () => "s" + ++n;
  const blobs = {}, trees = {}, commits = {};
  const seed = {};
  for (const f of files) {
    const p = path.join(repoDir, f);
    if (!fs.existsSync(p)) continue;
    const b = id();
    blobs[b] = fs.readFileSync(p).toString("base64");
    seed[f] = b;
  }
  let head = id();
  trees.t0 = seed;
  commits[head] = { tree: "t0", message: "start" };
  const calls = [];
  global.fetch = async (url, opts = {}) => {
    const u = new URL(url), p = u.pathname.replace(/^\/repos\/[^/]+\/[^/]+/, ""), m = opts.method || "GET";
    const body = opts.body ? JSON.parse(opts.body) : null;
    const ok = (j, status = 200) => ({ ok: status < 300, status, json: async () => j });
    calls.push(`${m} ${p}`);
    if (opts.headers.Authorization !== `Bearer ${process.env.GITHUB_TOKEN}`) return ok({ message: "Bad credentials" }, 401);
    if (m === "GET" && p.startsWith("/git/ref/heads/")) return ok({ object: { sha: head } });
    if (m === "GET" && p.startsWith("/git/commits/")) return ok({ tree: { sha: commits[p.split("/").pop()].tree } });
    if (m === "GET" && p.startsWith("/git/blobs/")) return ok({ content: blobs[p.split("/").pop()] });
    if (m === "GET" && p.startsWith("/contents/")) {
      const ref = u.searchParams.get("ref") || head;
      const b = trees[commits[ref].tree][decodeURIComponent(p.slice(10))];
      return b ? ok({ content: blobs[b], sha: b }) : ok({ message: "Not Found" }, 404);
    }
    if (m === "POST" && p === "/git/blobs") { const s = id(); blobs[s] = body.content; return ok({ sha: s }, 201); }
    if (m === "POST" && p === "/git/trees") {
      const t = { ...trees[body.base_tree] };
      for (const e of body.tree) {
        if (e.sha === null) delete t[e.path];
        else if (!(e.sha in blobs)) return ok({ message: "bad sha" }, 422);
        else t[e.path] = e.sha;
      }
      const s = id(); trees[s] = t; return ok({ sha: s }, 201);
    }
    if (m === "POST" && p === "/git/commits") {
      const s = id(); commits[s] = { tree: body.tree, message: body.message, parents: body.parents }; return ok({ sha: s }, 201);
    }
    if (m === "PATCH" && p.startsWith("/git/refs/heads/")) {
      if (commits[body.sha].parents[0] !== head) return ok({ message: "Update is not a fast forward" }, 422);
      head = body.sha; return ok({ object: { sha: head } });
    }
    return ok({ message: `unhandled ${m} ${p}` }, 500);
  };
  return {
    calls,
    text: (f) => { const b = trees[commits[head].tree][f]; return b ? Buffer.from(blobs[b], "base64").toString() : null; },
    files: () => Object.keys(trees[commits[head].tree]),
    message: () => commits[head].message,
    commits: () => Object.keys(commits).length - 1,
    // someone else commits in between (the news bot, say): the next PATCH from an older head is refused
    otherCommit: (f, text) => {
      const b = id(); blobs[b] = Buffer.from(text).toString("base64");
      const t = id(); trees[t] = { ...trees[commits[head].tree], [f]: b };
      const c = id(); commits[c] = { tree: t, message: "bot", parents: [head] }; head = c;
    },
  };
}

module.exports = { install };
