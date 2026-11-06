"""Lets `python -m tinyhttp` start the server, run from the folder above.

`python -m tinyhttp --host 127.0.0.1 --port 8001 shop:app` runs the WSGI
app called `app` in the module `shop` on 127.0.0.1, port 8001, as gunicorn
does. With no host it listens on every interface, with no port it uses
8000, and with no app named it runs `tinyhttp.echo:app`. `--keep-alive`
is how many seconds an idle connection is kept, 2 by default.
"""

import argparse
import importlib
import sys

from tinyhttp.server import HOST, KEEP_ALIVE, PORT, main


def load_app(spec):
    """Import "module:name" and return the object it names."""
    module_name, colon, name = spec.partition(":")
    if not colon or not module_name or not name:
        sys.exit(f"tinyhttp: expected module:name, such as shop:app, not {spec!r}")
    module = importlib.import_module(module_name)
    return getattr(module, name)


def port_number(text):
    """The --port value: a whole number from 0 to 65535, 0 for any free one."""
    if not (text.isascii() and text.isdigit()) or not 0 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"expected 0 to 65535, not {text!r}")
    return int(text)


def seconds(text):
    """The --keep-alive value: a whole number of seconds, 0 for none."""
    if not (text.isascii() and text.isdigit()):
        raise argparse.ArgumentTypeError(f"expected a whole number, not {text!r}")
    return int(text)


parser = argparse.ArgumentParser(prog="python -m tinyhttp")
parser.add_argument("app", nargs="?", default="tinyhttp.echo:app",
                    help="the WSGI app, as module:name (default: %(default)s)")
parser.add_argument("--port", type=port_number, default=PORT,
                    help="the port to listen on, 0 for any free one "
                         "(default: %(default)s)")
parser.add_argument("--host", default=HOST,
                    help="the address to listen on, such as 127.0.0.1 "
                         "(default: every interface)")
parser.add_argument("--keep-alive", type=seconds, default=KEEP_ALIVE,
                    help="seconds to keep an idle connection for its next "
                         "request, 0 to close after each "
                         "(default: %(default)s)")
args = parser.parse_args()
main(load_app(args.app), args.port, args.host, args.keep_alive)
