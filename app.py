import os
import re
import requests
import configparser
import urllib.parse
import xml.etree.ElementTree as ElementTree
from io import StringIO
from bs4 import BeautifulSoup
from flask import Flask, request, redirect, render_template, send_from_directory, abort, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from glob import glob
from pathlib import Path
from datetime import datetime
from snowflake import Snowflake, SnowflakeGenerator

app = Flask(__name__)
app.config["SECRET_KEY"] = "your_secret_key" # TODO: fix this for prod
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
bcrypt = Bcrypt(app)

snowflake_epoch = int(datetime(2025, 1, 1, 0, 0, 0).timestamp() * 1000)
snowflake = SnowflakeGenerator(1, epoch=snowflake_epoch)

DATA_ROOT = "data"
ITEMS_ROOT = f"{DATA_ROOT}/items"
USERS_ROOT = f"{DATA_ROOT}/users"
MEDIA_ROOT = f"{DATA_ROOT}/items"
EXTENSIONS = {
    "images": ("jpg", "jpeg", "png", "gif", "webp", "avif"),
    "videos": ("mp4", "mov", "mpeg", "ogv", "webm", "mkv"),
}
ITEMS_EXT = ".pignio"

class User(UserMixin):
    def __init__(self, username, filepath):
        self.username = username
        self.filepath = filepath
        with open(filepath, "r") as f:
            self.data = read_metadata(f.read())

    def get_id(self):
        return self.username

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

@app.route("/")
def index():
    return render_template("index.html", media=walk_items())

@app.route("/media/<path:filename>")
def serve_media(filename:str):
    return send_from_directory(MEDIA_ROOT, filename)

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
@login_required
def add_item():
    item = {}

    if request.method == "GET":
        if (iid := request.args.get("item")):
            if not (item := load_item(iid)):
                abort(404)

    elif request.method == "POST":
        iid = request.form.get("id") or generate_iid()

        store_item(iid, {
            "link": request.form.get("link"),
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "image": request.form.get("image"),
        }, request.files)

        return redirect(url_for("view_item", iid=iid))

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

    # iid = request.args.get("item")
    # item = load_item(iid)
    # if not item:
    #     abort(404)
    # if request.method == "GET":
    #     return render_template("remove.html", item=item)
    # elif request.method == "POST":
    #     delete_item(item)
    #     return redirect(url_for("index"))

@app.route("/api/preview")
@login_required
def preview():
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
                    with open(user.filepath, "w") as f:
                        f.write(write_metadata(user.data))
                login_user(user)
                # next_url = flask.request.args.get('next')
                # if not url_has_allowed_host_and_scheme(next_url, request.host): return flask.abort(400)
                # return redirect(next_url or url_for("index"))
                return redirect(url_for("index"))
    if request.method == "POST":
        flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@login_manager.user_loader
def load_user(username:str):
    filepath = os.path.join(USERS_ROOT, (username + ITEMS_EXT))
    if os.path.exists(filepath):
        return User(username, filepath)

def walk_items():
    results, iids = {}, {}

    for root, dirs, files in os.walk(MEDIA_ROOT):
        rel_path = os.path.relpath(root, MEDIA_ROOT).replace(os.sep, "/")
        if rel_path == ".":
            rel_path = ""

        results[rel_path], iids[rel_path] = [], []

        # for file in files:
        #     if file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["images"]])):
        #         iid = strip_ext(os.path.join(rel_path, file).replace(os.sep, "/"))
        #         image = os.path.join(rel_path, file).replace(os.sep, "/")
        #         data = load_sider_metadata(image) or {}
        #         data["image"] = image
        #         data["id"] = iid
        #         results[rel_path].append(data)
        #         files.remove(file)

        # for file in files:
        #     if file.lower().endswith(ITEMS_EXT):
        #         iid = strip_ext(os.path.join(rel_path, file).replace(os.sep, "/"))
        #         with open(os.path.join(MEDIA_ROOT, rel_path, file), "r") as f:
        #             data = read_metadata(f.read())
        #             data["id"] = iid
        #             results[rel_path].append(data)
        #         files.remove(file)

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

