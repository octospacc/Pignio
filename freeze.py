import os
from shutil import copytree, rmtree
from bs4 import BeautifulSoup # type: ignore[import-untyped]
from urllib.parse import unquote, urlparse, parse_qs
from app import *

BUILD_DIR = "build"

app.config["FREEZING"] = True
client = app.test_client()
done: set[str] = set()

def freeze_page(raw_path:str) -> None:
    if check_link(raw_path) and check_freezable(response := client.get(raw_path), raw_path):
        page = get_page_index(raw_path)
        mode = get_page_mode(raw_path)
        path = raw_path.split("?")[0]
        is_html = str(response.headers.get("Content-Type")).split(";")[0] == "text/html"
        to_freeze: set[str] = set()

        if is_html:
            soup = BeautifulSoup(response.data, "html.parser")

            for link in soup.find_all("a", href=True):
                url = cast(str, link["href"]) # type: ignore[index]
                if not is_url_absolute(url) and "nofollow" not in link.get("rel", []): # type: ignore[operator, union-attr, arg-type]
                    to_freeze.add(url)
                    ppath = url.split("?")[0]
                    ppage = get_page_index(url)
                    pmode = get_page_mode(url)
                    if ppage or pmode:
                        link["href"] = format_link(ppath, ppage, pmode) # type: ignore[index, operator]
                    else:
                        link["href"] += format_link(ppath, None, None, False) # type: ignore[index, operator]

            for link in soup.find_all("iframe", src=True):
                to_freeze.add(url := cast(str, link["src"])) # type: ignore[index]
                link["src"] += ".html" # type: ignore[index, operator]

            save_file(BUILD_DIR + format_link(path, page, mode), str(soup).encode("utf8"))
        elif str(response.headers.get("Content-Type")).split(";")[0] == "application/json":
            save_file(BUILD_DIR + path + ".json", response.data)
        else:
            save_file(BUILD_DIR + path, response.data)

        done.add(path)
        done.add(raw_path)
        print(f"* {path} / {page}")

        if is_html:
            for kind in ((["img", "video", "audio"], "src"), ("object", "data")):
                for media in soup.find_all(kind[0], **{kind[1]: True}): # type: ignore[arg-type]
                    src = cast(str, media[kind[1]]).split("?")[0] # type: ignore[index]
                    if check_link(src) and check_freezable(response := client.get(src)):
                        save_file(BUILD_DIR + src, response.data)
                        done.add(src)
                        print(f"  + {src}")

            for url in to_freeze:
                freeze_page(url)
                if url.startswith("/item/"):
                    freeze_page("/embed" + url)

def save_file(path:str, data:bytes) -> None:
    path = unquote(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def format_link(link:str, page:str|None, mode:str|None, full:bool=True):
    base = (link if link != "/" else "/index") if full else ("" if link != "/" else "index")
    return base + (f".{mode}" if mode else "") + (f".{page}" if page else "") + ".html"

def is_url_absolute(link:str) -> bool:
    return link.lower().startswith(("//", "http://", "https://"))

def check_link(link:str) -> bool:
    return not is_url_absolute(link) and link not in done

def check_freezable(response, url=None) -> bool:
    return response.status_code == 200 and (response.headers.get("X-Robots-Tag") != "noindex" or (url and url.startswith(("/embed/", "/api/v1/"))))

def get_page_index(path:str) -> str|None:
    return get_query_param(path, "page")

def get_page_mode(path:str) -> str|None:
    return get_query_param(path, "mode")

def get_query_param(url:str, key:str) -> str|None:
    if (vals := parse_qs(urlparse(url).query).get(key)):
        return vals[0]
    return None

def copy_module(module:str, prefix:str=""):
    copytree(f"node_modules/{module}/{prefix}", f"{BUILD_DIR}/static/module/{module}")

if __name__ == "__main__":
    if os.path.exists(BUILD_DIR):
        rmtree(BUILD_DIR)

    print("Freezing pages & items...")
    freeze_page("/")
    freeze_page("/api/v1/items")

    print("Copying assets...")
    copytree("static", os.path.join(BUILD_DIR, "static"), dirs_exist_ok=True)
    copy_module("uikit", "dist")
    copy_module("unpoly")
    copy_module("simplelightbox", "dist")

    print(f"Done! ({len(done)} links)")
