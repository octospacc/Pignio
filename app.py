import os
import urllib.parse
from functools import wraps
from typing import Any, cast
from random import shuffle
from flask import Flask, request, redirect, render_template, send_from_directory, abort, url_for, flash, session, make_response
from flask_bcrypt import Bcrypt # type: ignore[import-untyped]
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required, login_url # type: ignore[import-untyped]
from flask_wtf import FlaskForm # type: ignore[import-untyped]
from wtforms import StringField, PasswordField, BooleanField, SubmitField # type: ignore[import-untyped]
from wtforms.validators import DataRequired # type: ignore[import-untyped]
from _pignio import *
from _util import *

# config #
DEVELOPMENT = False
HTTP_PORT = 5000
HTTP_THREADS = 32
LINKS_PREFIX = ""
SITE_VERIFICATION = {
    "GOOGLE": "",
    "BING": "",
}
# endconfig #

try:
    from _config import *
except ModuleNotFoundError:
    from secrets import token_urlsafe
    config = read_textual(__file__).split("# config #")[1].split("# endconfig #")[0].strip()
    write_textual("_config.py", f"""\
SECRET_KEY = "{token_urlsafe()}"
{config}
""")
    from _config import *

app = Flask(__name__)
app.config["DEVELOPMENT"] = DEVELOPMENT
app.config["SECRET_KEY"] = SECRET_KEY
app.config["BCRYPT_HANDLE_LONG_PASSWORDS"] = True

app.config["LINKS_PREFIX"] = LINKS_PREFIX
app.config["APP_NAME"] = "Pignio"
app.config["APP_ICON"] = "📌"
app.config["SITE_VERIFICATION"] = SITE_VERIFICATION

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
bcrypt = Bcrypt(app)

class User(UserMixin):
    def __init__(self, username:str, filepath:str):
        self.username: str = username
        self.filepath: str = filepath
        self.data = cast(UserDict, read_metadata(read_textual(filepath)))

    def get_id(self) -> str:
        return generate_user_hash(self.username, self.data["password"])
    
    def is_admin(self) -> bool:
        return True # TODO

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField()
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
    limit = 50
    page = int(request.args.get("page", 1))
    next_count = (limit * page)
    all_items = walk_items()
    items = all_items[(limit * (page - 1)):next_count]
    if len(items) == 0 and len(all_items) > 0:
        abort(404)
    shuffle(items)
    return render_template("index.html", items=items, next_page=(page + 1 if len(all_items) > next_count else None))

@app.route("/manifest.json")
@noindex
def serve_manifest():
    response = make_response(render_template("manifest.json"))
    response.headers["Content-Type"] = "application/json"
    return response

@app.route("/static/module/dist/uikit/<path:filename>")
@noindex
def serve_module_uikit(filename:str):
    return send_from_directory(os.path.join("node_modules", "uikit", "dist"), filename)

@app.route("/static/module/unpoly/<path:filename>")
@noindex
def serve_module_unpoly(filename:str):
    return send_from_directory(os.path.join("node_modules", "unpoly"), filename)

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

@app.route("/user/<path:username>/feed")
def view_user_feed(username:str):
    if (user := load_user(username)):
        response = make_response(render_template("user-feed.xml", user=user, collections=walk_collections(username), load_item=load_item))
        response.headers["Content-Type"] = "application/atom+xml"
        return response
    else:
        abort(404)

@app.route("/search")
def search():
    query = request.args.get("query", "").lower()
    found = False
    results = []
    for item in walk_items():
        if any([query in (value if type(value) == str else list_to_wsv(value)).lower() for value in item.values()]):
            results.append(item)
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
    if form.validate_on_submit() and (user := load_user(form.username.data)):
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
            login_user(user, remember=bool(form.remember.data))
            next_url = urllib.parse.urlparse(request.args.get("next", ""))
            next_url = next_url.path + (f"?{next_url.query}" if next_url.query else "")
            return redirect(next_url or url_for("index"))
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

@app.route("/api/duplicates", methods=["POST"])
@noindex
@login_required
def check_duplicates():
    ...

@app.route("/api/collections/<path:iid>", methods=["GET", "POST"])
@noindex
@login_required
def collections_api(iid:str):
    if request.method == "POST":
        for collection, status in request.get_json().items():
            toggle_in_collection(current_user.username, collection, iid, status)
    results: dict[str, bool] = {}
    for folder, collection in walk_collections(current_user.username).items():
        results[folder] = iid in collection
    return results

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
def login_user_loader(userhash:str) -> User|None:
    username = userhash.split(":")[0]
    if (user := load_user(username)):
        if userhash == generate_user_hash(username, user.data["password"]):
            return user
    return None

@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return {"error": "Unauthorized"}, 401
    else:
        flash("Please log in to access this page.")
        return redirect(login_url("login", request.url))

def load_user(username:str) -> User|None:
    filepath = os.path.join(USERS_ROOT, (username + ITEMS_EXT))
    if os.path.exists(filepath):
        return User(username, filepath)
    return None

mkdirs(ITEMS_ROOT, USERS_ROOT)

if __name__ == "__main__":
    if DEVELOPMENT:
        app.run(port=HTTP_PORT, debug=True)
    else:
        import waitress
        waitress.serve(app, port=HTTP_PORT, threads=HTTP_THREADS)
