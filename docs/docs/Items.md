In Pignio, an item is a single, atomic piece of media or non-media which the app supports for viewing, pinning to collections, and so on.

## Item formats

Various kinds of items are supported, each with specified features and scopes, specified below with the corresponding formats and file extensions.

* Images
	* JPEG (`.jpg`, `.jpeg`)
	* JFIF
	* WEBP
	* AVIF
	* Bitmap (`.bmp`)
	* PNG, APNG
	* GIF
	* SVG
* Videos
	* MP4
	* MPG
	* MOV
	* MKV
	* OGV
	* WEBM
* Audios
	* MP3 (`.mp3`, `.mpeg`)
	* M4A
	* OGG
	* OPUS
	* WAV
	* FLAC
	* MIDI (`.mid`, `.midi`) with experimental browser support
* 3D models
* Fonts
	* TTF
	* OTF
	* WOFF / WOFF2
* Documents
	* Plaintext (`.txt`)
	* PDF
* Shockwave Flash animations (`.swf`)
* Emulator ROMs
	* NES / FC (`.nes`)
	* SNES / SFC (`.sfc`)
	* N64 (`.n64`, `.z64`)
	* GB, GBC, GBA
	* NDS
* Text on image

::: _pignio.EXTENSIONS

## Item metadata

Under construction. Refer to [Types reference#ItemDict](Types reference.md#_pignio.ItemDict) for the full fields reference straight from the source code.

All items:

* `title`: Optional item title. If not present, the filename or item ID will be used where needed.
* `description`: Optional additional text to show on the item page, no matter its type. Can contain URLs and hastags, which are automatically linkified where needed.
* `alttext`: For perceptive media like images or videos, an alternative text to be shown when the media can't be loaded, or for accessibility reasons.
* `link`: Optional URL specifying the external source of the item.
* `creator`: Username of the user on the instance which has created the item trough the system.
* `systags`: WSV list of specific words that the system applies a special meaning to.
* `langs`: WSV list of languages the content is marked as being in, in the 3-letter language code format. Can be shown to the user in item pages and is needed to run OCR scans on images.
* `status`: Publication status of the item. Currently supports `public` and `silent`. A missing value makes the system use the global default (public).

Text type items:

* `text`: The text to use to generate an image.
