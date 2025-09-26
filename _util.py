import os
import urllib.parse
from pathlib import Path
from slugify import slugify
from configparser import ConfigParser

def parse_bool(v:str|bool) -> bool|None:
    if type(v) == bool:
        return v
    elif type(v) == str:
        v = v.lower()
        if v in ("true", "1", "yes"):
            return True
        elif v in ("false", "0", "no"):
            return False
    return None

def mkdirs(*paths:str) -> None:
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)

def slugify_name(text:str):
    return slugify(text)[:64]

def strip_ext(filename:str) -> str:
    return os.path.splitext(filename)[0]

def host_to_absolute(host:str) -> str:
    scheme = urllib.parse.urlsplit(host).scheme
    if not scheme:
        host = f"https://{host}"
    return host

def read_ini(text:str):
    config = ConfigParser(interpolation=None)
    config.read_string(f"[DEFAULT]\n{text}")
    return config._defaults # type: ignore[attr-defined]

def read_textual(filepath:str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(filepath, "r") as f:
            return f.read()
