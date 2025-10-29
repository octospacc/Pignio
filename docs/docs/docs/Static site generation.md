# Static site generation (Experimental)

You can freeze your entire Pignio instance into a static site, which makes it possible to host it on any basic web server without Python. On a build machine or CI environment, [[Running|make sure all requirements to normally run the software are satisfied]], and that the app works, but then run the `freeze.py` script. It will generate a `build/` folder, with all the HTML pages prerendered and all media copied over, that you can then serve as-is or even package to share.

You can view a production demo of the static site generation feature at <https://pignioctt-9b535e.gitlab.io/index.html>. Also take a look at the CI scripts that build the site inside the Git repository: <https://gitlab.com/octospacc/pignioctt/>.

## Quirks

The server works with URL paths that have no extra suffixes, eg. no trailing slashes or html extension. However, writing HTML pages to disk for static serving with such naming would prove problematic in many environments, so all page files have an added `.html` suffix. This is no particular issue, but it means that the expected URLs differ between a Pignio dynamic site and a static one.

Given the impossibility to interpret query parameters in the URL, some features are also not available in the static sites and some things might differ, such as:

* Pagination is limited to the fixed size specified in the app configuration at build time, and is done via numbers appended to the page name (`.2.html`, `.3.html`, ...).
* Where otherwise reorderable on request between random or not, item lists are forced to be in natural order and are fixed this way.
* No searching is yet available, as this would need to be reimplemented with custom client-side JavaScript.
* Support in static sites for specific random things might fall behind in development, and be broken, but overall things should always work.

Additionally, for the moment the generated HTML pages rely on absolute links, so the static website must be hosted on the root of a domain and can't be browsed from the local file system (`file://`) without a server.
