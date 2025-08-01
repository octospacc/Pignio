import os
from typing import TypedDict, Required
from datetime import datetime
from snowflake import SnowflakeGenerator # type: ignore[import-untyped]
from queue import Queue
from threading import Thread

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
    langs: list[str]
    text: str
    alttext: str
    systags: list[str]
    type: str

class CollectionDict(MetaDict, total=False):
    items: list[str]

class UserDict(CollectionDict, total=False):
    password: Required[str]

DATA_ROOT = "data"
ITEMS_ROOT = f"{DATA_ROOT}/items"
USERS_ROOT = f"{DATA_ROOT}/users"
EVENTS_ROOT = f"{DATA_ROOT}/events"
EXTENSIONS = {
    "image": ("jpg", "jpeg", "jfif", "bmp", "png", "apng", "gif", "webp", "avif"),
    "video": ("mp4", "mov", "mpeg", "ogv", "webm", "mkv"),
    "audio": ("mp3", "m4a", "flac", "opus", "ogg", "wav"),
}
ITEMS_EXT = ".ini"
LISTS_EXT = ".wsv"
# EVENTS_EXT = f".events{LISTS_EXT}"
MODERATION_LIST = f"{DATA_ROOT}/moderation{LISTS_EXT}"

snowflake_epoch = int(datetime(2025, 1, 1, 0, 0, 0).timestamp() * 1000)
snowflake = SnowflakeGenerator(1, epoch=snowflake_epoch)

# events_queue = Queue()
moderation_queue: Queue[str] = Queue()

# def events_writer():

def moderation_writer():
    with open(MODERATION_LIST, "a") as f:
        while True:
            f.write(moderation_queue.get() + "\n")
            f.flush()
            #os.fsync(f)
            moderation_queue.task_done()

# Thread(target=events_writer).start()
Thread(target=moderation_writer, daemon=True).start()

STRINGS = {
    "Search": {
        "it": "Cerca",
    },
    "Create": {
        "it": "Crea",
    },
    "Title": {
        "it": "Titolo",
    },
    "Description": {
        "it": "Descrizione",
    },
    "Text": {
        "it": "Testo",
    },
    "Register": {
        "it": "Registrati",
    },
    "Confirm": {
        "it": "Conferma",
    },
    "Remember me": {
        "it": "Ricordami",
    },
    "Logged in as": {
        "it": "Accesso effettuato come",
    },
    "Load more": {
        "it": "Carica altro",
    },
    "Add": {
        "it": "Aggiungi",
    },
    "Edit": {
        "it": "Modifica",
    },
    "Delete": {
        "it": "Elimina",
    },
    "Report": {
        "it": "Segnala",
    },
    "Note": {
        "it": "Nota",
    },
    "Export data": {
        "it": "Esporta dati",
    },
    "username-note": {
        "en": "You cannot change this later.",
        "it": "Non può essere cambiato in seguito.",
    },
    "comment-placeholder": {
        "en": "What's on your mind?",
        "it": "A cosa stai pensando?",
    },
}
