import os
import re
import requests
import urllib.parse
from bs4 import BeautifulSoup
from flask import Flask, request, redirect, render_template, send_from_directory, abort, url_for
from pathlib import Path
from datetime import datetime
from snowflake import SnowflakeGenerator

app = Flask(__name__)
snowflake = SnowflakeGenerator(1, epoch=int(datetime(2025, 1, 1, 0, 0, 0).timestamp() * 1000))

DATA_ROOT = "data"
ITEMS_ROOT = f"{DATA_ROOT}/items"
MEDIA_ROOT = f"{DATA_ROOT}/items"
EXTENSIONS = {
    "images": ("jpg", "jpeg", "png", "gif", "webp", "avif"),
    "videos": ("mp4", "mov", "mpeg", "ogv", "webm", "mkv"),
}

@app.route("/")
def index():
    return render_template("index.html", media=walk_items())

@app.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_ROOT, filename)

@app.route("/item/<path:filename>")
def view_item(filename):
    # full_path = os.path.join(MEDIA_ROOT, filename)
    # if not os.path.exists(full_path):
    #     abort(404)
    item = load_item(filename)
    if not item:
        abort(404)
    return render_template("item.html", filename=filename, item=item)

@app.route("/search")
def search():
    query = request.args.get("query", "").lower()
    results = {}

    for folder, items in walk_items().items():
        results[folder] = []

        for item in items:
            image = item["id"]
            meta = load_sider_metadata(image) or {}
            if any([query in text.lower() for text in [image, *meta.values()]]):
                results[folder].append(image)

    return render_template("search.html", media=results, query=query)

@app.route("/add", methods=["GET", "POST"])
def add_item():
    item = {}

    if request.method == "GET":
        iid = request.args.get("item")
        if iid:
            item = load_item(iid)

    elif request.method == "POST":
        iid = request.form.get("id") or generate_iid()
        # title = request.form.get("title")
        # description = request.form.get("description")

        # if (url := request.form.get("url")):
        #     download_item(url)
        # else:
        #     with open(os.path.join(MEDIA_ROOT, f"{iid[1]}.item"), "w") as f:
        #         f.write(write_metadata({
        #             "description": description
        #         }))
        # return redirect(url_for("index"))

        filename = store_item(iid, {
            "link": request.form.get("link"),
            "title": request.form.get("title"),
            "description": request.form.get("description"),
        }, request.files['file'])

        return redirect(url_for("view_item", filename=filename))

    return render_template("add.html", item=item)

@app.route("/api/preview")
def preview():
    return fetch_url_data(request.args.get("url"))

@app.errorhandler(404)
def error_404(e):
    return render_template("404.html"), 404

def walk_items():
    results = {}

    for root, dirs, files in os.walk(MEDIA_ROOT):
        rel_path = os.path.relpath(root, MEDIA_ROOT).replace(os.sep, "/")
        if rel_path == ".":
            rel_path = ""

        results[rel_path] = []
        for file in files:
            filename = os.path.join(rel_path, file).replace(os.sep, "/")
            if file.lower().endswith(".item"):
                with open(os.path.join(MEDIA_ROOT, rel_path, file), "r") as f:
                    data = read_metadata(f.read())
                    data["id"] = filename
                    results[rel_path].append(data)
            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["images"]])):
                # results[rel_path].append(os.path.join(rel_path, file).replace(os.sep, "/"))
                image = os.path.join(rel_path, file).replace(os.sep, "/")
                data = load_sider_metadata(image) or {}
                data["image"] = image
                data["id"] = filename
                results[rel_path].append(data)
    
    return results

def load_item(iid):
    data = None
    filepath = os.path.join(MEDIA_ROOT, iid)

    if os.path.exists(filepath):
        if iid.lower().endswith(".item"):
            with open(filepath, "r") as f:
                data = read_metadata(f.read())
        else:
            data = load_sider_metadata(iid) or {}
            data["image"] = iid

    if data:
        data["id"] = iid
        return data

def load_sider_metadata(filename):
    filepath = os.path.join(MEDIA_ROOT, f"{strip_ext(filename)}.meta")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return read_metadata(f.read())

def read_metadata(text:str):
    data = {}
    for elem in BeautifulSoup(re.sub(r'<(\w+)>(.*?)</>', r'<\1>\2</\1>', text), "html.parser").find_all():
        data[elem.name] = elem.text.strip()
    return data

def write_metadata(data:dict):
    text = ""
    for key in data:
        if (value := data[key]):
            text += f'<{key}>{value}</>\n'
    return text

def fetch_url_data(url:str):
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")

        description = None
        desc_tag = soup.find("meta", attrs={"name": "description"}) or \
                   soup.find("meta", attrs={"property": "og:description"})
        if desc_tag and "content" in desc_tag.attrs:
            description = desc_tag["content"]

        image = None
        img_tag = soup.find("meta", attrs={"property": "og:image"}) or \
                  soup.find("meta", attrs={"name": "twitter:image"})
        if img_tag and "content" in img_tag.attrs:
            image = img_tag["content"]

        return {
            "title": soup_or_default(soup, "meta", {"property": "og:title"}, "content", (soup.title.string if soup.title else None)),
            "description": description,
            "image": image,
            "link": soup_or_default(soup, "link", {"rel": "canonical"}, "href", url),
        }

    except Exception as e:
        # print("Metadata fetch failed:", e)
        return {}

def download_item(url:str):
    data = fetch_url_data(url)
    url = urllib.parse.urlparse(data["link"])
    slug = (url.path or "index").split("/")[-1]
    domain = url.netloc
    Path(os.path.join(MEDIA_ROOT, domain)).mkdir(parents=True, exist_ok=True)
    path = os.path.join(MEDIA_ROOT, domain, slug)
    with open(f"{path}.meta", "w") as f:
        f.write(write_metadata(data))

def store_item(iid, data, file):
    item = load_item(iid)
    iid = split_iid(strip_ext(iid))
    filepath = os.path.join(MEDIA_ROOT, *iid)
    Path(os.path.join(MEDIA_ROOT, iid[0])).mkdir(parents=True, exist_ok=True)
    if file:
        with open(f"{filepath}.meta", "w") as f:
            f.write(write_metadata(data))
        # with open(f"{filepath}.{ext}", "wb") as f:
        #     f.write(write_metadata(data))
        ext = file.content_type.split("/")[1]
        file.save(f'{filepath}.{ext}')
        return "/".join(iid) + f".{ext}"
    else:
        with open(f"{filepath}.item", "w") as f:
            f.write(write_metadata(data))
        return "/".join(iid) + ".item"
    # return "/".join(iid)

def prop_or_default(items:dict, prop:str, default):
    return (items[prop] if (items and prop in items) else None) or default

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default):
    return prop_or_default(soup.find(tag, attrs=attrs), prop, default)

def generate_iid():
    date = datetime.now()
    return f"{date.year}/{date.month}/{next(snowflake)}"
    # return [f"{date.year}/{date.month}", next(snowflake)]

def split_iid(iid:str):
    iid = iid.split("/")
    return ["/".join(iid[:-1]), iid[-1]]

def strip_ext(filename:str):
    return os.path.splitext(filename)[0]

if __name__ == "__main__":
    app.run(debug=True)