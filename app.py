import os
import requests
import urllib.parse
from typing import Any
from io import StringIO
from configparser import ConfigParser
from bs4 import BeautifulSoup
from flask import Flask, request, redirect, render_template, send_from_directory, abort, url_for, flash
from flask_bcrypt import Bcrypt # type: ignore[import-untyped]
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required # type: ignore[import-untyped]
from flask_wtf import FlaskForm # type: ignore[import-untyped]
from wtforms import StringField, PasswordField, SubmitField # type: ignore[import-untyped]
from wtforms.validators import DataRequired # type: ignore[import-untyped]
from glob import glob
from pathlib import Path
from datetime import datetime
from snowflake import Snowflake, SnowflakeGenerator # type: ignore[import-untyped]

SECRET_KEY = "SECRET_KEY" # import secrets; print(secrets.token_urlsafe())
DEVELOPMENT = True
HTTP_PORT = 5000
HTTP_THREADS = 32
LINKS_PREFIX = ""

from _config import *

app = Flask(__name__)
app.config["LINKS_PREFIX"] = LINKS_PREFIX
app.config["APP_NAME"] = "Pignio"
app.config["APP_ICON"] = "📌"
app.config["SECRET_KEY"] = SECRET_KEY
app.config["BCRYPT_HANDLE_LONG_PASSWORDS"] = True

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
bcrypt = Bcrypt(app)

snowflake_epoch = int(datetime(2025, 1, 1, 0, 0, 0).timestamp() * 1000)
snowflake = SnowflakeGenerator(1, epoch=snowflake_epoch)

DATA_ROOT = "data"
ITEMS_ROOT = f"{DATA_ROOT}/items"
USERS_ROOT = f"{DATA_ROOT}/users"
EXTENSIONS = {
    "images": ("jpg", "jpeg", "png", "gif", "webp", "avif"),
    "videos": ("mp4", "mov", "mpeg", "ogv", "webm", "mkv"),
}
ITEMS_EXT = ".ini"

class User(UserMixin):
    def __init__(self, username, filepath):
        self.username = username
        self.filepath = filepath
        self.data = read_metadata(read_textual(filepath))

    def get_id(self):
        return self.username

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

@app.route("/")
def index():
    return render_template("index.html", items=walk_items())

@app.route("/static/module/<path:module>/<path:filename>")
def serve_module(module:str, filename:str):
    return send_from_directory(os.path.join("node_modules", module, "dist"), filename)

@app.route("/media/<path:filename>")
def serve_media(filename:str):
    return send_from_directory(ITEMS_ROOT, filename)

@app.route("/item/<path:iid>")
def view_item(iid:str):
    if (item := load_item(iid)):
        return render_template("item.html", item=item)
    else:
        abort(404)

@app.route("/user/<path:username>")
def view_user(username:str):
    if (user := load_user(username)):
        return render_template("user.html", user=user, collections=walk_collections(username), load_item=load_item)
    else:
        abort(404)

@app.route("/search")
def search():
    query = request.args.get("query", "").lower()
    found = False
    results = {}

    for folder, items in walk_items().items():
        results[folder] = []

        for item in items:
            if any([query in text.lower() for text in item.values()]):
                results[folder].append(item)
                found = True

    return render_template("search.html", items=(results if found else None), query=query)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    item = {}

    if request.method == "GET":
        if (iid := request.args.get("item")):
            if not (item := load_item(iid)):
                abort(404)

    elif request.method == "POST":
        iid = request.form.get("id") or generate_iid()
        data = {key: request.form[key] for key in ["link", "title", "description", "image", "text"]}

        if store_item(iid, data, request.files):
            return redirect(url_for("view_item", iid=iid))
        else:
            flash("Cannot save item", "danger")

    return render_template("add.html", item=item)

@app.route("/remove", methods=["GET", "POST"])
@login_required
def remove_item():
    if request.method == "GET":
        if (iid := request.args.get("item")):
            if (item := load_item(iid)):
                return render_template("remove.html", item=item)

    elif request.method == "POST":
        if (iid := request.form.get("id")):
            if (item := load_item(iid)):
                delete_item(item)
                return redirect(url_for("index"))

    abort(404)

@app.route("/api/preview")
@login_required
def link_preview():
    return fetch_url_data(request.args.get("url"))

@app.errorhandler(404)
def error_404(e):
    return render_template("404.html"), 404

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        if (user := load_user(form.username.data)):
            pass_equals = user.data["password"] == form.password.data
            try:
                hash_equals = bcrypt.check_password_hash(user.data["password"], form.password.data)
            except ValueError as e:
                hash_equals = False
            if pass_equals or hash_equals:
                if pass_equals:
                    user.data["password"] = bcrypt.generate_password_hash(user.data["password"]).decode("utf-8")
                    write_textual(user.filepath, write_metadata(user.data))
                login_user(user)
                # next_url = flask.request.args.get('next')
                # if not url_has_allowed_host_and_scheme(next_url, request.host): return flask.abort(400)
                # return redirect(next_url or url_for("index"))
                return redirect(url_for("index"))
    if request.method == "POST":
        flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("index"))

@login_manager.user_loader
def load_user(username:str):
    filepath = os.path.join(USERS_ROOT, (username + ITEMS_EXT))
    if os.path.exists(filepath):
        return User(username, filepath)

