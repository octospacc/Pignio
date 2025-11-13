Pignio contains a work-in-progress HTTP JSON API, partly built for use inside the web frontend and partly intended for integration with third-party apps implementing it. Be mindful that methods in the namespace of `/api/v0/` are intended either for internal use only, or are currently not considered production-ready and are subject to change, so use them at your own risk. All other methods are intended for general use already, listed below.

+ An example of a practical implementation of the API is available in the [WinDog](https://gitlab.com/octospacc/WinDog) multi-purpose chatbot for saving items via Telegram chats.
    + You can also test it using the `/Pignio` command in [@WinDogBot](https://t.me/WinDogBot).
+ Please refer to [[Types reference]] for type definitions for now, although what the HTTP API accepts is not exactly 1:1 how the program internally represents and stores data.
+ To make external calls to the API (when permitted), you need to set a standard `Authorization: Bearer <your API token>` on your HTTP request.
    + You can generate API tokens from your user settings page (`/settings`).

### Items API

* GET `/api/v1/items`: get the full representation of all accessible Items (returns an array of Items)
* GET `/api/v1/items/<item_id>`: get the full representation of an Item
* POST `/api/v1/items` (body = an Item): create a new Item on the server, as specified by the body
* PUT `/api/v1/items/<item_id>` (body = an Item): update the specified Item with new provided data
* DELETE `/api/v1/items/<item_id>`: delete the specified Item from the server
