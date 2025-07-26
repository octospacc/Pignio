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

0. Ensure you have `python` and `npm` installed on your system.
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
