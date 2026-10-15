# Record Room

A shareable SoundCloud listening room: paste a playlist, pull records off the shelf, drop them on the turntable, sign the guestbook and leave a track on the record cart. Three photo rooms (pink, white, red), each record sets off its own moment (disco ball, blobs, lasers, dancers…).

Live: https://record-room-rust.vercel.app

## Run locally

```
python3 server.py 5178
```

Serves the page plus a small JSON API (visitors, guestbook doodles, dropped records) stored in `./data`.

## Deploy

Vercel (`vercel deploy --prod`). On Vercel the API is `api/*.js`, backed by Vercel Blob (needs `BLOB_READ_WRITE_TOKEN`, set by connecting the Blob store to the project). `api/page.js` serves `index.html` with per-link preview tags.

## Layout

- `index.html` – the whole room (layout, records, turntable, moments, rooms, sharing)
- `api/` – Vercel functions; `server.py` – the same API for local use
- `assets/` – room plates, props, dancer clips, link-preview images