def walk_items():
    results, iids = {}, {}

    for root, dirs, files in os.walk(ITEMS_ROOT):
        rel_path = os.path.relpath(root, ITEMS_ROOT).replace(os.sep, "/")
        if rel_path == ".":
            rel_path = ""

        results[rel_path], iids[rel_path] = [], []

        for file in files:
            #if file.lower().endswith(ITEMS_EXT) or file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["images"]])):
            iid = strip_ext(os.path.join(rel_path, file).replace(os.sep, "/"))
            iid = filename_to_iid(iid)
            if iid not in iids[rel_path]:
                iids[rel_path].append(iid)

        for iid in iids[rel_path]:
            data = load_item(iid)
            results[rel_path].append(data)

    return results

def walk_collections(username:str):
    results: dict[str, list[str]] = {"": []}
    filepath = USERS_ROOT

    # if username:
    filepath = os.path.join(filepath, username)
    data = read_metadata(read_textual(filepath + ITEMS_EXT))
    results[""] = data["items"] if "items" in data else []

    # for root, dirs, files in os.walk(filepath):
    #     rel_path = os.path.relpath(root, filepath).replace(os.sep, "/")
    #     if rel_path == ".":
    #         rel_path = ""
    #     else:
    #         results[rel_path] = []

    #     for file in files:
    #         print(file, rel_path)
    #         results[rel_path] = read_metadata(read_textual(os.path.join(filepath, rel_path, file)))["items"].strip().replace(" ", "\n").splitlines()

    return results

def iid_to_filename(iid:str):
    if len(iid.split("/")) == 1:
        date = Snowflake.parse(int(iid), snowflake_epoch).datetime
        iid = f"{date.year}/{date.month}/{iid}"
    return iid

def filename_to_iid(iid:str):
    toks = iid.split("/")
    if len(toks) == 3 and "".join(toks).isnumeric():
        iid = toks[2]
    return iid

def load_item(iid:str):
    iid = filename_to_iid(iid)
    filename = iid_to_filename(iid)
    filepath = os.path.join(ITEMS_ROOT, filename)
    files = glob(f"{filepath}.*")

    if len(files):
        data = {"id": iid}

        for file in files:
            if file.lower().endswith(ITEMS_EXT):
                data = data | read_metadata(read_textual(file))

            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["images"]])):
                data["image"] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")

        return data

def store_item(iid:str, data:dict, files:dict):
    iid = filename_to_iid(iid)
    existing = load_item(iid)
    filename = split_iid(iid_to_filename(iid))
    filepath = os.path.join(ITEMS_ROOT, *filename)
    mkdirs(os.path.join(ITEMS_ROOT, filename[0]))
    image = False

    if len(files):
        file = files["file"]
        if file.seek(0, os.SEEK_END):
            file.seek(0, os.SEEK_SET)
            ext = file.content_type.split("/")[1]
            file.save(f"{filepath}.{ext}")
            image = True
    if not image and data["image"]:
        response = requests.get(data["image"], timeout=5)
        ext = response.headers["Content-Type"].split("/")[1]
        with open(f"{filepath}.{ext}", "wb") as f:
            f.write(response.content)
            image = True
    if not (existing or image or data["text"]):
        return False

    if existing:
        if "creator" in existing:
            data["creator"] = existing["creator"]
    else:
        data["creator"] = current_user.username
        items = current_user.data["items"] if "items" in current_user.data else []
        items.append(iid)
        current_user.data["items"] = items
        write_textual(current_user.filepath, write_metadata(current_user.data))

    write_textual(filepath + ITEMS_EXT, write_metadata(data))
    return True

def delete_item(item:dict):
    filepath = os.path.join(ITEMS_ROOT, iid_to_filename(item["id"]))
    files = glob(f"{filepath}.*")
    for file in files:
        os.remove(file)

def read_metadata(text:str) -> dict:
    config = ConfigParser(interpolation=None)
    config.read_string(f"[DEFAULT]\n{text}")
    data = config._defaults # type: ignore[attr-defined]
    for key in ("items",):
        if key in data:
            data[key] = wsv_to_list(data[key])
    return data

def write_metadata(data:dict) -> str:
    output = StringIO()
    config = ConfigParser(interpolation=None)
    for key in ("image", "datetime"):
        if key in data:
            del data[key]
    for key in data:
        if type(data[key]) == list:
            data[key] = list_to_wsv(data[key])
    config["DEFAULT"] = data
    config.write(output)
    return "\n".join(output.getvalue().splitlines()[1:]) # remove section header

def read_textual(filepath:str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(filepath, "r") as f:
            return f.read()

def write_textual(filepath:str, content:str):
    with open(filepath, "w", encoding="utf-8") as f:
        return f.write(content)

def fetch_url_data(url:str):
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

def prop_or_default(items:Any, prop:str, default):
    return (items[prop] if (items and prop in items) else None) or default

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default):
    return prop_or_default(soup.find(tag, attrs=attrs), prop, default)

def generate_iid() -> str:
    return str(next(snowflake))

def split_iid(iid:str):
    toks = iid.split("/")
    return ["/".join(toks[:-1]), toks[-1]]

def strip_ext(filename:str):
    return os.path.splitext(filename)[0]

def list_to_wsv(data:list, sep="\n") -> str:
    return sep.join(data)

def wsv_to_list(data:str) -> list:
    return data.strip().replace(" ", "\n").replace("\t", "\n").splitlines()

def mkdirs(*paths:str):
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)

mkdirs(ITEMS_ROOT, USERS_ROOT)

if __name__ == "__main__":
    if DEVELOPMENT:
        app.run(port=HTTP_PORT, debug=True)
    else:
        import waitress
        waitress.serve(app, port=HTTP_PORT, threads=HTTP_THREADS)
