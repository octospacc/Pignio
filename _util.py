import os
import requests
import urllib.parse
from PIL import Image
from typing import Any, cast
from base64 import b64decode, urlsafe_b64encode
from urllib.parse import urlparse
from io import StringIO
from configparser import ConfigParser
from bs4 import BeautifulSoup
from flask_login import current_user # type: ignore[import-untyped]
from glob import glob
from pathlib import Path
from datetime import datetime
from snowflake import Snowflake # type: ignore[import-untyped]
from hashlib import sha256
from pytesseract import image_to_string, TesseractNotFoundError # type: ignore[import-untyped]
from werkzeug.utils import safe_join
from slugify import slugify
from _pignio import *
from _functions import *

def generate_user_hash(username:str, password:str) -> str:
    return f"{username}:" + urlsafe_b64encode(sha256(password.encode()).digest()).decode()

def walk_items(walk_path:str|None=None) -> list:
    results: dict[str, dict[str, ItemDict|None]] = {}

    walk_root = ITEMS_ROOT
    if walk_path:
        walk_root += f"/{walk_path}"

    for root, dirs, files in os.walk(walk_root):
        rel_path = os.path.relpath(root, ITEMS_ROOT).replace(os.sep, "/")
        if rel_path == ".":
            rel_path = ""

        results[rel_path] = {}

        for file in files:
            #if file.lower().endswith(ITEMS_EXT) or file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["images"]])):
            iid = strip_ext(os.path.join(rel_path, file).replace(os.sep, "/"))
            iid = filename_to_iid(iid)
            results[rel_path][iid] = None

        for iid in results[rel_path]:
            if not (rel_rel_path := "/".join(rel_path.split("/")[:-1])) or (rel_rel_path not in results) or (filename_to_iid(rel_path) not in results[rel_rel_path]):
                results[rel_path][iid] = load_item(iid)

    return [value for inner in results.values() for value in inner.values()]

def count_items() -> int:
    results: dict[str, None] = {}
    for root, dirs, files in os.walk(ITEMS_ROOT):
        rel_path = os.path.relpath(root, ITEMS_ROOT).replace(os.sep, "/")
        for file in files:
            iid = strip_ext(os.path.join(rel_path, file).replace(os.sep, "/"))
            iid = filename_to_iid(iid)
            results[iid] = None
    return len(results)

def walk_collections(username:str) -> dict:
    results: dict[str, list[str]] = {"": []}
    filepath = USERS_ROOT

    # if username:
    filepath = os.path.join(filepath, username)
    data = cast(UserDict, read_metadata(read_textual(filepath + ITEMS_EXT)))
    results[""] = data["items"] if "items" in data else []
    results[""].reverse()

    for root, dirs, files in os.walk(filepath):
        rel_path = os.path.relpath(root, filepath).replace(os.sep, "/")
        if rel_path == ".":
            rel_path = ""
        for file in files:
            cid = rel_path + strip_ext(file)
            data = cast(UserDict, read_metadata(read_textual(os.path.join(filepath, file))))
            results[cid] = data["items"] if "items" in data else []
            results[cid].reverse()

    return results

def datetime_from_snowflake(iid:str) -> datetime:
    return Snowflake.parse(int(iid), snowflake_epoch).datetime

def iid_to_filename(iid:str) -> str:
    if len(iid.split("/")) == 1 and iid.isnumeric():
        date = datetime_from_snowflake(iid)
        iid = f"{date.year}/{date.month}/{iid}"
    return iid

def filename_to_iid(iid:str) -> str:
    toks = iid.split("/")
    if len(toks) == 3 and "".join(toks).isnumeric():
        iid = toks[2]
    return iid

def load_item(iid:str) -> ItemDict|None:
    iid = filename_to_iid(iid)
    filename = iid_to_filename(iid)
    filepath = safe_join(ITEMS_ROOT, filename)
    files = glob(f"{filepath}.*")

    if len(files):
        data: ItemDict = {"id": iid}
        if iid != filename:
            data["datetime"] = str(datetime_from_snowflake(iid)).split(".")[0]

        for file in files:
            if file.lower().endswith(ITEMS_EXT):
                data = data | read_metadata(read_textual(file))
            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["image"]])):
                data["image"] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")
            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["video"]])):
                data["video"] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")

        if safe_str_get(cast(dict, data), "type") == "comment":
            data["datetime"] = str(datetime_from_snowflake(iid.split("/")[-1])).split(".")[0]

        return data
    return None

