#!/usr/bin/env python3
"""
iCloud Photo Sync — API endpoint served via /webman/3rdparty/iCloudPhotoSync/api.cgi

Routes requests based on the 'method' parameter to the appropriate handler
in the lib/handlers/ directory.
"""
import json
import os
import sys
import cgi

# The ui/ dir lives at /var/packages/iCloudPhotoSync/target/ui/
# The lib/ dir lives at /var/packages/iCloudPhotoSync/target/lib/
PKG_TARGET = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LIB_DIR = os.path.join(PKG_TARGET, "lib")
VENDOR_DIR = os.path.join(LIB_DIR, "vendor")
sys.path.insert(0, LIB_DIR)
if os.path.isdir(VENDOR_DIR):
    sys.path.insert(0, VENDOR_DIR)

from handlers import status as status_handler
from handlers import auth as auth_handler
from handlers import account as account_handler
from handlers import album as album_handler
from handlers import sync as sync_handler
from handlers import config as config_handler
from handlers import log as log_handler
from handlers import move as move_handler

HANDLERS = {
    "status": status_handler.handle,
    "auth": auth_handler.handle,
    "account": account_handler.handle,
    "album": album_handler.handle,
    "sync": sync_handler.handle,
    "config": config_handler.handle,
    "log": log_handler.handle,
    "move": move_handler.handle,
}


def respond(success, data=None, error=None, total=None):
    result = {"success": success}
    if data is not None:
        result["data"] = data
    if error is not None:
        result["error"] = error
    if total is not None:
        result["total"] = total
    body = json.dumps(result)
    print("Content-Type: application/json")
    print("Content-Length: %d" % len(body))
    print()
    print(body)


def proxy_thumb():
    """Proxy iCloud thumbnail to avoid mixed-content browser block."""
    params = cgi.FieldStorage()
    url = params.getvalue("url", "")
    if not url or "icloud-content.com" not in url:
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("Invalid URL")
        return

    import requests
    try:
        r = requests.get(url, timeout=15)
        ct = r.headers.get("Content-Type", "image/jpeg")
        sys.stdout.buffer.write(("Content-Type: %s\r\n" % ct).encode())
        sys.stdout.buffer.write(("Content-Length: %d\r\n" % len(r.content)).encode())
        sys.stdout.buffer.write(("Cache-Control: public, max-age=86400\r\n").encode())
        sys.stdout.buffer.write(b"\r\n")
        sys.stdout.buffer.write(r.content)
    except Exception:
        print("Status: 502 Bad Gateway")
        print("Content-Type: text/plain")
        print()
        print("Fetch failed")


def _safe_filename(name, fallback="photo.jpg"):
    """Strip path separators and control chars from filename."""
    if not name:
        return fallback
    name = name.replace("\\", "_").replace("/", "_").replace("\r", "").replace("\n", "")
    name = name.strip(". ")
    return name or fallback


def download_photo():
    """Stream a single iCloud asset to the browser as file download."""
    params = cgi.FieldStorage()
    url = params.getvalue("url", "")
    filename = _safe_filename(params.getvalue("filename", ""))
    if not url or "icloud-content.com" not in url:
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("Invalid URL")
        return

    import requests
    try:
        r = requests.get(url, timeout=60, stream=True)
        ct = r.headers.get("Content-Type", "application/octet-stream")
        cl = r.headers.get("Content-Length")
        sys.stdout.buffer.write(("Content-Type: %s\r\n" % ct).encode())
        if cl:
            sys.stdout.buffer.write(("Content-Length: %s\r\n" % cl).encode())
        sys.stdout.buffer.write(
            ('Content-Disposition: attachment; filename="%s"\r\n' % filename).encode()
        )
        sys.stdout.buffer.write(b"\r\n")
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                sys.stdout.buffer.write(chunk)
    except Exception:
        print("Status: 502 Bad Gateway")
        print("Content-Type: text/plain")
        print()
        print("Fetch failed")


def download_zip(raw_body):
    """Stream a ZIP bundle of multiple iCloud assets. Expects JSON POST body:
    {"items": [{"url": "...", "filename": "..."}, ...], "zipname": "photos.zip"}
    """
    import zipfile, io, requests
    try:
        payload = json.loads(raw_body or "{}")
        items = payload.get("items") or []
        zipname = _safe_filename(payload.get("zipname") or "photos.zip", "photos.zip")
    except Exception as e:
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("Invalid payload: %s" % e)
        return

    items = [it for it in items if it.get("url") and "icloud-content.com" in it.get("url", "")]
    if not items:
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("No valid items")
        return

    buf = io.BytesIO()
    used = {}
    failed = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for it in items:
            raw_name = _safe_filename(it.get("filename"))
            n = used.get(raw_name, 0)
            used[raw_name] = n + 1
            name = raw_name
            if n > 0:
                dot = raw_name.rfind(".")
                if dot > 0:
                    name = "%s_%d%s" % (raw_name[:dot], n, raw_name[dot:])
                else:
                    name = "%s_%d" % (raw_name, n)
            try:
                resp = requests.get(it["url"], timeout=60)
                if resp.status_code != 200:
                    failed.append(raw_name)
                    continue
                zf.writestr(name, resp.content)
            except Exception:
                failed.append(raw_name)
                continue

    data = buf.getvalue()
    sys.stdout.buffer.write(b"Content-Type: application/zip\r\n")
    sys.stdout.buffer.write(("Content-Length: %d\r\n" % len(data)).encode())
    sys.stdout.buffer.write(
        ('Content-Disposition: attachment; filename="%s"\r\n' % zipname).encode()
    )
    if failed:
        # Comma-joined filenames; ASCII only (header-safe). Non-ASCII names are
        # escaped to avoid breaking the HTTP response.
        safe_list = ",".join(nm.encode("ascii", "replace").decode("ascii") for nm in failed)
        sys.stdout.buffer.write(("X-Export-Failed: %s\r\n" % safe_list).encode())
    sys.stdout.buffer.write(b"\r\n")
    sys.stdout.buffer.write(data)


def _method_from_query():
    """Parse the 'method' value from QUERY_STRING without touching stdin."""
    import urllib.parse
    qs = os.environ.get("QUERY_STRING", "")
    parsed = urllib.parse.parse_qs(qs)
    vals = parsed.get("method", [])
    return vals[0] if vals else ""


def main():
    # Read the method from QUERY_STRING first so POST bodies (download_zip)
    # aren't accidentally consumed by cgi.FieldStorage before the handler runs.
    method = _method_from_query()

    if method == "thumb":
        proxy_thumb()
        return
    if method == "download":
        download_photo()
        return
    if method == "download_zip":
        length = int(os.environ.get("CONTENT_LENGTH", "0") or 0)
        raw_body = sys.stdin.read(length) if length else ""
        download_zip(raw_body)
        return

    params = cgi.FieldStorage()

    # POST requests put params (incl. method) in the body, not QUERY_STRING.
    if not method:
        method = params.getvalue("method", "") or ""

    handler = HANDLERS.get(method)

    if not handler:
        respond(False, error={"code": 100, "message": "Unknown method: %s" % method})
        return

    try:
        result = handler(params)
        respond(**result)
    except Exception as e:
        respond(False, error={"code": 500, "message": str(e)})


if __name__ == "__main__":
    main()
