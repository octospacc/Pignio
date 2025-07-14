def read_textual(filepath:str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(filepath, "r") as f:
            return f.read()

def write_textual(filepath:str, content:str):
    with open(filepath, "w", encoding="utf-8") as f:
        return f.write(content)
