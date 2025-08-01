import os
import time
import urllib.parse
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from typing import Any, cast
from random import shuffle
from glob import glob
from flask import Flask, request, redirect, render_template, send_from_directory, send_file, abort, url_for, flash, session, make_response
from flask_bcrypt import Bcrypt # type: ignore[import-untyped]
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required, login_url # type: ignore[import-untyped]
from flask_wtf import FlaskForm # type: ignore[import-untyped]
from wtforms import StringField, PasswordField, BooleanField, SubmitField # type: ignore[import-untyped]
from wtforms.validators import DataRequired # type: ignore[import-untyped]
from werkzeug.utils import safe_join
from _app_factory import app
from _pignio import *
from _functions import *
from _util import *

# config #
DEVELOPMENT = False
HTTP_PORT = 5000
HTTP_THREADS = 32
LINKS_PREFIX = ""
RESULTS_LIMIT = 50
AUTO_OCR = True
INSTANCE_NAME = ""
INSTANCE_DESCRIPTION = ""
ALLOW_REGISTRATION = False
# ALLOW_FEDERATION = False
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

app.jinja_env.globals["_"] = gettext
app.config["DEVELOPMENT"] = DEVELOPMENT
app.config["SECRET_KEY"] = SECRET_KEY
app.config["BCRYPT_HANDLE_LONG_PASSWORDS"] = True

app.config["LINKS_PREFIX"] = LINKS_PREFIX
app.config["APP_NAME"] = "Pignio"
app.config["APP_ICON"] = "📌"
app.config["APP_DESCRIPTION"] = "Pignio is your personal self-hosted media pinboard, built on top of flat-file storage."
app.config["INSTANCE_NAME"] = INSTANCE_NAME or app.config["APP_NAME"]
app.config["INSTANCE_DESCRIPTION"] = INSTANCE_DESCRIPTION or app.config["APP_DESCRIPTION"]
app.config["ALLOW_REGISTRATION"] = ALLOW_REGISTRATION
app.config["SITE_VERIFICATION"] = SITE_VERIFICATION

login_manager = LoginManager()
login_manager.login_view = "view_login"
login_manager.init_app(app)
bcrypt = Bcrypt(app)

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField()
    submit = SubmitField("Login")

class RegisterForm(LoginForm):
    password2 = PasswordField("Confirm Password", validators=[DataRequired()])
    submit = SubmitField("Register")

@app.route("/")
def view_index():
    return view_random_items(request)

@app.route("/.well-known/nodeinfo")
@noindex
def serve_nodeinfo():
    return {
        "links": [
            {
                "rel": "http://nodeinfo.diaspora.software/ns/schema/2.1",
                "href": render_template("links-prefix.txt") + "/nodeinfo/2.1",
            },
        ],
    }

@app.route("/nodeinfo/2.1")
@noindex
def serve_nodeinfo_21():
    return {
        "version": "2.1",
        "software": {
            "name": app.config["APP_NAME"],
            "repository": "https://gitlab.com/octospacc/Pignio",
        },
        "services": {
            "outbound": ["atom1.0"],
        },
        "openRegistrations": app.config["ALLOW_REGISTRATION"],
        "usage": {
            "users": {
                "total": len(glob(f"{USERS_ROOT}/*.ini")),
            },
            "localPosts": count_items(),
        },
        "metadata": {
            "nodeName": app.config["INSTANCE_NAME"],
            "nodeDescription": app.config["INSTANCE_DESCRIPTION"],
        },
    }

@app.route("/.well-known/webfinger")
@noindex
@query_params("resource")
def webfinger(resource:str):
    prefix = render_template("links-prefix.txt")
    if not resource.startswith("acct:") or \
       not resource.endswith("@" + urllib.parse.urlparse(prefix).netloc) or \
       not (user := load_user(resource.split(":")[1].split("@")[0])):
        return abort(400)
    user_url = prefix + url_for("view_user", username=user.username)
    return {
        "subject": resource,
        "aliases": [user_url],
        "links": [
            {
                "rel": "http://webfinger.net/rel/profile-page",
                "type": "text/html",
                "href": user_url,
            },
            {
                "rel": "http://schemas.google.com/g/2010#updates-from",
                "type": "application/atom+xml",
                "href": prefix + url_for("view_user_feed", username=user.username),
            },
            # {
            #     "rel": "self",
            #     "type": "application/activity+json",
            #     "href": user_url,
            # },
            # {
            #     "rel": "http://webfinger.net/rel/avatar",
            #     "type": "image/jpeg",
            #     "href": ...,
            # },
        ],
    }

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

