from flask import request, session, redirect, url_for
from flask_login import login_user # type: ignore[import-untyped]
from hashlib import sha256
from base64 import urlsafe_b64encode
from typing import Literal, cast
from _functions import redirect_next
from _users import load_user, User # type: ignore[import-untyped]
from _util import generate_user_hash

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
