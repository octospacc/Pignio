import os
import json
import requests
import urllib.parse
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from bs4 import BeautifulSoup
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
# from _features import *

class User(UserMixin):
    data: UserDict = {}
    is_admin = False
    is_authed = False

    def __init__(self, username:str, filepath:str|None=None, url:str|None=None):
        self.username = username
        self.filepath = filepath
        self.url = self.json_url = url
        if filepath:
            try:
                self.data = cast(UserDict, read_metadata(read_textual(filepath)))
                self.is_admin = ("admin" in cast(list[str], self.data.get("roles", [])))
            except FileNotFoundError:
                pass

    def get_id(self) -> str:
        return generate_user_hash(self.username, self.data["password"])
    
    def save(self) -> None:
        if self.filepath:
            write_textual(self.filepath, write_metadata(self.data))
        else:
            raise Exception

class RemoteUser(User):
    url: str
    json_url: str

    def __init__(self, username:str, url:str):
        super().__init__(username, url=url)

def load_user(username:str) -> User|None:
    username = slugify_name(username)
    filepath = safe_join(USERS_ROOT, (username + ITEMS_EXT))
    if filepath and os.path.exists(filepath):
        return User(username, filepath)
    else:
        return None

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

def generate_user_hash(username:str, password:str) -> str:
    return f"{username}:" + urlsafe_b64encode(sha256(password.encode()).digest()).decode()

def verify_token_auth() -> User|Literal[False]:
    if (auth := request.headers.get("Authorization", "")).startswith("Bearer "):
        [username, token] = auth.split(" ")[1].split(":")
        if ((user := load_user(username)) and check_user_token(cast(list[str], user.data.get("tokens", [])), hash_api_token(token))):
            user.__dict__["is_authenticated"] = True
            return user
    return False

def check_user_token(tokens:list[str], hashed:str) -> str|Literal[False]:
    for token in tokens:
        if token.endswith(f":{hashed}"):
            return token
    return False

def hash_api_token(token:str) -> str:
    return urlsafe_b64encode(sha256(token.encode()).digest()).decode()

def init_user_session(user:User, remember:bool):
    session["session_hash"] = generate_user_hash(user.username, user.data["password"])
    login_user(user, remember=remember)
    return redirect_next()

def redirect_next():
    next_data = urllib.parse.urlparse(request.args.get("next", ""))
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
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs) if (current_user.is_authenticated or verify_token_auth()) else app.login_manager.unauthorized()
    return wrapped

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
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=9) as zipf:
        for file in files:
            zipf.write(*file)
    buffer.seek(0)
    return send_file(buffer, "application/zip", True, f"{name}.zip")

def getlang() -> str:
    return getprefs().get("lang") or request.headers.get("Accept-Language", "en").split(",")[0].split("-")[0]

def gettext(key:str, lang:str|None=None) -> str:
    data = STRINGS.get(key) or {}
    return data.get(lang or getlang()) or data.get("en") or key

def getprefs() -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(request.cookies.get("prefs")).items()}

def setprefs(**props:Any) -> Response:
    response = redirect_next()
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
