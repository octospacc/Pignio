import os
import time
import urllib.parse
import subprocess
import ffmpeg # type: ignore[import-untyped]
from hashlib import sha256
from shutil import rmtree, move, copyfile
from typing import Any, cast
from random import shuffle
from base64 import urlsafe_b64decode
from datetime import datetime
from glob import glob
from PIL import Image, ImageFile
from flask import Flask, request, redirect, render_template, send_from_directory, send_file, abort, url_for, flash, session, make_response
from flask_bcrypt import Bcrypt # type: ignore[import-untyped]
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, login_url, current_user # type: ignore[import-untyped]
from flask_wtf import FlaskForm # type: ignore[import-untyped]
from wtforms import StringField, PasswordField, BooleanField, SubmitField # type: ignore[import-untyped]
from wtforms.validators import DataRequired # type: ignore[import-untyped]
from werkzeug.utils import safe_join
from secrets import token_urlsafe
from _app_factory import app
from _util import *
from _pignio import *
from _functions import *
from _features import *

FFMPEG_AVAILABLE = check_ffmpeg_available()

app.jinja_env.globals["_"] = gettext
app.jinja_env.globals["getlang"] = getlang
app.jinja_env.globals["gettheme"] = gettheme
app.jinja_env.globals["clean_url_for"] = clean_url_for
app.jinja_env.globals["ATOM_CONTENT_TYPE"] = ATOM_CONTENT_TYPE
app.config["DEVELOPMENT"] = Config.DEVELOPMENT
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["BCRYPT_HANDLE_LONG_PASSWORDS"] = True

