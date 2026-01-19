import os
import requests
import ffmpeg # type: ignore[import-untyped]
from PIL import Image
from pytesseract import image_to_string, TesseractNotFoundError # type: ignore[import-untyped]
from base64 import b64decode
from typing import Literal, cast
from _pignio import ITEMS_EXT, MEDIA_TYPES, PROXY_ROOT, EXTENSIONS, Config
from _util import read_textual, write_textual, mkfiledir

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

def fetch_proxy_media(iid: str, url: str) -> tuple[bytes, str]:
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

# TODO: handle and pass language not found error
def ocr_image(filepath:str, langs:list[str]) -> str:
    text = ""
    try:
        image = Image.open(filepath)
        width, height = image.size
        monochrome = image.resize((width * 2, height * 2), resample=Image.Resampling.LANCZOS).convert("L").point(lambda x: 0 if x < 140 else 255, "1")
        text = image_to_string(monochrome, lang=("+".join(langs) if len(langs) > 0 else None))
    except TesseractNotFoundError:
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
