import os
import urllib.parse
from pathlib import Path
from slugify import slugify
from configparser import ConfigParser
from shutil import copyfile
from io import StringIO

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

def list_to_wsv(data:list[str], sep="\n") -> str:
    return sep.join([urllib.parse.quote(item) for item in data])

def wsv_to_list(data:str) -> list[str]:
    return [urllib.parse.unquote(item) for item in data.strip().replace(" ", "\n").replace("\t", "\n").splitlines()]

def safe_str_get(dikt:dict[str,str]|dict[str,str|None], key:str) -> str:
    return dikt and dikt.get(key) or ""

from _pignio import *

def write_textual(filepath:str, content:str) -> None:
    if Config.USE_BAK_FILES and os.path.isfile(filepath):
        copyfile(filepath, f"{filepath}.bak")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def read_metadata(text:str) -> MetaDict:
    data = read_ini(text)
    for key in ("items", "systags", "langs", "roles", "tokens"):
        if key in data:
            data[key] = wsv_to_list(data[key])
    return data

def write_metadata(data:dict[str, str]|MetaDict) -> str:
    output = StringIO()
    config = ConfigParser(interpolation=None)
    new_data: dict[str, str] = {}
    for key in data:
        if (value := data.get(key)) and key not in (*MEDIA_TYPES, "datetime"):
            if type(value) == str:
                new_data[key] = value
            elif type(value) == list:
                new_data[key] = list_to_wsv(value)
    config["DEFAULT"] = new_data
    config.write(output)
    return "\n".join(output.getvalue().splitlines()[1:]) # remove section header
