from flask import request, session, redirect, url_for
from hashlib import sha256
from base64 import urlsafe_b64encode
from typing import Literal, cast
from functools import wraps
from flask_login import login_required, login_user, current_user # type: ignore[import-untyped]
from _users import load_user, User # type: ignore[import-untyped]
from _util import generate_user_hash
from _functions import redirect_next, noindex
from _app_factory import app

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

def get_current_user():
    if not current_user.is_authenticated and (user := verify_token_auth()):
        return user
    return current_user

def is_request_authed():
    return current_user.is_authenticated or verify_token_auth()

def auth_required(func):
    @noindex
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs) if (is_request_authed() or app.config["FREEZING"]) else app.login_manager.unauthorized()
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
            return f(*args, **kwargs) if (not config_value or is_request_authed()) else app.login_manager.unauthorized()
        return wrapper
    return decorator