@app.route("/item/<path:iid>", methods=["GET", "POST"])
def view_item(iid:str):
    has_subitems = (dirpath := safe_join(ITEMS_ROOT, iid)) and os.path.isdir(dirpath)
    if (item := load_item(iid)) and get_item_permissions(item)["view"]:
        if request.method == "GET":
            if safe_str_get(cast(dict, item), "type") != "comment":
                if request.headers.get("Accept") == "application/activity+json":
                    return make_activitypub_item(item)
                else:
                    comments = walk_items(iid_to_filename(iid))
                    comments.reverse()
                    return render_template("item.html", item=item, comments=comments, get_item_permissions=get_item_permissions)
            else:
                [*item_toks, cid] = iid.split("/")
                return redirect(url_for("view_item", iid="/".join(item_toks)) + f"#{cid}")
        elif request.method == "POST" and current_user.is_authenticated and (comment := request.form.get("comment")):
            store_item(f"{iid_to_filename(iid)}/{generate_iid()}", {"text": comment}, comment=True)
            return redirect(url_for("view_item", iid=iid))
    elif has_subitems:
        return view_random_items(request, iid)
    return abort(404)

@app.route("/user/<path:username>")
def view_user(username:str):
    if (user := load_user(username)):
        if request.headers.get("Accept") == "application/activity+json":
            return make_activitypub_user(user)
        else:
            return render_template("user.html", user=user, collections=walk_collections(user.username), load_item=load_item)
    else:
        return abort(404)

@app.route("/user/<path:username>/feed")
def view_user_feed(username:str):
    if (user := load_user(username)):
        limit = int(request.args.get("limit") or 100)
        response = make_response(render_template("user-feed.xml", user=user, collections=walk_collections(username), limit=limit, load_item=load_item))
        response.headers["Content-Type"] = "application/atom+xml"
        return response
    else:
        return abort(404)

@app.route("/search")
def search():
    query = request.args.get("query", "").lower()
    found = False
    results = []
    for item in walk_items():
        if item and any([query in (value if type(value) == str else list_to_wsv(value)).lower() for value in item.values()]):
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
            if not (item := load_item(iid)) or not get_item_permissions(item)["edit"]:
                return abort(404)
    elif request.method == "POST":
        iid = request.form.get("id") or generate_iid()
        data = {key: request.form[key] for key in request.form}
        for key in ["langs"]:
            if key in data and type(data[key]) != list:
                data[key] = request.form.getlist(key)
        if store_item(iid, data, request.files, AUTO_OCR):
            return redirect(url_for("view_item", iid=iid))
        else:
            flash("Cannot save item", "danger")
    return render_template("add.html", item=item)

@app.route("/delete", methods=["GET", "POST"])
@noindex
@login_required
def remove_item():
    if request.method == "GET":
        iid = request.args.get("item")
    elif request.method == "POST":
        iid = request.form.get("id")
    if iid and (item := load_item(iid)) and get_item_permissions(item)["edit"]:
        if request.method == "GET":
            return render_template("delete.html", item=item, mode="Delete")
        elif request.method == "POST":
            delete_item(item)
            parent_iid = "/".join(iid.split("/")[:-1])
            return redirect(url_for("view_item", iid=parent_iid) if parent_iid else url_for("view_index"))
    return abort(404)

@app.route("/report", methods=["GET", "POST"])
@noindex
@login_required
def report_item():
    if request.method == "GET":
        iid = request.args.get("item")
    elif request.method == "POST":
        iid = request.form.get("id")
    if iid and (item := load_item(iid)) and (permissions := get_item_permissions(item)) and permissions["view"] and not permissions["edit"]:
        if request.method == "GET":
            return render_template("delete.html", item=item, mode="Report")
        elif request.method == "POST":
            moderation_queue.put(f"report@{time.time()}:{iid},{current_user.username}")
            return redirect(url_for("view_item", iid=iid))
    return abort(404)