def store_item(iid:str, data:dict[str, str], files:dict|None=None, ocr:bool=False, *, comment:bool=False) -> bool:
    iid = filename_to_iid(iid)
    existing = load_item(iid)
    
    if existing and not get_item_permissions(existing)["edit"]:
        return False

    filename = split_iid(iid_to_filename(iid))
    filepath = safe_join(ITEMS_ROOT, *filename)
    dirpath = safe_join(ITEMS_ROOT, filename[0])

    if not filepath or not dirpath:
        return False

    mkdirs(dirpath)

    has_media: bool|str = False
    media_path: str|None = None
    existing_media: str|None = None

    extra = {key: data[key] for key in ["provenance"] if key in data}
    data = {key: data[key] for key in ["link", "title", "description", "image", "video", "alttext", "langs", "text"] if key in data}
    if comment:
        data["type"] = "comment"

    if files and len(files):
        file = files["file"]
        if file.seek(0, os.SEEK_END):
            file.seek(0, os.SEEK_SET)
            mime = file.content_type.split("/")
            if is_file_type_allowed(mime[0], (ext := mime[1])):
                file.save(media_path := f"{filepath}.{ext}")
                has_media = mime[0]

    if not has_media and (media := safe_str_get(data, "video") or safe_str_get(data, "image")):
        if media.lower().startswith("data:"):
            kind = media.split("/")[0].split(":")[1].lower()
            ext = media.split(";")[0].split("/")[1].lower()
            if is_file_type_allowed(kind, ext):
                with open(media_path := f"{filepath}.{ext}", "wb") as f:
                    f.write(b64decode(media.split(",")[1]))
                    has_media = kind
        else:
            response = requests.get(media, timeout=5)
            mime = response.headers["Content-Type"].split("/")
            if is_file_type_allowed(mime[0], (ext := mime[1])):
                with open(media_path := f"{filepath}.{ext}", "wb") as f:
                    f.write(response.content)
                    has_media = mime[0]

    if not (existing or has_media or safe_str_get(data, "text")):
        return False

    langs = list(data["langs"] if "langs" in data else [])
    if ocr and (has_media == "image" or (existing_media := safe_str_get(cast(dict, existing), "image"))) and not safe_str_get(data, "alttext"):
        if existing_media:
            media_path = safe_join(ITEMS_ROOT, existing_media)
        if media_path and len(langs) > 0:
            data["alttext"] = ocr_image(media_path, langs)

    if existing:
        if (creator := safe_str_get(cast(dict, existing), "creator")):
            data["creator"] = creator
    else:
        data["creator"] = current_user.username
        if not comment:
            toggle_in_collection(current_user.username, "", iid, True)

    if (provenance := safe_str_get(extra, "provenance")):
        data["systags"] = provenance

    write_textual(filepath + ITEMS_EXT, write_metadata(data))
    return True

def delete_item(item:dict|str, only_media:bool=False) -> int:
    deleted = 0
    if (filepath := safe_join(ITEMS_ROOT, iid_to_filename(ensure_item_id(item)))):
        files = glob(f"{filepath}.*")
        for file in files:
            if not only_media or not file.lower().endswith(ITEMS_EXT):
                os.remove(file)
                deleted += 1
    return deleted

def get_item_permissions(item:ItemDict|str) -> dict[str, bool]:
    item = ensure_item_dict(item)
    creator = safe_str_get(cast(dict, item), "creator")
    return {"view": True, "edit": current_user.is_authenticated and (creator == current_user.username or current_user.is_admin)}

def is_file_type_allowed(kind:str, ext:str) -> bool:
    return ((kind == "image" and ext in EXTENSIONS["image"]) or (kind == "video" and ext in EXTENSIONS["video"]))

def ensure_item_id(data:dict|str) -> str:
    return cast(str, data["id"] if type(data) == dict else data)

def ensure_item_dict(data:ItemDict|str) -> ItemDict:
    return cast(ItemDict, data if type(data) == dict else load_item(cast(str, data)))

