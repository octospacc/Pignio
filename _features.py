import os
import json
import requests
import urllib.parse
from PIL import Image
from typing import Any, Literal, cast
from base64 import b64decode, urlsafe_b64encode
from urllib.parse import urlparse
from io import StringIO
from configparser import ConfigParser
from bs4 import BeautifulSoup # type: ignore[import-untyped]
from glob import glob, escape as glob_escape
from datetime import datetime
from snowflake import Snowflake # type: ignore[import-untyped]
from hashlib import sha256
from shutil import copyfile
from pytesseract import image_to_string, TesseractNotFoundError # type: ignore[import-untyped]
from werkzeug.utils import safe_join
from _util import *
from _pignio import *
from _functions import *
from _media import *
from _auth import *

def sort_items(items, key:str="datetime", inverse:bool=False):
    items = sorted(items, key=(lambda item: item.get(key, '0')))
    if inverse or key == "datetime":
        items.reverse()
    return items

def walk_items(walk_path:str|None=None, only_ids:bool=False, creator:str|None=None, comments:bool=False) -> list:
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
            if check_file_supported(file):
                iid = strip_ext(os.path.join(rel_path, file).replace(os.sep, "/"))
                iid = filename_to_iid(iid)
                results[rel_path][iid] = None

        if not only_ids:
            for iid in results[rel_path]:
                is_comment = not (not (rel_rel_path := "/".join(rel_path.split("/")[:-1])) or (rel_rel_path not in results) or (filename_to_iid(rel_path) not in results[rel_rel_path]))
                if (not comments and not is_comment) or (comments and is_comment):
                    item = load_item(iid)
                    if item and (not creator or item.get("creator") == creator):
                        results[rel_path][iid] = item

    output = [value for inner in results.values() for value in inner.values()]
    return [item for item in output if item]

def count_items() -> int:
    return len(walk_items(only_ids=True))

def count_users() -> int:
    return len(glob(f"{USERS_ROOT}/*.ini"))

def walk_collections(username:str) -> dict:
    results: dict[str, CollectionDict] = {}
    filepath = USERS_ROOT

    filepath = os.path.join(filepath, username)
    data = cast(UserDict, read_metadata(read_textual(filepath + ITEMS_EXT)))
    results[""] = load_collection(data)

    for root, dirs, files in os.walk(filepath):
        rel_path = os.path.relpath(root, filepath).replace(os.sep, "/")
        if rel_path == ".":
            rel_path = ""
        for file in files:
            if check_file_is_meta(file):
                cid = rel_path + strip_ext(file)
                data = cast(UserDict, read_metadata(read_textual(os.path.join(filepath, file))))
                results[cid] = load_collection(data)

    return results

def list_folders(path:str):
    folders = []
    if path and (base := safe_join(ITEMS_ROOT, path)):
        for folder in [name for name in os.listdir(base) if os.path.isdir(os.path.join(base, name))]:
            if is_items_folder(f"{path}/{folder}"):
                folders.append(folder)
    return sorted(folders)

def make_folders(collections):
    folders = []
    for cid in collections:
        items = list(filter(None, [load_item(iid) for iid in collections[cid]["items"]]))
        if len(items) > 0:
            folders.append({**collections[cid], "id": cid, "items": items[:2] + items[-2:]})
    return folders

def has_subitems_directory(iid:str) -> str|Literal[False]:
    return dirpath if ((dirpath := safe_join(ITEMS_ROOT, iid)) and os.path.isdir(dirpath)) else False # TODO also check if folder is not empty?