@app.route("/notifications")
@noindex
@login_required
def view_notifications():
    return pagination("notifications.html", "events", load_events(current_user))

@app.route("/login", methods=["GET", "POST"])
@noindex
def view_login():
    if current_user.is_authenticated:
        return redirect(url_for("view_index"))
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
            return init_user_session(user, form.remember.data)
    if request.method == "POST":
        flash("Invalid username or password", "danger")
    return render_template("login.html", form=form, mode="Login")

@app.route("/register", methods=["GET", "POST"])
@noindex
def view_register():
    if not app.config["ALLOW_REGISTRATION"]:
        return abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("view_index"))
    form = RegisterForm()
    if form.validate_on_submit() and (username := form.username.data) and not (user := load_user(username)) and form.password.data == form.password2.data:
        write_textual(safe_join(USERS_ROOT, (slugify_name(username) + ITEMS_EXT)), write_metadata({
            "password": bcrypt.generate_password_hash(form.password.data).decode("utf-8"),
        }))
        return init_user_session(load_user(username), form.remember.data)
    if request.method == "POST":
        flash("Invalid username or password", "danger")
    return render_template("login.html", form=form, mode="Register")

@app.route("/logout")
@noindex
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("view_index"))

@app.route("/api/duplicates", methods=["POST"])
@noindex
@login_required
def check_duplicates():
    ...

@app.route("/api/export")
@noindex
@login_required
def export_api():
    file = BytesIO()
    with ZipFile(file, "w", ZIP_DEFLATED, compresslevel=9) as zipf:
        userbase = os.path.join(USERS_ROOT, current_user.username)
        zipf.write(f"{userbase}.ini")
        for filename in glob(f"{userbase}/*.ini"):
            zipf.write(filename)
        for item in walk_items():
            if item and safe_str_get(item, "creator") == current_user.username:
                filename = os.path.join(ITEMS_ROOT, iid_to_filename(item["id"]))
                for filename in glob(f"{filename}.*"):
                    zipf.write(filename)
    file.seek(0)
    return send_file(file, "application/zip", True, f"{current_user.username}.zip")

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
    if request.method == "GET" and (item := load_item(iid)) and get_item_permissions(item)["view"]:
        return item
    elif request.method == "POST" or request.method == "PUT":
        iid = iid or generate_iid()
        status = store_item(iid, request.get_json(), None, AUTO_OCR)
        return {"id": iid if status else None}
    elif request.method == "DELETE" and get_item_permissions(iid)["edit"]:
        delete_item(iid)
        return {}

@app.route("/api/slugify")
@noindex
@query_params("text")
def slugify_api(text:str):
    return slugify_name(text)

@app.route("/api/preview")
@noindex
@login_required
@query_params("url")
def preview_api(url:str):
    return fetch_url_data(url)

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
        return redirect(login_url("view_login", request.url))

@app.before_request
def remove_trailing_slash():
    if request.path != "/" and request.path.endswith("/"):
        return redirect(request.path.rstrip("/"))

@app.errorhandler(404)
def error_404(e):
    return render_template("404.html"), 404

def view_random_items(request, root:str|None=None):
    return pagination("index.html", "items", walk_items(root), (lambda items: shuffle(items)), root=root)

def pagination(template:str, key:str, all_items:list, modifier=None, **kwargs):
    page = int(request.args.get("page") or 1)
    next_count = (RESULTS_LIMIT * page)
    items = all_items[(RESULTS_LIMIT * (page - 1)):next_count]
    if len(items) == 0 and len(all_items) > 0:
        return abort(404)
    if modifier:
        modifier(items)
    return render_template(template, **kwargs, **{key: items}, next_page=(page + 1 if len(all_items) > next_count else None))

mkdirs(ITEMS_ROOT, USERS_ROOT)

if __name__ == "__main__":
    if DEVELOPMENT:
        app.run(port=HTTP_PORT, debug=True)
    else:
        import waitress
        waitress.serve(app, port=HTTP_PORT, threads=HTTP_THREADS)
