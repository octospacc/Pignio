import os
from typing import TypedDict, Required, Literal, Any
from secrets import token_urlsafe
from datetime import datetime
from snowflake import SnowflakeGenerator # type: ignore[import-untyped]
from queue import Queue
from threading import Thread
from _util import *

class DataContainer:
    data: MetaDict

    def __init__(self, data_dict:MetaDict):
        # Initialize an instance attribute to store the dictionary data
        self.data = data_dict

    def __getattr__(self, key):
        """Fallback for dot notation (obj.a)"""
        if key in self.data:
            return self.data[key]
        # raise AttributeError(f"'{key}' not found")
        return None

    def __setitem__(self, key, value):
        """Implementation for bracket notation (obj['a'] = value)"""
        # This updates the underlying dictionary
        self.data[key] = value

    def __getitem__(self, key):
        """Implementation for bracket notation access (obj['a'])"""
        return self.data[key]

    def __or__(self, other):
        """
        Handles the pipe operator: obj | dict
        Returns a NEW instance with merged data.
        """
        if not isinstance(other, dict):
            return NotImplemented
        # Create a new dictionary merging the two
        new_data = self.data | other 
        return DataContainer(new_data)

    def __ior__(self, other):
        """
        Handles the in-place pipe operator: obj |= dict
        Updates the existing instance.
        """
        if not isinstance(other, dict):
            return NotImplemented
        # Update the internal dictionary in place
        self.data |= other
        return self
    
    def get(self, key):
        return self.__getattr__(key)

    def __len__(self):
        return len(self.data)

class MetaDict(TypedDict):
    title: str

class ItemDict(MetaDict, total=False): # type: ignore[call-arg]
    id: str
    description: str
    datetime: str
    link: str
    images: list[str]
    image: str
    video: str
    model: str
    doc: str
    langs: list[str]
    text: str
    alttext: str
    systags: list[str]
    status: Literal["public", "silent"]
    type: str
    creator: str

class CollectionDict(MetaDict, total=False): # type: ignore[call-arg]
    items: list[str]
    description: str

class UserDict(CollectionDict, total=False): # type: ignore[call-arg]
    password: str
    tokens: list[str]

DATA_ROOT = "data"
ITEMS_ROOT = f"{DATA_ROOT}/items"
TEMP_ROOT = f"{DATA_ROOT}/temp"
USERS_ROOT = f"{DATA_ROOT}/users"
EVENTS_ROOT = f"{DATA_ROOT}/events"
CACHE_ROOT = f"{DATA_ROOT}/cache"
THUMBS_ROOT = f"{CACHE_ROOT}/thumbs"
RENDERS_ROOT = f"{CACHE_ROOT}/renders"
PROXY_ROOT = f"{CACHE_ROOT}/proxy"
EXTENSIONS = {
    "image": ("mpo", "jpg", "jpeg", "jfif", "bmp", "png", "apng", "gif", "webp", "avif", "svg"),
    "video": ("mp4", "mov", "mpg", "ogv", "webm", "mkv"),
    "audio": ("mp3", "m4a", "flac", "opus", "ogg", "wav", "mid", "midi"),
    "audio.extra": {"mpeg": "mp3"},
    "model": ("glb", ),
    "font": ("ttf", "otf", "woff", "woff2"),
    "doc": ("pdf", "txt", "md", "markdown"),
    # "web": ("warc", ),
    "swf": ("swf", ),
    "rom": ("nes", "sfc", "n64", "z64", "gb", "gbc", "gba", "nds"),
}
ITEMS_EXT = ".ini"
LISTS_EXT = ".wsv"
# EVENTS_EXT = f".events{LISTS_EXT}"
MEDIA_TYPES = [kind for kind in EXTENSIONS.keys() if "." not in kind]
MODERATION_LIST = f"{DATA_ROOT}/moderation{LISTS_EXT}"
ATOM_CONTENT_TYPE = "application/atom+xml; charset=UTF-8"
ACTIVITYPUB_TYPES = ['application/ld+json; profile="https://www.w3.org/ns/activitystreams"', "application/activity+json"]

mkdirs(ITEMS_ROOT, USERS_ROOT)

