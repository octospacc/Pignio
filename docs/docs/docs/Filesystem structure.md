Being a flat-file software system, Pignio stores all its data into individual files on disk for all its features. This happens in a folder aptly called `data` in the root directory of the program, and the following is its rough tree diagram.

```
data
├───config.ini
├───items
│   └───<subfolder>
│       └───<item files>
├───users
│   ├───<user>.ini
│   └───<user folder>
│       └───<collections files>
├───cache
└───temp
```
