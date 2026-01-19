import os
import json
import requests
import urllib.parse
import ffmpeg # type: ignore[import-untyped]
from io import BytesIO
from zipstream import ZipFile, ZIP_DEFLATED # type: ignore[import-untyped]
from bs4 import BeautifulSoup # type: ignore[import-untyped]
from functools import wraps
from typing import Callable, Any, Literal, cast
from base64 import b64decode, urlsafe_b64encode
from hashlib import sha256
from slugify import slugify
from jinja2 import Undefined
from flask import request, session, redirect, url_for, make_response, render_template, send_file, abort, Response
from flask_login import UserMixin, login_required, login_user, current_user # type: ignore[import-untyped]
from werkzeug.utils import safe_join
from _app_factory import app
from _util import *
from _pignio import *
from _media import check_ffmpeg_available
from _users import User, RemoteUser
# from _features import *

# class Item(DataContainer):
#     def __init__(self, data:ItemDict):
#         self.data = data

#     # def save(self):
#     #     write_textual(filepath + ITEMS_EXT, write_metadata(self.data))

def load_events(user:User) -> list[dict[str,str]]:
    events = []
    try:
        sources = wsv_to_list(read_textual(os.path.join(EVENTS_ROOT, user.username + LISTS_EXT)))
    except FileNotFoundError:
        sources = []
    if user.is_admin:
        sources += wsv_to_list(read_textual(MODERATION_LIST))
    for event in sources:
        events.append(parse_event(event))
    events = sorted(events, key=(lambda event: event["datetime"]))
    events.reverse()
    return events

def parse_event(text:str) -> dict[str,str]:
    [base, extra] = text.split(":")
    extra += ","
    [kind, time] = base.split("@")
    event = {"kind": kind, "datetime": str(datetime.fromtimestamp(float(time)))}
    if kind == "pin":
        [item, user, collection] = extra.split(",")[:3]
        event = event | {"item": item, "user": user, "collection": collection}
    else:
        [item, user] = extra.split(",")[:2]
        event = event | {"item": item, "user": user}
    return event

def redirect_next(strict:bool=False):
    if (next_arg := request.args.get("next", "")) or not strict:
        next_data = urllib.parse.urlparse(next_arg)
        next_url = next_data.path + (f"?{next_data.query}" if next_data.query else "")
        return redirect(next_url or url_for("view_index"))

def noindex(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        response = make_response(view_func(*args, **kwargs))
        response.headers["X-Robots-Tag"] = "noindex"
        return response
    return wrapped_view

def auth_required(func):
    @noindex
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs) if (current_user.is_authenticated or verify_token_auth() or app.config["FREEZING"]) else app.login_manager.unauthorized()
    return wrapped

def extra_login_required(func):
    @noindex
    @login_required
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapped

def auth_required_config(config_value:bool):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs) if not config_value or (current_user.is_authenticated or verify_token_auth()) else app.login_manager.unauthorized()
        return wrapper
    return decorator

def query_params(*param_names):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for name in param_names:
                kwargs[name] = request.args.get(name)
            return f(*args, **kwargs)
        return wrapper
    return decorator

def response_with_type(content, mime):
    response = make_response(content)
    response.headers["Content-Type"] = mime
    return response

def send_zip_archive(name:str, files:list) -> Response:
    zipf = ZipFile(mode="w", compression=ZIP_DEFLATED)
    for file in files:
        zipf.write(*file)
    response = Response(zipf, mimetype='application/zip')
    response.headers['Content-Disposition'] = f'attachment; filename={name}.zip'
    return response

def getlang() -> str:
    return getprefs().get("lang") or request.headers.get("Accept-Language", "en").split(",")[0].split("-")[0]

def gettheme() -> str|None:
    return getprefs().get("theme")

def gettext(key:str, lang:str|None=None) -> str:
    data = STRINGS.get(key) or {}
    return data.get(lang or getlang()) or data.get("en") or key

def getprefs() -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(request.cookies.get("prefs")).items()}

def setprefs(**props:Any) -> Response:
    if not (response := redirect_next(True)):
        response = make_response()
    response.set_cookie("prefs", urllib.parse.urlencode(getprefs() | props), max_age=(60 * 60 * 24 * 365 * 5))
    return response

def clean_url_for(endpoint:str, **values:Any) -> str:
    return url_for(endpoint, **{k: v for k, v in values.items() if not isinstance(v, Undefined)})

def is_for_activitypub():
    return (request.headers.get("Accept") in ACTIVITYPUB_TYPES)

def make_activitypub(id:str, kind:str, name:str, **kwargs) -> dict:
    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": kind,
        "id": render_template("links-prefix.txt") + id,
        "name": name,
        **kwargs,
    }

def make_activitypub_item(item:ItemDict) -> dict:
    attached = None
    if not (text := item.get("text")):
        text = item.get("description") or ""
        if (image := item.get("image")):
            attached = [{"type": "Image", "url": image}]
        elif (video := item.get("video")):
            attached = [{"type": "Video", "url": video}]
    if attached:
        attached[0]["url"] = render_template("links-prefix.txt") + url_for("serve_media", filename=attached[0]["url"])
    text = text.strip() + "\n\n" + (item.get("link") or "")
    return make_activitypub(url_for("view_item", iid=item["id"]), "Note", render_template("item-title.txt", item=item), content=text.strip(), attachments=attached)

def make_activitypub_user(user:User) -> dict:
    return make_activitypub(url_for("view_user", username=user.username), "Person", user.username)

def activitypub_fetch(url):
    return requests.get(url, headers={"Accept": ACTIVITYPUB_TYPES[0]}).json()

# def load_remote_item(path:str, host:str):
#     return activitypub_fetch()

def load_remote_user(username:str, host:str) -> RemoteUser|None:
    try:
        username = f"{username}@{host}"
        url = requests.get(f"{host_to_absolute(host)}/.well-known/webfinger?resource=acct:{username}").json()["aliases"][0]
        source = activitypub_fetch(url)
        return RemoteUser(username, url)
    except (json.JSONDecodeError, requests.ConnectionError):
        return None
