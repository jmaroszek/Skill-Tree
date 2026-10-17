"""The JavaScript behind a clientside callback, for tests that run it in Node."""
from support.paths import app_asset_files


def clientside_source(app, output):
    """(source, namespace, function name) of the clientside callback whose
    outputs include ``output``.

    The source is the script that defines the function: the inline script
    Dash made from JavaScript written in the Python, or the asset that sets
    window.dash_clientside.<namespace>.<name>. Running it in a page whose
    window.dash_clientside exists defines the function.
    """
    spec = next(c for c in app._callback_list
                if c.get("clientside_function") and output in c["output"])
    namespace = spec["clientside_function"]["namespace"]
    name = spec["clientside_function"]["function_name"]
    for script in app._inline_scripts:
        if name in script:
            return script, namespace, name
    for path in app_asset_files(".js"):
        source = path.read_text(encoding="utf-8")
        if f"dash_clientside.{namespace}.{name} =" in source:
            return source, namespace, name
    raise LookupError(f"no script defines {namespace}.{name}")
