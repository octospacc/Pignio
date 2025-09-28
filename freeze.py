import os
from shutil import copytree, rmtree
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs
from app import *

BUILD_DIR = "build"
app.config["FREEZING"] = True
client = app.test_client()
done: set[str] = set()

def freeze_page(path:str) -> None:
    if check_link(path) and check_freezable(response := client.get(path), path):
        page = get_page_index(path)
        path = path.split("?")[0]
        is_html = str(response.headers.get("Content-Type")).split(";")[0] == "text/html"
        to_freeze: set[str] = set()

        if is_html:
            soup = BeautifulSoup(response.data, "html.parser")

            for link in soup.find_all("a", href=True):
                if "nofollow" not in link.get("rel", []): # type: ignore[operator, union-attr, arg-type]
                    to_freeze.add(url := cast(str, link["href"])) # type: ignore[index]
                    ppath = url.split("?")[0]
                    if (ppage := get_page_index(url)):
                        link["href"] = format_link(ppath, ppage) # type: ignore[index, operator]
                    else:
                        link["href"] += format_link(ppath, ppage, False) # type: ignore[index, operator]

            for link in soup.find_all("iframe", src=True):
                to_freeze.add(url := cast(str, link["src"])) # type: ignore[index]
                link["src"] += ".html" # type: ignore[index, operator]

            save_file(BUILD_DIR + format_link(path, page), str(soup).encode("utf8"))
        else:
            save_file(BUILD_DIR + path, response.data)

        done.add(path)
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

def format_link(link:str, page:str|None, full:bool=True):
    return ((link if link != "/" else "/index") if full else ("" if link != "/" else "index")) + (f".{page}" if page else "") + ".html"

def check_link(link:str) -> bool:
    return not link.lower().startswith(("//", "http://", "https://")) and link not in done

def check_freezable(response, url=None) -> bool:
    return response.status_code == 200 and (response.headers.get("X-Robots-Tag") != "noindex" or (url and url.startswith("/embed/")))

def get_page_index(path:str) -> str|None:
    if (page := parse_qs(urlparse(path).query).get("page")):
        return page[0]
    return None

if __name__ == "__main__":
    if os.path.exists(BUILD_DIR):
        rmtree(BUILD_DIR)
    print("Freezing pages & items...")
    freeze_page("/")
    print("Copying assets...")
    copytree("static", os.path.join(BUILD_DIR, "static"))
    copytree("node_modules/uikit/dist", f"{BUILD_DIR}/static/module/uikit")
    copytree("node_modules/unpoly", f"{BUILD_DIR}/static/module/unpoly")
    print(f"Done! ({len(done)} links)")
