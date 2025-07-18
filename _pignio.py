from typing import TypedDict, Required
from datetime import datetime
from snowflake import SnowflakeGenerator # type: ignore[import-untyped]

class MetaDict(TypedDict):
    ...

class ItemDict(MetaDict, total=False):
    id: str
    title: str
    description: str
    datetime: str
    link: str
    image: str
    video: str
    text: str
    systags: list[str]

class UserDict(MetaDict, total=False):
    password: Required[str]
    items: list[str]

DATA_ROOT = "data"
ITEMS_ROOT = f"{DATA_ROOT}/items"
USERS_ROOT = f"{DATA_ROOT}/users"
EXTENSIONS = {
    "image": ("jpg", "jpeg", "png", "gif", "webp", "avif"),
    "video": ("mp4", "mov", "mpeg", "ogv", "webm", "mkv"),
    "audio": ("mp3", "m4a", "flac", "opus", "ogg", "wav"),
}
ITEMS_EXT = ".ini"

snowflake_epoch = int(datetime(2025, 1, 1, 0, 0, 0).timestamp() * 1000)
snowflake = SnowflakeGenerator(1, epoch=snowflake_epoch)
