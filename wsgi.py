"""The server's side of WSGI (PEP 3333): calling an app with a request.

The app is any callable app(environ, start_response). environ is a dict
describing the request; the app calls start_response with the status and
headers, then returns the body as an iterable of bytes.
"""

import io
import sys
from urllib.parse import unquote_to_bytes


def build_environ(request, server_address, client_address):
    """Turn a Request into the environ dict PEP 3333 says an app gets."""
    environ = {
        "REQUEST_METHOD": request.method,
        # The app answers every path, rather than being mounted under one.
        "SCRIPT_NAME": "",
        # The PEP wants %XX escapes decoded, and the resulting bytes held in
        # a str as latin-1, one character per byte. The app decodes them as
        # UTF-8 itself if it wants to.
        "PATH_INFO": unquote_to_bytes(request.path).decode("latin-1"),
        "QUERY_STRING": request.query,
        "SERVER_NAME": server_address[0],
        "SERVER_PORT": str(server_address[1]),
        "SERVER_PROTOCOL": request.version,
        "REMOTE_ADDR": client_address[0],
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        # The body, as a file the app can read() from.
        "wsgi.input": io.BytesIO(request.body),
        "wsgi.errors": sys.stderr,
        # One request at a time, in one process, until pre-fork workers.
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    # Headers become HTTP_ keys: "user-agent" is HTTP_USER_AGENT. The two
    # that describe the body go in without the prefix, as the PEP says.
    for name, value in request.headers.items():
        key = name.upper().replace("-", "_")
        if key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            environ[key] = value
        else:
            environ["HTTP_" + key] = value
    return environ


def get_response(app, environ):
    """Call a WSGI app and collect its reply.

    Returns (status, headers, body): a status such as "200 OK", a list of
    (name, value) pairs, and the whole body as bytes. Whatever the app
    raises is passed on to the caller.
    """
    status = None
    headers = None
    body = []

    def start_response(new_status, new_headers, exc_info=None):
        nonlocal status, headers
        # A second call is only allowed for an error, with exc_info. The PEP
        # says to re-raise if headers were already sent, but we send nothing
        # until the app is done, so the error reply can always replace them.
        if status is not None and exc_info is None:
            raise RuntimeError("start_response called twice")
        status = new_status
        headers = new_headers
        # The PEP's write(), for old apps that send the body through it.
        return body.append

    result = app(environ, start_response)
    try:
        # Collect every piece before sending, so Content-Length is known.
        for chunk in result:
            body.append(chunk)
    finally:
        # The PEP makes calling close() the server's job, even after an error.
        if hasattr(result, "close"):
            result.close()

    # Checked after the loop, because an app that's a generator doesn't run,
    # and so doesn't call start_response, until it's iterated.
    if status is None:
        raise RuntimeError("the app never called start_response")
    return status, headers, b"".join(body)
