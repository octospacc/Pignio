import os
import requests
import urllib.parse
from functools import wraps
from typing import Any, cast
from base64 import b64decode, urlsafe_b64encode
from io import StringIO
from configparser import ConfigParser
from bs4 import BeautifulSoup
from flask import Flask, request, redirect, render_template, send_from_directory, abort, url_for, flash, session, make_response
from flask_bcrypt import Bcrypt # type: ignore[import-untyped]
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required # type: ignore[import-untyped]
from flask_wtf import FlaskForm # type: ignore[import-untyped]
from wtforms import StringField, PasswordField, SubmitField # type: ignore[import-untyped]
from wtforms.validators import DataRequired # type: ignore[import-untyped]
from glob import glob
from pathlib import Path
from datetime import datetime
from snowflake import Snowflake, SnowflakeGenerator # type: ignore[import-untyped]
from hashlib import sha256
from _util import *

# config #
DEVELOPMENT = False
HTTP_PORT = 5000
HTTP_THREADS = 32
LINKS_PREFIX = ""
# endconfig #

try:
    from _config import *
except ModuleNotFoundError:
    # print("Configuration file not found! Generating...")
    from secrets import token_urlsafe
    config = read_textual(__file__).split("# config #")[1].split("# endconfig #")[0].strip()
    write_textual("_config.py", f"""\
SECRET_KEY = "{token_urlsafe()}"
{config}
""")
    # print("Saved configuration to _config.py. Exiting!")
    # exit()
    from _config import *

app = Flask(__name__)
app.config["LINKS_PREFIX"] = LINKS_PREFIX
app.config["APP_NAME"] = "Pignio"
app.config["APP_ICON"] = "📌"
app.config["DEVELOPMENT"] = DEVELOPMENT
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
    "image": ("jpg", "jpeg", "png", "gif", "webp", "avif"),
    "video": ("mp4", "mov", "mpeg", "ogv", "webm", "mkv"),
    "audio": ("mp3", "m4a", "flac", "opus", "ogg", "wav"),
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

def noindex(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        response = make_response(view_func(*args, **kwargs))
        response.headers["X-Robots-Tag"] = "noindex"
        return response
    return wrapped_view

@app.route("/")
def index():
    return render_template("index.html", items=walk_items())

@app.route("/manifest.json")
@noindex
def serve_manifest():
    response = make_response(render_template("manifest.json"))
    response.headers["Content-Type"] = "application/json"
    return response

@app.route("/static/module/<path:module>/<path:filename>")
@noindex
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
@noindex
@login_required
def add_item():
    item = {}

    if request.method == "GET":
        if (iid := request.args.get("item")):
            if not (item := load_item(iid)):
                abort(404)

    elif request.method == "POST":
        iid = request.form.get("id") or generate_iid()

        if store_item(iid, request.form, request.files):
            return redirect(url_for("view_item", iid=iid))
        else:
            flash("Cannot save item", "danger")

    return render_template("add.html", item=item)

@app.route("/delete", methods=["GET", "POST"])
@noindex
@login_required
def remove_item():
    if request.method == "GET":
        if (iid := request.args.get("item")):
            if (item := load_item(iid)):
                return render_template("delete.html", item=item)

    elif request.method == "POST":
        if (iid := request.form.get("id")):
            if (item := load_item(iid)):
                delete_item(item)
                return redirect(url_for("index"))

    abort(404)

@app.errorhandler(404)
def error_404(e):
    return render_template("404.html"), 404

@app.route("/login", methods=["GET", "POST"])
@noindex
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
                session["session_hash"] = generate_user_hash(user.username, user.data["password"])
                login_user(user)
                # next_url = flask.request.args.get('next')
                # if not url_has_allowed_host_and_scheme(next_url, request.host): return flask.abort(400)
                # return redirect(next_url or url_for("index"))
                return redirect(url_for("index"))
    if request.method == "POST":
        flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
@noindex
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("index"))

@app.route("/api/preview")
@noindex
@login_required
def link_preview():
    return fetch_url_data(request.args.get("url"))

@app.route("/api/items", defaults={'iid': None}, methods=["POST"])
@app.route("/api/items/<path:iid>", methods=["GET", "PUT", "DELETE"])
@noindex
@login_required
def items_api(iid:str):
    if request.method == "GET":
        return load_item(iid)
    elif request.method == "POST" or request.method == "PUT":
        iid = iid or generate_iid()
        status = store_item(iid, request.get_json())
        return {"id": iid if status else None}
    elif request.method == "DELETE":
        delete_item(iid)
        return {}

@login_manager.user_loader
def load_user(username:str):
    filepath = os.path.join(USERS_ROOT, (username + ITEMS_EXT))
    if os.path.exists(filepath):
        return User(username, filepath)

@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return {"error": "Unauthorized"}, 401
    else:
        flash("Please log in to access this page.")
        return redirect(url_for("login"))

@app.before_request
def validate_session():
    if current_user.is_authenticated:
        expected_hash = generate_user_hash(current_user.username, current_user.data["password"])
        if session.get("session_hash") != expected_hash:
            logout_user()

def generate_user_hash(username:str, password:str):
    text = f"{username}:{password}"
    return urlsafe_b64encode(sha256(text.encode()).digest()).decode()

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

            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["image"]])):
                data["image"] = file.replace(os.sep, "/").removeprefix(f"{ITEMS_ROOT}/")

        return data

def store_item(iid:str, data:dict, files:dict|None=None):
    iid = filename_to_iid(iid)
    existing = load_item(iid)
    filename = split_iid(iid_to_filename(iid))
    filepath = os.path.join(ITEMS_ROOT, *filename)
    mkdirs(os.path.join(ITEMS_ROOT, filename[0]))
    image = False
    data = {key: data[key] for key in ["link", "title", "description", "image", "text"] if key in data}

    if files and len(files):
        file = files["file"]
        if file.seek(0, os.SEEK_END):
            file.seek(0, os.SEEK_SET)
            mime = file.content_type.split("/")
            ext = mime[1]
            if mime[0] == "image" and ext in EXTENSIONS["image"]:
                file.save(f"{filepath}.{ext}")
                image = True
    if not image and "image" in data and data["image"]:
        if data["image"].lower().startswith("data:image/"):
            ext = data["image"].lower().split(";")[0].split("/")[1]
            if ext in EXTENSIONS["image"]:
                with open(f"{filepath}.{ext}", "wb") as f:
                    f.write(b64decode(data["image"].split(",")[1]))
                    image = True
        else:
            response = requests.get(data["image"], timeout=5)
            mime = response.headers["Content-Type"].split("/")
            ext = mime[1]
            if mime[0] == "image" and ext in EXTENSIONS["image"]:
                with open(f"{filepath}.{ext}", "wb") as f:
                    f.write(response.content)
                    image = True
    if not (existing or image or ("text" in data and data["text"])):
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

def delete_item(item:dict|str):
    iid = cast(str, item["id"] if type(item) == dict else item)
    filepath = os.path.join(ITEMS_ROOT, iid_to_filename(iid))
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

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default):
    elem = soup.find(tag, attrs=attrs)
    return (elem.get(prop) if elem else None) or default # type: ignore[attr-defined]

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
