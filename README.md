# Pignio

Pignio is your personal self-hosted media pinboard, built on top of flat-file storage.

<table><tr>
<td><a href="https://gitlab.com/octospacc/Pignio"><b>GitLab.com</b></a></td>
<td><a href="https://github.com/octospacc/Pignio">GitHub</a></td>
<td><a href="https://gitea.it/octospacc/Pignio">Gitea.it</a></td>
</tr></table>

You can view a production demo of the latest version of the software at <https://pignio.octt.eu.org/>.

![](https://octospacc.altervista.org/wp-content/uploads/2025/07/img_20250713_1007347894476461753800707-960x1280.jpg)

## Deploying

0. Ensure you have the base requirements installed on your system: `python` and `npm`.
    * Additionally, `node` is needed to render text posts into images correctly, as well as fonts, which must be available for all kinds of characters that might be rendered.
        * On Windows, all fonts should be available out of the box, while on Linux you might need to install them. On Debian and derivatives, install the `fonts-noto` metapackage for a nice collection of glyphs, including non-latin scripts and emojis.
    * Optionally, `tesseract` and all desired scripts/languages must also be installed, to allow for image OCR.
1. Get the source code of Pignio: `git clone --depth 1 https://gitlab.com/octospacc/Pignio` `&& cd Pignio`.
2. Install all requirements: `python -m pip install -r requirements.txt` `&&` `npm install`.
3. Run with `python app.py`. Optionally, you can edit the configuration file that is automatically created.

Pignio also runs well on PythonAnywhere, even on the free plan. To deploy it on there, after also installing npm as explained on <https://help.pythonanywhere.com/pages/Node/>, follow the above standard installation procedure, then create a new webapp with manual setup, and adjust your WSGI configuration file as follows:

```python
path = '/path/to/your/downloaded/Pignio'
if path not in sys.path:
    sys.path.append(path)
from app import app as application
```

## Static site generation (Experimental)

You can freeze your entire Pignio instance into a static site, which makes it possible to host it on any basic web server without Python. On a build machine or CI environment, make sure all requirements to normally run the software are satisfied, and that the app works, but then run the `freeze.py` script. It will generate a `build/` folder, with all the HTML pages prerendered and all media copied over, that you can then serve as-is or even package to share.

You can view a production demo of the static site generation feature at <https://pignioctt-9b535e.gitlab.io/index.html>.

## Thanks & Third-Party Libraries

* [UIkit](https://getuikit.com/) for the frontend framework
* [Unpoly](https://unpoly.com/) for smooth SPA-like navigation
* [model-viewer](https://modelviewer.dev/) for displaying of 3D models
* [Ruffle](https://ruffle.rs/) for Shockwave Flash emulation
* [EmulatorJS](https://emulatorjs.org/) for emulation of various game consoles