def walk_collections(username:str=None):
    results = {"": []}

    filepath = USERS_ROOT

    if username:
        filepath = os.path.join(filepath, username)
        results[""] = read_metadata(read_textual(filepath + ITEMS_EXT))["items"].strip().replace(" ", "\n").splitlines()

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
    filepath = os.path.join(MEDIA_ROOT, filename)
    files = glob(f"{filepath}.*")

    if len(files):
        data = {"id": iid}

        for file in files:
            if file.lower().endswith(ITEMS_EXT):
                # with open(file, "r", encoding="utf-8") as f:
                #     data = data | read_metadata(f.read())
                data = data | read_metadata(read_textual(file))

            elif file.lower().endswith(tuple([f".{ext}" for ext in EXTENSIONS["images"]])):
                data["image"] = file.replace(os.sep, "/").removeprefix(f"{MEDIA_ROOT}/")

        return data

def load_sider_metadata(filename:str):
    filepath = os.path.join(MEDIA_ROOT, f"{strip_ext(filename)}{ITEMS_EXT}")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return read_metadata(f.read())

# def read_metadata(text:str):
#     data = {}
#     xml = "<root>" + re.sub(r'<(\w+)>(.*?)</>', r'<\1>\2</\1>', text) + "</root>"
#     for elem in ElementTree.fromstring(xml, parser=ElementTree.XMLParser(encoding="utf-8")).findall('*'):
#         data[elem.tag] = elem.text.strip()
#     return data

def read_metadata(text:str) -> dict:
    config = configparser.ConfigParser(allow_unnamed_section=True, interpolation=None)
    config.read_string(text)
    return config._sections[configparser.UNNAMED_SECTION] # tuple(config._sections.values())[0]

# def write_metadata(data:dict):
#     text = ""
#     for key in data:
#         if key not in ("image",) and (value := data[key]):
#             text += f'<{key}>{value}</>\n'
#     return text

def write_metadata(data:dict) -> str:
    output = StringIO()
    config = configparser.ConfigParser(allow_unnamed_section=True, interpolation=None)
    del data["image"]
    config[configparser.UNNAMED_SECTION] = data
    config.write(output)
    return "\n".join(output.getvalue().splitlines()[1:]) # remove section header

def read_textual(filepath:str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(filepath, "r") as f:
            return f.read()

def write_textual(filepath:str, content:bytes):
    with open(filepath, "w", encoding="utf-8") as f:
        return f.write(content)

def fetch_url_data(url:str):
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

def store_item(iid, data, files):
    iid = iid_to_filename(iid)
    iid = split_iid(strip_ext(iid))
    filepath = os.path.join(MEDIA_ROOT, *iid)
    Path(os.path.join(MEDIA_ROOT, iid[0])).mkdir(parents=True, exist_ok=True)
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
    # with open(filepath + ITEMS_EXT, "w", encoding="utf-8") as f:
    #     f.write(write_metadata(data))
    write_textual(filepath + ITEMS_EXT, write_metadata(data))

def delete_item(item:dict):
    filepath = os.path.join(MEDIA_ROOT, iid_to_filename(item["id"]))
    files = glob(f"{filepath}.*")
    # for key in ("id", "image"):
    #     if key in item and (value := item[key]):
    #         filepath = os.path.join(MEDIA_ROOT, value)
    #         if os.path.exists(filepath):
    #             os.remove(filepath)
    for file in files:
        os.remove(file)

def prop_or_default(items:dict, prop:str, default):
    return (items[prop] if (items and prop in items) else None) or default

def soup_or_default(soup:BeautifulSoup, tag:str, attrs:dict, prop:str, default):
    return prop_or_default(soup.find(tag, attrs=attrs), prop, default)

def generate_iid():
    return str(next(snowflake))
    # iid = next(snowflake)
    # date = Snowflake.parse(iid, snowflake_epoch).datetime
    # return f"{date.year}/{date.month}/{next(snowflake)}"

def split_iid(iid:str):
    iid = iid.split("/")
    return ["/".join(iid[:-1]), iid[-1]]

def strip_ext(filename:str):
    return os.path.splitext(filename)[0]

if __name__ == "__main__":
    app.run(debug=True)