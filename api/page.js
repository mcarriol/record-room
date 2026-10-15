// The room page, with a link preview (title, description, room picture) that names the shared playlist.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const PAGE = readFileSync(join(process.cwd(), "index.html"), "utf8");
const ROOMS = ["pink", "white", "red"];
const esc = v => String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function playlistMeta(url) {
  try {
    const r = await fetch("https://soundcloud.com/oembed?format=json&url=" + encodeURIComponent(url), { signal: AbortSignal.timeout(3500) });
    if (!r.ok) return {};
    const o = await r.json(), m = (o.title || "").match(/^(.*) by (.*)$/);
    return { title: (m ? m[1] : o.title || "").slice(0, 120), by: (o.author_name || (m && m[2]) || "").slice(0, 80) };
  } catch { return {}; }
}

export default async function handler(req, res) {
  const q = new URL(req.url, "http://x").searchParams;
  const room = ROOMS.includes(q.get("room")) ? q.get("room") : "pink";
  const lst = q.get("list") || "";
  const url = /^[\w\-./]{1,200}$/.test(lst) ? "https://soundcloud.com/" + lst : q.get("url") || "";
  const { title = "", by = "" } = /^https:\/\/(www\.|m\.|on\.)?soundcloud\.com\//.test(url) ? await playlistMeta(url) : {};
  const head = title ? `${title} · Record Room` : "Record Room";
  const desc = (title && by ? `${title}, selected by ${by}. ` : title ? `${title}. ` : "") +
    "Pull a record off the shelf, drop it on the turntable, sign the guestbook and leave a record for the next visitor.";
  const base = `https://${req.headers["x-forwarded-host"] || req.headers.host}`;
  const img = `${base}/assets/og-${room}.jpg`;
  const tags = [
    `<meta name="description" content="${esc(desc)}">`, `<meta property="og:type" content="website">`, `<meta property="og:site_name" content="Record Room">`,
    `<meta property="og:title" content="${esc(head)}">`, `<meta property="og:description" content="${esc(desc)}">`,
    `<meta property="og:image" content="${esc(img)}">`, `<meta property="og:image:width" content="1200">`, `<meta property="og:image:height" content="630">`,
    `<meta property="og:url" content="${esc(base + (req.headers["x-vercel-original-url"] || req.url))}">`,
    `<meta name="twitter:card" content="summary_large_image">`, `<meta name="twitter:title" content="${esc(head)}">`,
    `<meta name="twitter:description" content="${esc(desc)}">`, `<meta name="twitter:image" content="${esc(img)}">`,
  ].join("\n");
  const html = PAGE.replace("<title>Record Room</title>", `<title>${esc(head)}</title>`).replace("<!--OG-->", tags);
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "public, max-age=0, s-maxage=300, stale-while-revalidate=3600");
  res.status(200).send(html);
}
