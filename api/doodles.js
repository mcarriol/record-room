import { json, clean, newId, readItems, saveJson, put } from "./_store.js";
const MAX_BYTES = 350_000;

export default async function handler(req, res) {
  try {
    if (req.method === "GET") return json(res, 200, { doodles: await readItems("doodles/meta/", 120) });
    if (req.method !== "POST") return json(res, 405, { error: "Not allowed." });
    const b = req.body || {};
    const img = String(b.image || "");
    if (!img.startsWith("data:image/png;base64,")) return json(res, 400, { error: "The drawing didn't come through. Try again." });
    const raw = Buffer.from(img.split(",", 2)[1], "base64");
    if (raw.length > MAX_BYTES || raw.subarray(0, 4).toString("hex") !== "89504e47") return json(res, 400, { error: "That drawing is too large." });
    const id = newId();
    const png = await put(`doodles/img/${id}.png`, raw, { access: "public", addRandomSuffix: false, contentType: "image/png" });
    const item = { id, name: clean(b.name, 24) || "Anonymous", note: clean(b.note, 90), img: png.url, at: Math.floor(Date.now() / 1000) };
    await saveJson(`doodles/meta/${Date.now()}-${id}.json`, item);
    json(res, 201, { doodle: item });
  } catch (e) { json(res, 500, { error: "Something went wrong. Try again." }); }
}
