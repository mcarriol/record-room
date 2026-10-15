#!/usr/bin/env python3
"""Masked image edit with OpenAI GPT Image 2 (stdlib only). Transparent pixels in the mask are the ones that change.

  python3 tools/edit_image.py "prompt" --image crop.png --mask mask.png --out edited.png --size 1536x1024 --quality low
"""
import argparse, base64, json, os, pathlib, sys, urllib.request, urllib.error, uuid

KEY_FILE = pathlib.Path.home() / ".claude" / "openai.env"
ENDPOINT = "https://api.openai.com/v1/images/edits"


def load_key():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit(f"No OpenAI API key in $OPENAI_API_KEY or {KEY_FILE}")
    return key


def multipart(fields, files):
    b = uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, path in files.items():
        out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{pathlib.Path(path).name}\"\r\nContent-Type: image/png\r\n\r\n".encode()
        out += pathlib.Path(path).read_bytes() + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={b}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask")
    ap.add_argument("--out", default="edited.png")
    ap.add_argument("--model", default="gpt-image-2")
    ap.add_argument("--size", default="1536x1024")
    ap.add_argument("--quality", default="low", choices=["low", "medium", "high", "auto"])
    ap.add_argument("--n", type=int, default=1)
    a = ap.parse_args()
    files = {"image[]": a.image}
    if a.mask:
        files["mask"] = a.mask
    body, ctype = multipart({"model": a.model, "prompt": a.prompt, "size": a.size, "quality": a.quality, "n": str(a.n)}, files)
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Authorization": f"Bearer {load_key()}", "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"OpenAI API error {e.code}: {e.read().decode(errors='replace')}")
    out = pathlib.Path(a.out)
    written = []
    for k, d in enumerate(res.get("data", [])):
        p = out if a.n == 1 else out.with_name(f"{out.stem}-{k + 1}{out.suffix}")
        p.write_bytes(base64.b64decode(d["b64_json"]))
        written.append(str(p))
    print(json.dumps({"written": written, "usage": res.get("usage")}))


if __name__ == "__main__":
    main()
