import { json, clean, newId, readItems, saveJson, exists } from "./_store.js";

async function soundcloudTrack(url) {
  let host = "";
  try { host = new URL(url).host.toLowerCase(); } catch {}
  if (!["soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"].includes(host)) throw new Error("That isn't a SoundCloud link.");
  const r = await fetch("https://soundcloud.com/oembed?format=json&url=" + encodeURIComponent(url)).catch(() => null);
  if (!r || !r.ok) throw new Error("SoundCloud couldn't find that track. Check the link is public.");
  const o = await r.json();
  const src = (o.html || "").match(/src="([^"]+)"/);
  const inner = src ? new URL(src[1].replace(/&amp;/g, "&")).searchParams.get("url") || "" : "";
  if (inner.includes("/playlists/")) throw new Error("The cart takes single tracks. Paste a link to one song, not a playlist.");
  if (!inner.includes("/tracks/")) throw new Error("SoundCloud won't embed that track.");
  const m = (o.title || "").match(/^(.*) by (.*)$/);
  return { api: inner, title: (m ? m[1] : o.title || "").slice(0, 120), artist: (o.author_name || (m && m[2]) || "").slice(0, 80), artwork: o.thumbnail_url || "" };
}

export default async function handler(req, res) {
  try {
    if (req.method === "GET") return json(res, 200, { gifts: await readItems("gifts/", 200) });
    if (req.method !== "POST") return json(res, 405, { error: "Not allowed." });
    const url = clean(req.body?.url, 400), from = clean(req.body?.from, 24) || "A visitor";
    let meta;
    try { meta = await soundcloudTrack(url); } catch (e) { return json(res, 400, { error: e.message }); }
    const trackId = (meta.api.match(/tracks\/(\d+)/) || [])[1] || newId();
    const path = `gifts/${trackId}.json`;
    if (await exists(path)) return json(res, 409, { error: "That record is already on the shelf." });
    const item = { id: newId(), url, from, at: Math.floor(Date.now() / 1000), ...meta };
    await saveJson(path, item);
    json(res, 201, { gift: item });
  } catch (e) { json(res, 500, { error: "Something went wrong. Try again." }); }
}
