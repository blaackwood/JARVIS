"""Bounded image loading for teaching-board photo cards.

Only public HTTP(S) URLs are fetched. Every redirect is validated, response
size is capped, and only common raster image formats are accepted. No remote
image is loaded directly by Qt.
"""
from __future__ import annotations

import functools
import json
from urllib.parse import quote, urljoin, urlparse

_MAX_IMAGE_BYTES = 800_000
_MAX_JSON_BYTES = 250_000
_TIMEOUT = 10
_USER_AGENT = "JARVIS-Visual-Card/1.0"


def _get_public(url: str, max_bytes: int, accept: str):
    import requests
    from core.tasks.web import check_url, Refused

    parts=urlparse(str(url or "").strip())
    if parts.username or parts.password:
        raise ValueError("Image URLs containing embedded credentials are refused.")
    current=check_url(url)
    for hop in range(5):
        # DNS/private-address validation is repeated for every destination.
        check_url(current)
        try:
            response=requests.get(
                current,
                headers={"User-Agent":_USER_AGENT,"Accept":accept},
                timeout=_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except Exception as exc:
            raise RuntimeError(f"download failed ({type(exc).__name__})") from None
        if response.status_code in (301,302,303,307,308):
            location=response.headers.get("Location","")
            response.close()
            if not location:
                raise RuntimeError("redirect has no target")
            current=urljoin(current,location)
            parts=urlparse(current)
            if parts.username or parts.password:
                raise ValueError("Image redirect with embedded credentials was refused.")
            current=check_url(current)
            continue
        if response.status_code >= 400:
            response.close()
            raise RuntimeError(f"site answered HTTP {response.status_code}")
        declared=response.headers.get("Content-Length")
        try:
            if declared and int(declared)>max_bytes:
                response.close()
                raise RuntimeError("image is larger than the allowed size")
        except ValueError:
            pass
        chunks=[]; total=0
        try:
            for chunk in response.iter_content(32_768):
                if not chunk: continue
                total+=len(chunk)
                if total>max_bytes:
                    raise RuntimeError("download exceeded the size limit")
                chunks.append(chunk)
            mime=(response.headers.get("Content-Type") or "").split(";",1)[0].strip().lower()
            return b"".join(chunks),mime,current
        finally:
            response.close()
    raise RuntimeError("too many redirects")


@functools.lru_cache(maxsize=12)
def _fetch_query(query: str):
    safe=quote(query.strip().replace(" ","_"),safe="_()-")
    api=f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe}"
    raw,mime,_=_get_public(api,_MAX_JSON_BYTES,"application/json")
    if "json" not in mime:
        raise RuntimeError("Wikipedia did not return a JSON summary")
    try:
        data=json.loads(raw.decode("utf-8"))
    except Exception:
        raise RuntimeError("Wikipedia summary could not be read") from None
    image=(data.get("thumbnail") or {}).get("source") or (data.get("originalimage") or {}).get("source")
    if not image:
        raise RuntimeError(f"Wikipedia has no public image for '{query}'")
    title=str(data.get("title") or query)[:100]
    return _fetch_image(image),title,"Wikimedia / Wikipedia"


@functools.lru_cache(maxsize=12)
def _fetch_image(url: str):
    raw,mime,final=_get_public(url,_MAX_IMAGE_BYTES,"image/png,image/jpeg,image/webp")
    allowed={"image/png","image/jpeg","image/jpg","image/webp"}
    if mime not in allowed:
        raise RuntimeError(f"unsupported image format: {mime or 'unknown'}")
    if not raw.startswith((b"\x89PNG\r\n\x1a\n",b"\xff\xd8\xff",b"RIFF")):
        raise RuntimeError("image bytes do not match an allowed raster format")
    return raw,mime,final


def fetch_photo(query: str = "", url: str = "") -> dict:
    """Return trusted bytes, title and credit suitable for a local Qt image card."""
    if url:
        original=str(url).strip()
        parts=urlparse(original)
        if parts.username or parts.password:
            raise ValueError("Image URLs containing embedded credentials are refused.")
        raw,mime,final=_fetch_image(original)
        credit=urlparse(final).hostname or "image source"
        return {"data":raw,"mime_type":mime,"title":str(query or "Imagem")[:100],"credit":credit}
    q=" ".join(str(query or "").split())[:100]
    if not q:
        raise ValueError("photo requires a Wikipedia query or an image URL")
    (raw,mime,final),title,credit=_fetch_query(q)
    return {"data":raw,"mime_type":mime,"title":title,"credit":credit}


def enrich_photo_item(item: dict) -> dict:
    """Populate one normalized photo mark with bounded, validated local bytes."""
    try:
        photo=fetch_photo(item.get("photo_query",""),item.get("photo_url",""))
        item["photo_data"]=photo["data"]
        item["photo_mime"]=photo["mime_type"]
        item["photo_title"]=photo.get("title") or item.get("photo_query") or "Imagem"
        item["credit"]=item.get("credit") or photo.get("credit") or ""
        item["title"]=item.get("title") or item["photo_title"]
        item["caption"]=item.get("caption") or item["photo_title"]
        item.pop("photo_error",None)
    except Exception as exc:
        item["photo_data"]=b""
        item["photo_error"]=f"Imagem indisponível: {str(exc)[:100]}"
        item["title"]=item.get("title") or item.get("photo_query") or "Fotografia"
    return item
