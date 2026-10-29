"""Lets `python -m tinyhttp` start the server, run from the folder above.

`python -m tinyhttp --port 8001 shop:app` runs the WSGI app called `app` in
the module `shop` on port 8001, as gunicorn does. With no port it uses
8000, and with no app named it runs `tinyhttp.echo:app`.
"""

import argparse
import importlib
import sys

from tinyhttp.server import PORT, main


def load_app(spec):
    """Import "module:name" and return the object it names."""
    module_name, colon, name = spec.partition(":")
    if not colon or not module_name or not name:
        sys.exit(f"tinyhttp: expected module:name, such as shop:app, not {spec!r}")
    module = importlib.import_module(module_name)
    return getattr(module, name)


def port_number(text):
    """The --port value: a whole number from 1 to 65535."""
    if not (text.isascii() and text.isdigit()) or not 1 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"expected 1 to 65535, not {text!r}")
    return int(text)


parser = argparse.ArgumentParser(prog="python -m tinyhttp")
parser.add_argument("app", nargs="?", default="tinyhttp.echo:app",
                    help="the WSGI app, as module:name (default: %(default)s)")
parser.add_argument("--port", type=port_number, default=PORT,
                    help="the port to listen on (default: %(default)s)")
args = parser.parse_args()
main(load_app(args.app), args.port)