def is_items_folder(path:str) -> str|Literal[False]:
    if (dirpath := has_subitems_directory(path)):
        if len([item for item in [x for x in walk_items(path) if x] if item.get("type") != "comment"]) > 0:
            return dirpath
    return False

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
    if not filepath:
        return None

    files = glob(f"{glob_escape(filepath)}.*")
    if len(files):
        # data = Item({"id": iid})
        data: ItemDict = {"id": iid}
        if iid != filename:
            data["datetime"] = str(datetime_from_snowflake(iid)).split(".")[0]

        for file in files:
            if check_file_is_meta(file):
                data = data | read_metadata(read_textual(file))
            elif (kind := check_file_is_content(file)):
                cast(dict, data)[kind] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")

        if data.get("type") == "comment":
            data["datetime"] = str(datetime_from_snowflake(iid.split("/")[-1])).split(".")[0]
        elif data.get("type") == "carousel":
            if not data.get("images"):
                data["images"] = []
            for file in glob(f"{filepath}/*.*"):
                if (kind := check_file_is_content(file)) == "image":
                    data["images"].append(file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/"))
            data["images"] = sorted(data["images"])

        if len(data) > 1: # prevent empty ini files with no valid media from being returned
            return data
    return None

# TODO: when updating existing item, and providing new media in the request, first delete old ones to account for different extensions; also clean cache every time
def store_item(iid:str, data:dict[str, str], files:dict|None=None, ocr:bool=False, *, comment:bool=False) -> bool:
    iid = filename_to_iid(iid)
    existing = load_item(iid)
    
    if existing and not get_item_permissions(existing)["edit"]:
        return False # NOTE: this is not working?

    filename = split_iid(iid_to_filename(iid))
    filepath = safe_join(ITEMS_ROOT, *filename)
    dirpath = safe_join(ITEMS_ROOT, filename[0])

    if not filepath or not dirpath:
        return False

    mkdirs(dirpath)

    has_media: bool|str = False
    media_path: str|None = None
    existing_media: str|None = None

    extra = {key: data[key] for key in ["provenance", "nsfw", "archive", "collections"] if key in data}
    data = {key: data[key] for key in ["link", "title", "description", "images", "image", "video", "audio", "text", "alttext", "langs", "status"] if key in data}
    if comment:
        data["type"] = "comment"

    if files and len(files):
        file = files["file"]
        if file.seek(0, os.SEEK_END):
            file.seek(0, os.SEEK_SET)
            [kind, ext] = file.content_type.split("/")
            if (newext := get_allowed_filetype(kind, ext)):
                file.save(media_path := f"{filepath}.{newext}")
                has_media = kind

    if not has_media and (media := (data.get("video") or data.get("audio") or data.get("image"))):
        if extra.get("archive"):
            if (stored := store_url_file(media, filepath)):
                has_media, media_path = stored
        else:
            has_media = True
    
    if not has_media and (images := data.get("images")) and (images := json.loads(str(images))) and len(images) >= 2:
        data["images"] = images
        if extra.get("archive"):
            mkdirs(filepath)
            for i, image in enumerate(images):
                if store_url_file(image, f"{filepath}/{i + 1}") == False:
                    return False
        has_media = "images"

    if not (existing or has_media or safe_str_get(data, "text")):
        return False

    langs = list(data["langs"] if "langs" in data else [])
    if ocr and (has_media == "image" or (existing_media := safe_str_get(cast(dict, existing), "image"))) and not safe_str_get(data, "alttext"):
        if existing_media:
            media_path = safe_join(ITEMS_ROOT, existing_media)
        if media_path and len(langs) > 0:
            data["alttext"] = ocr_image(media_path, langs)

    if existing:
        if (kind := existing.get("type")):
            data["type"] = kind
        if (creator := existing.get("creator")):
            data["creator"] = creator
        for kind in MEDIA_TYPES:
            if (media := safe_str_get(existing, kind)) and type(media) == str and is_absolute_url(media): # and not data.get(kind):
                data[kind] = media
    else:
        data["creator"] = (username := get_current_user().username)
        if has_media == "images":
            data["type"] = "carousel"
        if not comment:
            if (collections := extra.get("collections")):
                for collection in list(collections):
                    if collection != "-":
                        toggle_in_collection(username, collection, iid, True)
            else:
                toggle_in_collection(username, "", iid, True)

    systags = []
    if (provenance := safe_str_get(extra, "provenance")):
        systags.append(provenance)
    if extra.get("nsfw"):
        systags.append("nsfw")
    data["systags"] = systags # type: ignore[assignment]

    write_textual(filepath + ITEMS_EXT, write_metadata(data))
    delete_item_cache(iid)
    return True

def delete_item(item:dict|str, only_media:bool=False) -> int:
    deleted = 0
    if (filepath := safe_join(ITEMS_ROOT, iid_to_filename(ensure_item_id(item)))):
        files = glob(f"{filepath}.*")
        for file in files:
            if not only_media or not file.lower().endswith(ITEMS_EXT):
                os.remove(file)
                deleted += 1
    return deleted + delete_item_cache(item)

def delete_item_cache(item:dict|str) -> int:
    deleted = 0
    if (filepath := safe_join(CACHE_ROOT, ensure_item_id(item))):
        files = glob(f"{filepath}.*")
        for file in files:
            os.remove(file)
            deleted += 1
    return deleted

def get_item_permissions(item:ItemDict|str) -> dict[str, bool]:
    item = ensure_item_dict(item)
    return {"view": True, "edit": (user := get_current_user()).is_authenticated and (item.get("creator") == user.username or user.is_admin)}

def ensure_item_id(data:dict|str) -> str:
    return cast(str, data["id"] if type(data) == dict else data)

def ensure_item_dict(data:ItemDict|str) -> ItemDict:
    return cast(ItemDict, data if type(data) == dict else load_item(cast(str, data)))

def toggle_in_collection(username:str, cid:str, iid:str, status:bool) -> None:
    filepath = get_collection_filepath(username, cid)
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

def get_collection_filepath(username:str, cid:str) -> str:
    return f"{USERS_ROOT}/{username}" + (f"/{cid}" if cid else "") + ITEMS_EXT

def load_collection(data:UserDict) -> CollectionDict:
    items = data.get("items", [])
    items.reverse()
    return cast(CollectionDict, {**data, "items": items})

def fetch_url_data(url:str) -> dict[str, str|None]:
    response = requests.get(url, timeout=5)
    mime = response.headers["Content-Type"].split("/")[0]
    if mime in ["image", "video", "audio"]:
        return {
            mime: url,
            "link": response.url,
        }
    else:
        soup = BeautifulSoup(response.text, "html.parser")
        media = {"image": None, "video": None, "audio": None}

        title_tag = soup.find("meta", attrs={"property": "og:title", "content": True}) or \
                    soup.find("meta", attrs={"name": "twitter:title", "content": True})
        title = (title_tag["content"] if title_tag else None) or (soup.title.string if soup.title else None) # type: ignore[index]

        description = None
        desc_tag = soup.find("meta", attrs={"property": "og:description", "content": True}) or \
                   soup.find("meta", attrs={"name": "twitter:description", "content": True}) or \
                   soup.find("meta", attrs={"name": "description", "content": True})
        if desc_tag: # type: ignore[attr-defined]
            description = desc_tag["content"] # type: ignore[index]

        img_tag = soup.find("meta", attrs={"property": "og:image", "content": True}) or \
                  soup.find("meta", attrs={"property": "og:image:url", "content": True}) or \
                  soup.find("meta", attrs={"property": "og:image:secure_url", "content": True}) or \
                  soup.find("meta", attrs={"name": "twitter:image", "content": True})
        if img_tag: # type: ignore[attr-defined]
            media["image"] = img_tag["content"] # type: ignore[index]

        video_tag = soup.find("meta", attrs={"property": "og:video", "content": True}) or \
                    soup.find("meta", attrs={"property": "og:video:url", "content": True}) or \
                    soup.find("meta", attrs={"property": "og:video:secure_url", "content": True})
        if video_tag: # type: ignore[attr-defined]
            media["video"] = video_tag["content"] # type: ignore[index]

        audio_tag = soup.find("meta", attrs={"property": "og:audio", "content": True}) or \
                    soup.find("meta", attrs={"property": "og:audio:url", "content": True}) or \
                    soup.find("meta", attrs={"property": "og:audio:secure_url", "content": True})
        if audio_tag: # type: ignore[attr-defined]
            media["audio"] = audio_tag["content"] # type: ignore[index]

        alttext = None
        alt_tag = soup.find("meta", attrs={"property": "og:image:alt", "content": True}) or \
                  soup.find("meta", attrs={"name": "twitter:image:alt", "content": True})
        if alt_tag:
            alttext = alt_tag["content"] # type: ignore[index]

        for kind in media.keys():
            if (source := media[kind]):
                parsed = urlparse(source)
                if not parsed.scheme and not parsed.netloc:
                    parsed = urlparse(url)
                    media[kind] = f"{parsed.scheme}://{parsed.netloc}" + source

        return {
            "title": title,
            "description": description,
            **media,
            "alttext": alttext,
            "link": soup_or_default(soup, "link", {"rel": "canonical"}, "href", response.url),
        }

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default:Any) -> Any:
    elem = soup.find(tag, attrs=attrs)
    return (elem.get(prop) if elem else None) or default # type: ignore[attr-defined]

def generate_iid() -> str:
    return str(next(snowflake))

def split_iid(iid:str) -> tuple[str, str]:
    toks = iid.split("/")
    return ("/".join(toks[:-1]), toks[-1])

def view_embedded(iid:str, template:str, key:str, kwarger:Callable|None=None):
    if (item := load_item(iid)) and (media := item.get(key)):
        kwargs = kwarger(item) if kwarger else {}
        return render_template(f"embeds/{template}.html", **{key: media}, **kwargs)
    else:
        return abort(404)
