## With Docker Compose

A file for deploying Pignio automatically via Docker Compose is provided. You can thus run Pignio on your server in seconds with just the following commands. By default, the software will be exposed on port 5000 of your host, and data will be stored in the local directory `data/` next to the Docker configuration file.

```sh
git clone --depth 1 https://gitlab.com/octospacc/Pignio && cd Pignio
# optional: edit `docker-compose.yml` as you wish
sudo docker-compose up -d
```

## From source (manually)

0. Ensure you have the base requirements installed on your system: `python` and `npm`.
    * Additionally, `node` is needed to render text posts into images correctly, as well as fonts, which must be available for all kinds of characters that might be rendered.
        * On Windows, all fonts should be available out of the box, while on Linux you might need to install them. On Debian and derivatives, install the `fonts-noto` metapackage for a nice collection of glyphs, including non-latin scripts and emojis.
    * Optionally, `tesseract` and all desired scripts/languages must also be installed, to allow for image OCR.
    * Optionally, to use the audio/video editing features, and generation of GIF video thumbnails, `ffmpeg` must also be installed.
1. Get the source code of Pignio: `git clone --depth 1 https://gitlab.com/octospacc/Pignio` `&& cd Pignio`.
2. Install all requirements: `python -m pip install -r requirements.txt` `&&` `npm install` (don't forget this last one, otherwise the app will run but the frontend and some features will be broken).
3. Run with `python app.py`. Optionally, you can edit the configuration file that is automatically created (`data/config.ini`).

## Deploy on PythonAnywhere

Pignio also runs well on PythonAnywhere, even on the free plan. To deploy it on there, after also installing npm as explained on <https://help.pythonanywhere.com/pages/Node/>, follow the above manual installation procedure, then create a new webapp with manual setup in the PythonAnywhere interface, and adjust your WSGI configuration file as follows:

```python
path = '/path/to/your/downloaded/Pignio'
if path not in sys.path:
    sys.path.append(path)
from app import app as application
```
