"""Lets `python -m tinyhttp` start the server, run from the folder above.

`python -m tinyhttp shop:app` runs the WSGI app called `app` in the module
`shop`, as gunicorn does. With no app named, it runs `tinyhttp.echo:app`.
"""

import importlib
import sys

from tinyhttp.server import main


def load_app(spec):
    """Import "module:name" and return the object it names."""
    module_name, colon, name = spec.partition(":")
    if not colon or not module_name or not name:
        sys.exit(f"tinyhttp: expected module:name, such as shop:app, not {spec!r}")
    module = importlib.import_module(module_name)
    return getattr(module, name)


if len(sys.argv) > 2:
    sys.exit("usage: python -m tinyhttp [module:name]")
main(load_app(sys.argv[1] if len(sys.argv) == 2 else "tinyhttp.echo:app"))
