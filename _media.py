import os
import requests
import ffmpeg # type: ignore[import-untyped]
from PIL import Image, ImageFile
from io import BytesIO
from flask import send_file
from pytesseract import image_to_string, TesseractError, TesseractNotFoundError # type: ignore[import-untyped]
from base64 import b64decode
from typing import Literal, Callable, cast
from werkzeug.utils import safe_join
from _pignio import ItemDict, ITEMS_ROOT, ITEMS_EXT, MEDIA_TYPES, PROXY_ROOT, EXTENSIONS, Config
from _util import read_textual, write_textual, mkfiledir, parse_absolute_url

def check_file_supported(filename:str) -> bool:
    return check_file_is_meta(filename) or bool(check_file_is_content(filename))

def check_file_is_meta(filename:str) -> bool:
    return filename.lower().endswith(ITEMS_EXT)

def check_file_is_content(filename:str) -> str|Literal[False]:
    for kind in MEDIA_TYPES:
        if filename.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS[kind]])):
            return kind
    return False

def get_http_mime(response) -> tuple[str, str]:
    return response.headers["Content-Type"].lower().split(";")[0].split("/")

def store_url_file(url:str, filepath:str) -> tuple[str, str]|Literal[False]|None:
    if (urllow := url.lower()).startswith("data:") and "/" in urllow:
        [kind, ext] = urllow.split(",")[0].split(";")[0].split(":")[1].split("/")
        if (newext := get_allowed_filetype(kind, ext)):
            with open(media_path := f"{filepath}.{newext}", "wb") as f:
                f.write(b64decode(url.split(",")[1]))
                return (kind, media_path)
    elif urllow.startswith(("http://", "https://", "//")):
        response = requests.get(url, timeout=15)
        [kind, ext] = get_http_mime(response)
        if (newext := get_allowed_filetype(kind, ext)):
            with open(media_path := f"{filepath}.{newext}", "wb") as f:
                f.write(response.content)
                return (kind, media_path)
    else:
        return None
    return False

def get_allowed_filetype(kind:str, ext:str) -> str|Literal[False]:
    for testkind in MEDIA_TYPES:
        if ext in EXTENSIONS[testkind]:
            return ext
    extra = EXTENSIONS.get(f"{kind}.extra")
    return extra and cast(dict, extra).get(ext) or False

def resolve_media(item:ItemDict, field:str):
    media = item.get(field)
    if not media:
        return None

    # locale
    local = safe_join(ITEMS_ROOT, str(media))
    if local and os.path.exists(local):
        return local

    # remoto
    url = parse_absolute_url(str(media))
    if not url:
        return None

    data, mime = fetch_proxy_media(item["id"], url)
    return BytesIO(data), mime

def fetch_proxy_media(iid:str, url:str, n:int=0) -> tuple[bytes, str]:
    if n:
        iid += f"/{n}"
    metapath = os.path.join(PROXY_ROOT, f"{iid}.inf")

    if Config.PROXY_CACHE and os.path.exists(metapath):
        kind, ext = read_textual(metapath).split("/")
        path = os.path.join(PROXY_ROOT, f"{iid}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read(), f"{kind}/{ext}"

    resp = requests.get(url, timeout=10)
    kind, ext = get_http_mime(resp)
    mime = f"{kind}/{ext}"

    if Config.PROXY_CACHE:
        path = os.path.join(PROXY_ROOT, f"{iid}.{ext}")
        mkfiledir(path)
        with open(path, "wb") as f:
            f.write(resp.content)
        write_textual(metapath, mime, False)

    return resp.content, mime

def build_video_thumb(video_path: str) -> bytes:
    streams = (
        ffmpeg
        .input(video_path, t=Config.VIDEO_THUMB_DURATION)
        .video.filter("fps", Config.VIDEO_THUMB_FPS)
        .filter("scale", Config.VIDEO_THUMB_WIDTH, -1, flags="lanczos")
        .filter_multi_output("split")
    )
    gif = ffmpeg.filter(
        [streams[1], streams[0].filter("palettegen")],
        "paletteuse",
        dither="none",
    )
    return ffmpeg.output(gif, "pipe:1", format="gif").run(capture_stdout=True)[0]

def build_image_thumb(image_path: str) -> bytes:
    pil = Image.open(image_path)
    if pil.width > Config.THUMB_WIDTH:
        pil = pil.resize(
            (Config.THUMB_WIDTH, int(pil.height * Config.THUMB_WIDTH / pil.width)),
            Image.LANCZOS, # type: ignore[attr-defined]
        ) # type: ignore[assignment]
    pil = pil.convert("RGBA") # type: ignore[assignment]
    ImageFile.MAXBLOCK = pil.size[0] * pil.size[1]

    buf = BytesIO()
    pil.save(
        buf,
        format=Config.THUMB_TYPE,
        quality=Config.THUMB_QUALITY,
        optimize=True,
        progressive=True,
    )
    return buf.getvalue()

def serve_or_build(
    path: str,
    cachable: bool,
    builder: Callable[[], bytes],
    mimetype: str | None = None,
):
    if cachable and os.path.exists(path):
        return send_file(path, mimetype=mimetype)

    data = builder()

    if cachable:
        mkfiledir(path)
        with open(path, "wb") as f:
            f.write(data)

    return send_file(
        BytesIO(data),
        mimetype=mimetype,
        download_name=os.path.basename(path),
    )

def ocr_image(filepath:str, langs:list[str]) -> str:
    text = ""
    try:
        image = Image.open(filepath)
        width, height = image.size
        monochrome = image.resize((width * 2, height * 2), resample=Image.Resampling.LANCZOS).convert("L").point(lambda x: 0 if x < 140 else 255, "1")
        text = image_to_string(monochrome, lang=("+".join(langs) if len(langs) > 0 else None))
    except (TesseractNotFoundError, TesseractError):
        pass
    return text

def check_ffmpeg_available():
    try:
        ffmpeg.probe("")
    except FileNotFoundError:
        return False
    except ffmpeg.Error:
        pass
    return True
