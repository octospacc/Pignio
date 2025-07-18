import os
import requests
from typing import Any, cast
from base64 import b64decode, urlsafe_b64encode
from io import StringIO
from configparser import ConfigParser
from bs4 import BeautifulSoup
from flask_login import current_user # type: ignore[import-untyped]
from glob import glob
from pathlib import Path
from snowflake import Snowflake # type: ignore[import-untyped]
from hashlib import sha256
from _pignio import *

def generate_user_hash(username:str, password:str) -> str:
    return f"{username}:" + urlsafe_b64encode(sha256(password.encode()).digest()).decode()

def walk_items():
    results = {}

    for root, dirs, files in os.walk(ITEMS_ROOT):
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
            results[rel_path][iid] = load_item(iid)

    return [value for inner in results.values() for value in inner.values()]

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
    if len(iid.split("/")) == 1:
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
    filepath = os.path.join(ITEMS_ROOT, filename)
    files = glob(f"{filepath}.*")

    if len(files):
        data: ItemDict = {"id": iid}
        if iid != filename:
            data["datetime"] = str(datetime_from_snowflake(iid))

        for file in files:
            if file.lower().endswith(ITEMS_EXT):
                data = data | read_metadata(read_textual(file))
            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["image"]])):
                data["image"] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")
            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["video"]])):
                data["video"] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")

        return data
    return None

def store_item(iid:str, data:dict[str, str], files:dict|None=None) -> bool:
    iid = filename_to_iid(iid)
    existing = load_item(iid)
    filename = split_iid(iid_to_filename(iid))
    filepath = os.path.join(ITEMS_ROOT, *filename)
    mkdirs(os.path.join(ITEMS_ROOT, filename[0]))
    has_media = False
    extra = {key: data[key] for key in ["provenance"] if key in data}
    data = {key: data[key] for key in ["link", "title", "description", "image", "text"] if key in data}

    if files and len(files):
        file = files["file"]
        if file.seek(0, os.SEEK_END):
            file.seek(0, os.SEEK_SET)
            mime = file.content_type.split("/")
            if is_file_type_allowed(mime[0], (ext := mime[1])):
                file.save(f"{filepath}.{ext}")
                has_media = True

    if not has_media and "image" in data and data["image"]:
        if data["image"].lower().startswith("data:image/"):
            ext = data["image"].lower().split(";")[0].split("/")[1]
            if is_file_type_allowed("image", ext):
                with open(f"{filepath}.{ext}", "wb") as f:
                    f.write(b64decode(data["image"].split(",")[1]))
                    has_media = True
        else:
            response = requests.get(data["image"], timeout=5)
            mime = response.headers["Content-Type"].split("/")
            if is_file_type_allowed(mime[0], (ext := mime[1])):
                with open(f"{filepath}.{ext}", "wb") as f:
                    f.write(response.content)
                    has_media = True

    if not (existing or has_media or safe_str_get(data, "text")):
        return False

    if existing:
        if (creator := safe_str_get(cast(dict, existing), "creator")):
            data["creator"] = creator
    else:
        data["creator"] = current_user.username
        items = current_user.data["items"] if "items" in current_user.data else []
        items.append(iid)
        current_user.data["items"] = items
        write_textual(current_user.filepath, write_metadata(current_user.data))

    if (provenance := safe_str_get(extra, "provenance")):
        data["systags"] = provenance
    write_textual(filepath + ITEMS_EXT, write_metadata(data))
    return True

def delete_item(item:dict|str) -> int:
    deleted = 0
    iid = cast(str, item["id"] if type(item) == dict else item)
    filepath = os.path.join(ITEMS_ROOT, iid_to_filename(iid))
    files = glob(f"{filepath}.*")
    for file in files:
        os.remove(file)
        deleted += 1
    return deleted

def is_file_type_allowed(kind:str, ext:str) -> bool:
    return ((kind == "image" and ext in EXTENSIONS["image"]) or (kind == "video" and ext in EXTENSIONS["video"]))

def read_metadata(text:str) -> MetaDict:
    config = ConfigParser(interpolation=None)
    config.read_string(f"[DEFAULT]\n{text}")
    data = config._defaults # type: ignore[attr-defined]
    for key in ("items", "systags"):
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

    return {
        "title": soup_or_default(soup, "meta", {"property": "og:title"}, "content", (soup.title.string if soup.title else None)),
        "description": description,
        "image": image,
        "link": soup_or_default(soup, "link", {"rel": "canonical"}, "href", url),
    }

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default:Any) -> Any:
    elem = soup.find(tag, attrs=attrs)
    return (elem.get(prop) if elem else None) or default # type: ignore[attr-defined]

def generate_iid() -> str:
    return str(next(snowflake))

def split_iid(iid:str) -> tuple[str, str]:
    toks = iid.split("/")
    return ("/".join(toks[:-1]), toks[-1])

def strip_ext(filename:str) -> str:
    return os.path.splitext(filename)[0]

def list_to_wsv(data:list[str], sep="\n") -> str:
    return sep.join(data)

def wsv_to_list(data:str) -> list[str]:
    return data.strip().replace(" ", "\n").replace("\t", "\n").splitlines()

def safe_str_get(dikt:dict[str,str]|dict[str,str|None], key:str) -> str:
    return dikt.get(key) or ""

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
