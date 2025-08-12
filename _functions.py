import os
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from functools import wraps
from slugify import slugify
from flask import request, session, redirect, url_for, make_response, render_template
from flask_login import UserMixin, login_required, login_user # type: ignore[import-untyped]
from werkzeug.utils import safe_join
from _app_factory import app
from _pignio import *
from _util import *

class User(UserMixin):
    data: UserDict = {}

    def __init__(self, username:str, filepath:str|None=None, url:str|None=None):
        self.username = username
        self.filepath = filepath
        self.url = self.json_url = url
        if filepath:
            try:
                self.data = cast(UserDict, read_metadata(read_textual(filepath)))
            except FileNotFoundError:
                pass

    def get_id(self) -> str:
        return generate_user_hash(self.username, self.data["password"])
    
    def is_admin(self) -> bool:
        return True # TODO
    
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
    if user.is_admin():
        sources += wsv_to_list(read_textual(MODERATION_LIST))
    for event in sources:
        events.append(parse_event(event))
    events = sorted(events, key=(lambda event: event["datetime"]))
    events.reverse()
    return events

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

def getlang() -> str:
    return session.get("lang") or request.headers.get("Accept-Language", "en").split(",")[0].split("-")[0]

def gettext(key:str, lang:str|None=None) -> str:
    data = STRINGS.get(key) or {}
    return data.get(lang or getlang()) or data.get("en") or key

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
