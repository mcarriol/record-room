// Shared storage for the Vercel deploy: every record, note and visitor is its own file in Vercel Blob,
// so nothing is ever overwritten and every visitor, in every room, reads the same data.
import { put, list, del, head } from "@vercel/blob";

export const json = (res, code, obj) => { res.setHeader("Cache-Control", "no-store"); res.status(code).json(obj); };
export const clean = (t, n) => String(t ?? "").replace(/[\x00-\x1f\x7f]/g, "").trim().slice(0, n);
export const newId = () => Math.random().toString(16).slice(2, 14).padEnd(12, "0");

export async function listAll(prefix, max = 2000) {
  const out = []; let cursor;
  do { const r = await list({ prefix, cursor, limit: 1000 }); out.push(...r.blobs); cursor = r.hasMore ? r.cursor : undefined; } while (cursor && out.length < max);
  return out;
}
// newest first, each item's JSON fetched in parallel (item files are never rewritten, so the CDN copy is always right)
export async function readItems(prefix, limit) {
  const blobs = (await listAll(prefix)).sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt)).slice(0, limit);
  const items = await Promise.all(blobs.map(b => fetch(b.url).then(r => r.ok ? r.json() : null).catch(() => null)));
  return items.filter(Boolean);
}
export const saveJson = (path, obj) => put(path, JSON.stringify(obj), { access: "public", addRandomSuffix: false, allowOverwrite: true, contentType: "application/json" });
export const exists = async path => { try { await head(path); return true; } catch { return false; } };
export { put, del };
