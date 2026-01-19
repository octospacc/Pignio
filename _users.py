import os
from flask_login import UserMixin # type: ignore[import-untyped]
from typing import cast
from _util import generate_user_hash, read_metadata, read_textual, write_textual, write_metadata, slugify_name
from _pignio import UserDict, DataContainer, USERS_ROOT, ITEMS_EXT
from werkzeug.utils import safe_join

class User(UserMixin, DataContainer):
    data: UserDict
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
