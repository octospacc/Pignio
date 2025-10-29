Instead of a traditional table-based database, all application and user data that requires specific fields is stored as simple key-value properties in INI files, which are read and written efficiently by the system, and can also be comfortably edited manually by users.

All properties in the INI file are written directly, so without any parent section. The INI dialect used is the one defined by Python, without any interpolation of the values, so:

* No whitespace is allowed to the left of keys, when declaring a property.
* Any text after the key (and the equals symbol `=`) is interpreted literally, without any obscure escaping rules.
* Multiline values are supported, by adding whitespace to the left of the lines following the start of a property.
* Comment lines with the hash symbol (`#`) are allowed.