import { createHash } from "node:crypto";
import { json, clean, listAll, put, exists } from "./_store.js";

export default async function handler(req, res) {
  try {
    if (req.method !== "POST") return json(res, 405, { error: "POST only" });
    const vid = createHash("sha256").update(clean(req.body?.id, 64)).digest("hex").slice(0, 24);
    const path = `visitors/${vid}`;
    if (!(await exists(path))) await put(path, "1", { access: "public", addRandomSuffix: false, allowOverwrite: true, contentType: "text/plain" });
    json(res, 200, { visitors: (await listAll("visitors/", 100000)).length });
  } catch (e) { json(res, 500, { error: "Something went wrong. Try again." }); }
}
