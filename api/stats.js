import { json, listAll } from "./_store.js";
export default async function handler(req, res) {
  try { json(res, 200, { visitors: (await listAll("visitors/", 100000)).length }); }
  catch { json(res, 500, { error: "Something went wrong." }); }
}