class Config:
    @staticmethod
    def _makeget():
        user_path = f"{DATA_ROOT}/config.ini"
        base_ini = read_textual("config.template.ini")
        base = read_ini(base_ini)

        if not os.path.isfile(user_path):
            with open(user_path, "w", encoding="utf-8") as f:
                f.write(f"Secret_Key = {token_urlsafe()}\n\n{base_ini}")
        user = read_ini(read_textual(user_path))

        def _get(key:str) -> Any:
            return user.get(key, base.get(key))
        return _get
    _get = _makeget()

    SECRET_KEY = _get("secret_key")
    DEVELOPMENT = parse_bool_strict(_get("development"))
    HTTP_HOST = _get("http_host")
    HTTP_PORT = int(_get("http_port"))
    HTTP_THREADS = int(_get("http_threads"))
    LINKS_PREFIX = _get("links_prefix")
    RESULTS_LIMIT = int(_get("results_limit"))
    AUTO_OCR = parse_bool_strict(_get("auto_ocr"))
    INSTANCE_NAME = _get("instance_name")
    INSTANCE_DESCRIPTION = _get("instance_description")
    RESTRICT_INDEX = parse_bool_strict(_get("restrict_index"))
    RESTRICT_ITEMS = parse_bool_strict(_get("restrict_items"))
    RESTRICT_USERS = parse_bool_strict(_get("restrict_users"))
    RESTRICT_FEEDS = parse_bool_strict(_get("restrict_feeds"))
    RESTRICT_SEARCH = parse_bool_strict(_get("restrict_search"))
    RESTRICT_ITEMS_DOWNLOAD = parse_bool_strict(_get("restrict_items_download"))
    RESTRICT_FOLDERS_DOWNLOAD = parse_bool_strict(_get("restrict_folders_download"))
    ALLOW_REGISTRATION = parse_bool_strict(_get("allow_registration"))
    # ALLOW_FEDERATION = False
    USE_THUMBNAILS = parse_bool_strict(_get("use_thumbnails"))
    THUMBNAIL_CACHE = parse_bool_strict(_get("thumbnail_cache"))
    RENDER_CACHE = parse_bool_strict(_get("render_cache"))
    PROXY_CACHE = parse_bool_strict(_get("proxy_cache"))
    VIDEO_THUMB_DURATION = int(_get("video_thumbnail_duration"))
    VIDEO_THUMB_WIDTH = int(_get("video_thumbnail_width"))
    VIDEO_THUMB_FPS = int(_get("video_thumbnail_fps"))
    THUMB_QUALITY = int(_get("image_thumbnail_quality"))
    THUMB_WIDTH = int(_get("image_thumbnail_width"))
    THUMB_TYPE = _get("image_thumbnail_type")
    RENDER_TYPE = _get("image_render_type")
    USE_BAK_FILES = parse_bool_strict(_get("use_bak_files"))
    # PANSTORAGE_URL = ""
    SITE_VERIFICATION = {
        "GOOGLE": _get("site_verification_google"),
        "BING": _get("site_verification_bing"),
    }

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
    "Profile": {
        "it": "Profilo",
    },
    "Item": {
        "it": "Elemento",
    },
    "Items": {
        "it": "Elementi",
    },
    "User": {
        "it": "Utente",
    },
    "Users": {
        "it": "Utenti",
    },
    "Image": {
        "it": "Immagine",
    },
    "Document": {
        "it": "Documento",
    },
    "3D Model": {
        "it": "Modello 3D",
    },
    "Administration": {
        "it": "Amministrazione",
    },
    "Current Configuration": {
        "it": "Configurazione Attuale",
    },
    "Clear Cache": {
        "it": "Pulisci Cache",
    },
    "Cache cleared": {
        "it": "Cache pulita",
    },
    "Clear BAK Files": {
        "it": "Pulisci File BAK",
    },
    "BAK files cleared": {
        "it": "File BAK puliti",
    },
    "Clear Temp Files": {
        "it": "Pulisci File Temporanei",
    },
    "Temp files cleared": {
        "it": "File temporanei puliti",
    },
    "Profile updated": {
        "it": "Profilo aggiornato",
    },
    "Statistics": {
        "it": "Statistiche",
    },
    "Registration Allowed": {
        "it": "Registrazione Permessa",
    },
    "Settings": {
        "it": "Impostazioni",
    },
    "Search": {
        "it": "Cerca",
    },
    "Search results for": {
        "it": "Risultati di ricerca per",
    },
    "No results found for": {
        "it": "Nessun risultato trovato per",
    },
    "Copy to clipboard": {
        "it": "Copia negli appunti",
    },
    "Expand": {
        "it": "Espandi",
    },
    "Shrink": {
        "it": "Riduci",
    },
    "Name": {
        "it": "Nome",
    },
    "Folder": {
        "it": "Cartella",
    },
    "Collection": {
        "it": "Raccolta",
    },
    "New Collection": {
        "it": "Nuova Raccolta",
    },
    "Pin to Collections": {
        "it": "Salva nelle Raccolte",
    },
    "Pinned": {
        "it": "Salvati",
    },
    "Created": {
        "it": "Creati",
    },
    "Comments": {
        "it": "Commenti",
    },
    "Notifications": {
        "it": "Notifiche",
    },
    "No notifications": {
        "it": "Nessuna notifica",
    },
    "Create": {
        "it": "Crea",
    },
    "Public": {
        "it": "Pubblico",
    },
    "Silent": {
        "it": "Silenzioso",
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
    "Apply": {
        "it": "Applica",
    },
    "Fields": {
        "it": "Campi",
    },
    "All": {
        "it": "Tutto",
    },
    "Any": {
        "it": "Qualsiasi",
    },
    "Add": {
        "it": "Aggiungi",
    },
    "Add image from URL": {
        "it": "Aggiungi immagine da URL",
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
    "Back": {
        "it": "Indietro",
    },
    "Save": {
        "it": "Salva",
    },
    "Note": {
        "it": "Nota",
    },
    "Random order": {
        "it": "Ordine casuale",
    },
    "Natural order": {
        "it": "Ordine naturale",
    },
    "Alphanumeric order": {
        "it": "Ordine alfanumerico",
    },
    "Gallery": {
        "it": "Galleria",
    },
    "Masonry": {
        "it": "Griglia",
    },
    "Content Languages": {
        "it": "Lingue del Contenuto",
    },
    "Visibility": {
        "it": "Visibilità",
    },
    "Provenance": {
        "it": "Provenienza",
    },
    "Export data": {
        "it": "Esporta dati",
    },
    "Download folder": {
        "it": "Scarica cartella",
    },
    "Overwrite": {
        "it": "Sovrascrivi",
    },
    "Join": {
        "it": "Unisci",
    },
    "Join Videos": {
        "it": "Unisci Video",
    },
    "Trim": {
        "it": "Accorcia",
    },
    "Trim Media": {
        "it": "Accorcia Media",
    },
    "Save as New": {
        "it": "Salva come Nuovo",
    },
    "Set Start": {
        "it": "Imposta Inizio",
    },
    "Set End": {
        "it": "Imposta Fine",
    },
    "Marking": {
        "it": "Indicazione",
    },
    "Mark as sensitive": {
        "it": "Indica come sensibile",
    },
    "Switch Theme": {
        "it": "Cambia Tema",
    },
    "username-note": {
        "en": "You cannot change this later.",
        "it": "Non può essere cambiato in seguito.",
    },
    "comment-placeholder": {
        "en": "What's on your mind?",
        "it": "A cosa stai pensando?",
    },
    "do-comment": {
        "en": "Comment",
        "it": "Commenta",
    },
    "login-to-access": {
        "en": "Please log in to access this page.",
        "it": "Accedi per visualizzare questa pagina.",
    },
    "report-tip": {
        "en": "The report will be sent to admins for review.",
        "it": "La segnalazione verrà inviata agli amministratori.",
    },
    "upload-tip": {
        "en": "Select or drop a media file",
        "it": "Seleziona o trascina un file media",
    },
    "link-fill": {
        "en": "Fill data from link",
        "it": "Inserisci dati da link",
    },
    "switch-render-mode": {
        "en": "Switch rendering mode",
        "it": "Cambia modalità di rendering",
    },
    "systag-ai": {
        "en": "This media is marked as being generated, in whole or substantial part, by artificial intelligence models.",
        "it": "Questo media è indicato come generato, completamente o in gran parte, da modelli di intelligenza artificiale.",
    },
    "systag-oc": {
        "en": "The user who uploaded this media has marked it as being their own original content.",
        "it": "L'utente che ha caricato questo media lo ha indicato come proprio contenuto originale.",
    },
    "systag-nsfw": {
        "en": "This media is marked as potentially sensitive, or \"not safe for work\". Click it to reveal it.",
        "it": "Questo media è indicato come potenzialmente sensibile, o \"not safe for work\". Cliccalo per rivelarlo.",
    },
    "API Tokens": {
        "it": "Token API",
    },
    "Create New Token": {
        "it": "Crea Nuovo Token",
    },
    "created-token": {
        "en": "Created a new API token! (Copy it now and store it safely, it will not be visible anymore.)",
        "en": "Creato un nuovo token API! (Copialo ora e conservalo al sicuro, non sarà più visibile.)",
    },
    "deleted-token": {
        "en": "API token deleted!",
        "it": "Token API eliminato!",
    },
    "login-invalid": {
        "en": "Invalid username or password",
        "it": "Username o password errati",
    },
    "Not Found": {
        "it": "Non Trovato",
    },
    "French": {
        "fr": "Français",
    },
    "German": {
        "de": "Deutsch",
    },
    "Greek": {
        "el": "ελληνικά",
    },
    "Italian": {
        "it": "Italiano",
    },
    "Japanese": {
        "ja": "日本語",
    },
    "Korean": {
        "kp": "조선어",
        "kr": "한국어",
    },
    "Russian": {
        "ru": "Русский",
    },
    "Spanish": {
        "es": "Español",
    },
}