def toggle_in_collection(username:str, collection:str, iid:str, status:bool) -> None:
    filepath = get_collection_filepath(username, collection)
    try:
        data = cast(CollectionDict, read_metadata(read_textual(filepath)))
    except FileNotFoundError:
        data = cast(CollectionDict, {})
    if not "items" in data:
        data["items"] = []
    if status:
        data["items"].append(iid)
    else:
        data["items"].remove(iid)
    mkdirs("/".join(filepath.split("/")[:-1]))
    write_textual(filepath, write_metadata(data))

def get_collection_filepath(username:str, collection:str) -> str:
    return f"{USERS_ROOT}/{username}" + (f"/{collection}" if collection else "") + ITEMS_EXT

def read_metadata(text:str) -> MetaDict:
    config = ConfigParser(interpolation=None)
    config.read_string(f"[DEFAULT]\n{text}")
    data = config._defaults # type: ignore[attr-defined]
    for key in ("items", "systags", "langs"):
        if key in data:
            data[key] = wsv_to_list(data[key])
    return data

def write_metadata(data:dict[str, str]|MetaDict) -> str:
    output = StringIO()
    config = ConfigParser(interpolation=None)
    new_data: dict[str, str] = {}
    for key in data:
        if (value := data.get(key)) and key not in ("image", "video", "datetime"):
            if type(value) == str:
                new_data[key] = value
            elif type(value) == list:
                new_data[key] = list_to_wsv(value)
    config["DEFAULT"] = new_data
    config.write(output)
    return "\n".join(output.getvalue().splitlines()[1:]) # remove section header

def slugify_name(text:str):
    return slugify(text)[:64]

def fetch_url_data(url:str) -> dict[str, str|None]:
    response = requests.get(url, timeout=5)
    soup = BeautifulSoup(response.text, "html.parser")

    description = None
    desc_tag = soup.find("meta", attrs={"name": "description"}) or \
               soup.find("meta", attrs={"property": "og:description"})
    if desc_tag and "content" in desc_tag.attrs: # type: ignore[attr-defined]
        description = desc_tag["content"] # type: ignore[index]

    image = None
    img_tag = soup.find("meta", attrs={"property": "og:image"}) or \
              soup.find("meta", attrs={"name": "twitter:image"})
    if img_tag and "content" in img_tag.attrs: # type: ignore[attr-defined]
        image = img_tag["content"] # type: ignore[index]
    
    if image:
        parsed = urlparse(image)
        if not parsed.scheme and not parsed.netloc:
            parsed = urlparse(url)
            image = f"{parsed.scheme}://{parsed.netloc}" + image

    # video = None
    # video_tag = soup.find("meta", attrs={"property": "og:video"})
    # if video_tag and "content" in video_tag.attrs:
    #     video = video_tag["content"]

    return {
        "title": soup_or_default(soup, "meta", {"property": "og:title"}, "content", (soup.title.string if soup.title else None)),
        "description": description,
        "image": image,
        "link": soup_or_default(soup, "link", {"rel": "canonical"}, "href", url),
    }

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default:Any) -> Any:
    elem = soup.find(tag, attrs=attrs)
    return (elem.get(prop) if elem else None) or default # type: ignore[attr-defined]

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

def generate_iid() -> str:
    return str(next(snowflake))

def split_iid(iid:str) -> tuple[str, str]:
    toks = iid.split("/")
    return ("/".join(toks[:-1]), toks[-1])

def strip_ext(filename:str) -> str:
    return os.path.splitext(filename)[0]

def list_to_wsv(data:list[str], sep="\n") -> str:
    return sep.join([urllib.parse.quote(item) for item in data])

def wsv_to_list(data:str) -> list[str]:
    return [urllib.parse.unquote(item) for item in data.strip().replace(" ", "\n").replace("\t", "\n").splitlines()]

def safe_str_get(dikt:dict[str,str]|dict[str,str|None], key:str) -> str:
    return dikt and dikt.get(key) or ""

def mkdirs(*paths:str) -> None:
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)

def read_textual(filepath:str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(filepath, "r") as f:
            return f.read()

def write_textual(filepath:str, content:str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def parse_event(text:str) -> dict[str,str]:
    [base, extra] = text.split(":")
    extra += ","
    [kind, time] = base.split("@")
    event = {"kind": kind, "datetime": str(datetime.fromtimestamp(float(time)))}
    if kind == "pin":
        [item, user, collection] = extra.split(",")[:3]
        event = event | {"item": item, "user": user, "collection": collection}
    else:
        [item, user] = extra.split(",")[:2]
        event = event | {"item": item, "user": user}
    return event