app.config["FREEZING"] = False
app.config["LINKS_PREFIX"] = Config.LINKS_PREFIX
app.config["APP_NAME"] = "Pignio"
app.config["APP_ICON"] = "📌"
app.config["APP_REPO"] = "https://gitlab.com/octospacc/Pignio"
app.config["APP_DESCRIPTION"] = "Pignio is your personal self-hosted media pinboard, built on top of flat-file storage."
app.config["INSTANCE_NAME"] = Config.INSTANCE_NAME or app.config["APP_NAME"]
app.config["INSTANCE_DESCRIPTION"] = Config.INSTANCE_DESCRIPTION or app.config["APP_DESCRIPTION"]
app.config["ALLOW_REGISTRATION"] = Config.ALLOW_REGISTRATION
app.config["SITE_VERIFICATION"] = Config.SITE_VERIFICATION
app.config["CONFIG"] = Config
app.config["FFMPEG_AVAILABLE"] = FFMPEG_AVAILABLE
app.config["VIDEO_THUMBS"] = FFMPEG_AVAILABLE and Config.USE_THUMBNAILS

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
# @auth_required_config(False) # Restrict_Index
def view_index():
    return view_random_items()

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
            "repository": app.config["APP_REPO"],
        },
        # "protocols": ["activitypub"],
        "services": {
            "outbound": ["atom1.0"],
        },
        "openRegistrations": app.config["ALLOW_REGISTRATION"],
        "usage": {
            "users": {
                "total": count_users(),
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
    if not resource or \
       not resource.startswith("acct:") or \
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
                "type": ATOM_CONTENT_TYPE,
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
    return response_with_type(render_template("manifest.json"), "application/json")

@app.route("/static/module/uikit/<path:filename>")
@noindex
def serve_module_uikit(filename:str):
    return send_from_directory(os.path.join("node_modules", "uikit", "dist"), filename)

@app.route("/static/module/unpoly/<path:filename>")
@noindex
def serve_module_unpoly(filename:str):
    return send_from_directory(os.path.join("node_modules", "unpoly"), filename)

@app.route("/static/module/simplelightbox/<path:filename>")
@noindex
def serve_module_simplelightbox(filename:str):
    return send_from_directory(os.path.join("node_modules", "simplelightbox", "dist"), filename)

@app.route("/media/<path:filename>")
def serve_media(filename:str):
    return send_from_directory(ITEMS_ROOT, filename)

@app.route("/thumb/<path:iid>")
def serve_thumb(iid:str):
    if Config.USE_THUMBNAILS and (item := load_item(iid)):
        image = item.get("image")
        video = FFMPEG_AVAILABLE and item.get("video")
        if video:
            filename = f'{item["id"]}.gif'
            filepath = os.path.join(CACHE_ROOT, filename)
            if Config.THUMBNAIL_CACHE and os.path.exists(filepath):
                return send_from_directory(CACHE_ROOT, filename)
            else:
                streams = (ffmpeg
                    ).input(os.path.join(ITEMS_ROOT, video), t=VIDEO_THUMB_DURATION
                    ).video.filter("fps", VIDEO_THUMB_FPS
                    ).filter("scale", VIDEO_THUMB_WIDTH, -1, flags="lanczos"
                    ).filter_multi_output("split")
                gif = ffmpeg.filter([streams[1], streams[0].filter("palettegen")], "paletteuse", dither="none")
                if Config.THUMBNAIL_CACHE:
                    mkdirs(os.path.dirname(filepath))
                    ffmpeg.output(gif, filepath, format="gif").run()
                    return send_from_directory(CACHE_ROOT, filename)
                else:
                    return send_file(BytesIO(ffmpeg.output(gif, 'pipe:1', format="gif").run(capture_stdout=True)[0]), f"image/gif")
        elif image:
            if image.lower().endswith(".gif"):
                return redirect(url_for("serve_media", filename=image))
            filename = f'{item["id"]}.{THUMB_TYPE}'
            filepath = os.path.join(CACHE_ROOT, filename)
            if Config.THUMBNAIL_CACHE and os.path.exists(filepath):
                return send_from_directory(CACHE_ROOT, filename)
            else:
                pil = Image.open(os.path.join(ITEMS_ROOT, image))
                if pil.width > THUMB_WIDTH:
                    pil = pil.resize((THUMB_WIDTH, int(pil.height * (THUMB_WIDTH / float(pil.width)))), Image.LANCZOS) # type: ignore[assignment, attr-defined]
                pil = pil.convert("RGBA") # type: ignore[assignment]
                ImageFile.MAXBLOCK = pil.size[0] * pil.size[1]
                if Config.THUMBNAIL_CACHE:
                    mkdirs(os.path.dirname(filepath))
                    pil.save(filepath, format=THUMB_TYPE, quality=THUMB_QUALITY, optimize=True, progressive=True)
                    return send_from_directory(CACHE_ROOT, filename)
                else:
                    buffer = BytesIO()
                    pil.save(buffer, format=THUMB_TYPE, quality=THUMB_QUALITY, optimize=True, progressive=True)
                    buffer.seek(0)
                    return send_file(buffer, f"image/{THUMB_TYPE}")
    return abort(404)

@app.route("/render/<path:iid>")
def render_media(iid:str):
    if (item := load_item(iid)) and (text := item.get("text")):
        filename = f'{item["id"]}.{RENDER_TYPE}'
        filepath = os.path.join(CACHE_ROOT, filename)
        if Config.RENDER_CACHE and os.path.exists(filepath):
            return send_from_directory(CACHE_ROOT, filename)
        else:
            args = ["node", "render.js"]
            if (background := item.get("image")):
                args.append(os.path.join(ITEMS_ROOT, background))
            image, err = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate(input=text.encode("utf-8"))
            if Config.RENDER_CACHE:
                mkdirs(os.path.dirname(filepath))
                with open(filepath, "wb") as f:
                    f.write(image) # TODO handle creation of parent directories when necessary
            return response_with_type(image, f"image/{RENDER_TYPE}")
    return abort(404)

@app.route("/model-viewer/<path:iid>")
def model_viewer(iid:str):
    return view_embedded(iid, "model-viewer", "model", lambda item: {"poster": item.get("image")})

@app.route("/font-viewer/<path:iid>")
def font_viewer(iid:str):
    return view_embedded(iid, "font-viewer", "font")

@app.route("/flash-player/<path:iid>")
def flash_player(iid:str):
    return view_embedded(iid, "ruffle", "swf")

@app.route("/emulator-player/<path:iid>")
def emulator_player(iid:str):
    return view_embedded(iid, "emulatorjs", "rom")

@app.route("/item/<path:iid>", methods=["GET", "POST"])
# @auth_required_config(False) # Restrict_Items
def view_item(iid:str, embed:bool=False):
    if (item := load_item(iid)) and get_item_permissions(item)["view"]:
        if request.method == "GET":
            if safe_str_get(cast(dict, item), "type") != "comment":
                if is_for_activitypub():
                    return make_activitypub_item(item)
                else:
                    comments = walk_items(iid_to_filename(iid))
                    comments.reverse()
                    return render_template("item.html", embed=embed, item=item, comments=comments, get_item_permissions=get_item_permissions, time=time.time())
            else:
                [*item_toks, cid] = iid.split("/")
                return redirect(url_for("view_item", iid="/".join(item_toks)) + f"#{cid}")
        elif request.method == "POST" and current_user.is_authenticated and (comment := request.form.get("comment")):
            store_item(f"{iid_to_filename(iid)}/{generate_iid()}", {"text": comment}, comment=True)
            return redirect(url_for("view_item", iid=iid))
    elif not embed and has_subitems_directory(iid):
        return view_orderable_items(iid)
    return abort(404)

# TODO: also add @app.route("/@<path:username>"), redirecting to main url of user ?
@app.route("/user/<path:username>")
@app.route("/user/<path:username>/<path:cid>")
# @auth_required_config(False) # Restrict_Users
def view_user(username:str, cid:str|None=None):
    userparts = username.lstrip("@").split("@")
    if len(userparts) > 1:
        if (user := load_remote_user(*userparts)):
            if is_for_activitypub():
                return redirect(user.json_url)
            elif current_user.is_authenticated:
                return render_template("user.html", user=user, collections={})
            else:
                return redirect(user.url)
    elif (user := load_user(userparts[0])):
        if is_for_activitypub():
            return make_activitypub_user(user)
        else:
            mode = request.args.get("mode")
            if mode == "all":
                pinned = [item for folder in walk_collections(user.username).values() for item in folder["items"]]
                created = [item for item in sort_items(walk_items(creator=user.username)) if item["id"] not in pinned]
                return pagination("user.html", "items", created+pinned, user=user, load_item=load_item, mode=mode)
            elif mode == "created":
                return pagination("user.html", "items", sort_items(walk_items(creator=user.username)), user=user, load_item=load_item, mode=mode)
            elif mode == "comments":
                if current_user.is_authenticated and current_user.username == user.username:
                    comments = sort_items(walk_items(creator=user.username, comments=True))
                    for comment in comments:
                        tokens = comment['id'].split('/')
                        comment['iid'] = '/'.join(tokens[:-1])
                        comment['cid'] = tokens[-1]
                    return pagination("user.html", "comments", comments, user=user, load_item=load_item, mode=mode)
                else:
                    return abort(404)
            else:
                description = None
                collections = walk_collections(user.username)
                pinned = collections.pop("")
                folders = make_folders(collections)
                if cid:
                    if (pinned := collections.get(cid)):
                        description = pinned["description"]
                        folders = []
                    else:
                        return abort(404)
                return pagination("user.html", "items", pinned["items"], user=user, name=cid, description=description, folders=folders, load_item=load_item, mode=mode)
    return abort(404)

@app.route("/user/<path:username>/feed") # TODO deprecate this which could conflict with collections
@app.route("/feed/user/<path:username>")
@noindex
def view_user_feed(username:str):
    if (user := load_user(username)):
        return feed_response("user-feed", user=user, collections=walk_collections(username), load_item=load_item)
    else:
        return abort(404)

@app.route("/feed/item/<path:fid>")
@noindex
def view_folder_feed(fid:str):
    if is_items_folder(fid):
        return feed_response("folder-feed", folder=fid, items=walk_items(fid))
    else:
        return abort(404)

@app.route("/embed/<path:kind>/<path:path>")
@noindex
def view_embed(kind:str, path:str):
    if kind == "item":
        return view_item(path, True)
    # elif kind == "user": ...
    else:
        return abort(404)

@app.route("/search")
@noindex
# @auth_required_config(False) # Restrict_Search
def search():
    query_raw = query = request.args.get("query", "")
    cased = parse_bool(request.args.get("cased"))
    field = request.args.get("field", "")
    creators = request.args.get("creators", "").lower().replace("+", " ").replace(",", " ").split()
    if not cased:
        query = query.lower()
    results = []
    for item in walk_items():
        if field:
            value = item.get(field, "")
            if query in (value if type(value) == str else list_to_wsv(value)).lower():
                results.append(item)
        elif any([query in (value if type(value) == str else list_to_wsv(value)).lower() for value in item.values()]):
            results.append(item)
    if len(creators) > 0:
        results = list(filter(lambda item: item.get("creator") in creators, results))
    return pagination("search.html", "items", results, query=query_raw, cased=cased, field=field, creators=", ".join(creators))

@app.route("/trim", methods=["GET", "POST"])
@query_params("iid")
@extra_login_required
def media_trim(iid:str):
    if FFMPEG_AVAILABLE and (item := load_item(iid)) and ((video := item.get("video")) or ((audio := item.get("audio")) and not audio.lower().endswith((".mid", ".midi")))) and (perms := get_item_permissions(item))["view"]:
        if request.method == "GET":
            return render_template("media-trim.html", item=item, can_overwrite=perms["edit"])
        elif request.method == "POST" and (action := request.form.get("action")):
            media_path = os.path.join(ITEMS_ROOT, video or audio)
            media_ext = (video or audio).split('.')[-1]
            temp_path = os.path.join(TEMP_ROOT, f"{time.time()}-{sha256((video or audio).encode()).hexdigest()}.{media_ext}")
            mkdirs(TEMP_ROOT)
            (ffmpeg
                ).input(media_path, ss=request.form.get("start")
                ).output(temp_path, to=request.form.get("end"), c="copy"
                ).run(overwrite_output=True)
            if action == "save" and perms["edit"]:
                if Config.USE_BAK_FILES:
                    copyfile(media_path, f"{media_path}.bak")
                move(temp_path, media_path)
                return redirect(url_for("view_item", iid=item["id"]))
            elif action == "copy":
                new_iid = generate_iid()
                new_path = os.path.join(ITEMS_ROOT, iid_to_filename(new_iid))
                old_ini = os.path.join(ITEMS_ROOT, iid_to_filename(item["id"]) + ITEMS_EXT)
                move(temp_path, f"{new_path}.{media_ext}")
                if os.path.exists(old_ini):
                    copyfile(old_ini, new_path + ITEMS_EXT)
                toggle_in_collection(current_user.username, "", new_iid, True)
                return redirect(url_for("view_item", iid=new_iid))
    else:
        return abort(404)

@app.route("/join", methods=["GET", "POST"])
@extra_login_required
def video_join():
    if not FFMPEG_AVAILABLE:
        return abort(404)
    iids = request.args.getlist("iid")
    if request.method == "POST":
        iids = list(filter(lambda iid: iid.strip(), request.form.get("iids").splitlines()))
        if len(iids) < 2:
            flash("You must specify 2 or more videos to join", "danger")
        else:
            items = []
            for iid in iids:
                if (item := load_item(iid)) and (video := item.get("video")) and get_item_permissions(item)["view"]:
                    items.append(item)
                else:
                    items = []
                    flash("One or more of the specified items is not available", "danger")
            if len(items) >= 2:
                iid = generate_iid()
                item_path = os.path.join(ITEMS_ROOT, iid_to_filename(iid))
                (ffmpeg
                    ).concat(*[stream for item in items for stream in [ffmpeg.input(os.path.join(ITEMS_ROOT, item["video"]))] for stream in [stream.video, stream.audio]], v=1, a=1
                    ).output(item_path + ".mp4"
                    ).run(overwrite_output=True)
                write_textual(item_path + ITEMS_EXT, write_metadata({"description": "Joined from " + " + ".join(iids)}))
                toggle_in_collection(current_user.username, "", iid, True)
                return redirect(url_for("view_item", iid=iid))
    return render_template("video-join.html", iids=iids)

@app.route("/add", methods=["GET", "POST"])
@extra_login_required
def add_item():
    item = {}
    if request.method == "GET":
        if (iid := request.args.get("item")):
            if not (item := load_item(iid)) or not get_item_permissions(item)["edit"]:
                return abort(404)
    elif request.method == "POST":
        iid = request.form.get("id") or generate_iid()
        data = {key: request.form[key] for key in request.form}
        for key in ["langs", "collections"]:
            if key in data and type(data[key]) != list:
                data[key] = request.form.getlist(key)
        if store_item(iid, data, request.files, Config.AUTO_OCR):
            return redirect(url_for("view_item", iid=iid))
        else:
            flash("Cannot save item", "danger")
    return render_template("add.html", item=item, collections=walk_collections(current_user.username))

@app.route("/delete", methods=["GET", "POST"])
@extra_login_required
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
@extra_login_required
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
@extra_login_required
def view_notifications():
    return pagination("notifications.html", "events", load_events(current_user))

@app.route("/settings", methods=["GET", "POST"])
@extra_login_required
def view_settings():
    user = load_user(current_user.username)
    tokens = []
    tokens_raw = user.data.get("tokens", [])
    tokens_changed = False
    # webhooks_changed = False
    if request.method == "POST":
        match request.form.get("action"):
            case "create-token":
                token = token_urlsafe()
                hashed = hash_api_token(token)
                tokens_raw.append(f"{time.time()}:{hashed}")
                tokens_changed = True
                flash(f'{gettext("created-token")}: ({urlsafe_b64decode(hashed).hex()[:16]}) <input class="uk-input" style="width: 100%;" type="text" value="{user.username}:{token}" readonly />', "primary")
            case "delete-token" if (hashed := request.form.get("token")) and (token := check_user_token(tokens_raw, hashed)):
                tokens_raw.remove(token)
                tokens_changed = True
                flash(gettext("deleted-token"))
            # case "create-webhook":
            # case "delete-webhook":
    for token in tokens_raw:
        [timestamp, hashed] = token.split(":")
        tokens.append({"date": datetime.fromtimestamp(float(timestamp)), "hash": hashed, "name": urlsafe_b64decode(hashed).hex()[:16]})
    if tokens_changed:
        user.data["tokens"] = tokens_raw
        user.save()
    tokens.reverse()
    return render_template("settings.html", tokens=tokens)

@app.route("/stats")
@noindex
def view_stats():
    return render_template("stats.html", items=count_items(), users=count_users())

@app.route("/admin", methods=["GET", "POST"])
@extra_login_required
def view_admin():
    if current_user.is_admin:
        if request.method == "POST":
            match request.form.get("action"):
                case "clear-cache":
                    if os.path.exists(CACHE_ROOT):
                        rmtree(CACHE_ROOT)
                    flash(f'{gettext("Cache cleared")}!')
                case "clear-bak-files":
                    files = glob(f"{DATA_ROOT}/**/*.bak", recursive=True)
                    for file in files:
                        os.remove(file)
                    flash(f'{gettext("BAK files cleared")}! ({len(files)})')
                case "clear-temp-files":
                    if os.path.exists(TEMP_ROOT):
                        rmtree(TEMP_ROOT)
                    flash(f'{gettext("Temp files cleared")}!')
        return render_template("admin.html")
    else:
        abort(404)

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
                user.save()
            return init_user_session(user, form.remember.data)
    if request.method == "POST":
        flash(gettext("login-invalid"), "danger")
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
        user = User(username := slugify_name(username), safe_join(USERS_ROOT, (username + ITEMS_EXT)))
        user.data["password"] = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user.save()
        return init_user_session(user, form.remember.data)
    if request.method == "POST":
        flash(gettext("login-invalid"), "danger")
    return render_template("login.html", form=form, mode="Register")

@app.route("/logout")
@noindex
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("view_index"))

@app.route("/setprefs", methods=["POST"])
@noindex
def set_http_prefs():
    theme = gettheme()
    if request.form.get("option") == "theme":
        theme = "light" if gettheme() == "dark" else "dark"
    return setprefs(lang=request.form.get("lang"), theme=theme)

@app.route("/api/v0/duplicates", methods=["POST"])
@extra_login_required
def check_duplicates():
    ...

@app.route("/api/v0/export")
@auth_required
def export_api():
    username = current_user.username
    userbase = os.path.join(USERS_ROOT, username)
    files = [[f"{userbase}.ini"], *[[filename] for filename in glob(f"{userbase}/*.ini")]]
    for item in walk_items(creator=username):
        filename = os.path.join(ITEMS_ROOT, iid_to_filename(item["id"]))
        for filename in glob(f"{filename}.*"):
            files.append([filename])
    return send_zip_archive(username, files)

@app.route("/api/v0/download/<path:fid>")
@auth_required
def download_api(fid:str):
    if (dirpath := is_items_folder(fid)):
        results = []
        for root, dirs, files in os.walk(dirpath):
            for file in files:
                if check_file_supported(file):
                    filepath = os.path.join(root, file)
                    results.append([filepath, os.path.relpath(filepath, dirpath)])
        return send_zip_archive(dirpath, results)
    else:
        return abort(404)

@app.route("/api/v0/collections/<path:iid>", methods=["GET", "POST"])
@auth_required
def collections_api(iid:str):
    username = current_user.username
    if request.method == "POST":
        for collection, status in request.get_json().items():
            toggle_in_collection(username, slugify_name(collection), iid, status)
    results: dict[str, bool] = {}
    for cid, collection in walk_collections(username).items():
        results[cid] = iid in collection["items"]
    return results

@app.route("/api/v1/items", defaults={"iid": None}, methods=["GET", "POST"])
@app.route("/api/v1/items/<path:iid>", methods=["GET", "PUT", "DELETE"])
@auth_required
def items_api(iid:str|None):
    if request.method == "GET":
        if not iid:
            return walk_items()
        elif (item := load_item(iid)) and get_item_permissions(item)["view"]:
            return item
    elif not app.config["FREEZING"]:
        if request.method == "POST" or request.method == "PUT":
            iid = iid or generate_iid()
            status = store_item(iid, request.get_json(), None, Config.AUTO_OCR)
            return {"id": iid if status else None}
        elif iid and request.method == "DELETE" and get_item_permissions(iid)["edit"]:
            delete_item(iid)
            return {}
    return abort(404)

@app.route("/api/v0/slugify")
@noindex
@query_params("text")
def slugify_api(text:str):
    return slugify_name(text)

@app.route("/api/v0/preview")
@extra_login_required
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
        flash(gettext("login-to-access"))
        return redirect(login_url("view_login", request.url))

@app.before_request
def remove_trailing_slash():
    if request.path != "/" and request.path.endswith("/"):
        return redirect(request.path.rstrip("/"))

@app.after_request
def request_headers(response):
    if request.endpoint != "view_embed":
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response

@app.errorhandler(400)
def error_400(e):
    return render_template("error.html", code=400, name="Bad Request", description="The browser (or proxy) sent a request that this server could not understand."), 400

@app.errorhandler(404)
def error_404(e):
    return render_template("error.html", code=404, name=gettext("Not Found"), description="The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again."), 404

def feed_response(template:str, **kwargs:Any):
    return response_with_type(render_template(f"{template}.xml", limit=int(request.args.get("limit") or Config.RESULTS_LIMIT), content_type=ATOM_CONTENT_TYPE, **kwargs), ATOM_CONTENT_TYPE)

def view_orderable_items(root:str):
    if (ordering := request.args.get("ordering")) == "natural" or app.config["FREEZING"]:
        return pagination("index.html", "items", walk_items(root), root=root, folders=list_folders(root), ordering=ordering)
    else:
        return view_random_items(root)

def view_random_items(root:str|None=None):
    return pagination("index.html", "items", walk_items(root), (lambda items: shuffle(items)), root=root, folders=(list_folders(root) if root else []))

def pagination(template:str, key:str, all_items:list, modifier=None, **kwargs):
    page = int(request.args.get("page") or 1)
    limit = int(request.args.get("limit") or Config.RESULTS_LIMIT)
    next_count = (limit * page)
    items = all_items[(limit * (page - 1)):next_count]
    if len(items) == 0 and len(all_items) > 0:
        return abort(404)
    if modifier:
        modifier(items)
    return render_template(template, **kwargs, **{key: items}, limit=limit, next_page=(page + 1 if len(all_items) > next_count else None))

if __name__ == "__main__":
    print(f"Running Pignio on {Config.HTTP_HOST}:{Config.HTTP_PORT}...")

    if Config.DEVELOPMENT:
        app.run(host=Config.HTTP_HOST, port=Config.HTTP_PORT, debug=True)
    else:
        import waitress
        waitress.serve(app, host=Config.HTTP_HOST, port=Config.HTTP_PORT, threads=Config.HTTP_THREADS)
