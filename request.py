"""Parsing a request's head, the request line and headers, into a Request.

No sockets here: parse_head takes bytes, so it can be tried on its own.
"""

from dataclasses import dataclass

VERSIONS = ("HTTP/1.0", "HTTP/1.1")


class BadRequest(Exception):
    """The client sent something we can't treat as an HTTP request."""


@dataclass
class Request:
    method: str     # "GET"
    path: str       # "/products", without the query
    query: str      # "page=2", the part after "?", or "" if there isn't one
    version: str    # "HTTP/1.1"
    headers: dict   # Names lowercased: {"host": "localhost:8000"}


def parse_head(head):
    """Parse a head, as read_head returns it, into a Request.

    Raises BadRequest if it isn't valid HTTP/1.0 or HTTP/1.1.
    """
    # latin-1 turns each byte into one character, so decoding never fails.
    # HTTP's headers were defined in it, long before UTF-8.
    lines = head.decode("latin-1").split("\r\n")
    for line in lines:
        # A lone \r or \n could make us and a proxy in front of us disagree
        # about where a line ends, so the standard says to refuse it.
        if "\r" in line or "\n" in line:
            raise BadRequest("line ending in a lone \\r or \\n")

    method, path, query, version = parse_request_line(lines[0])
    headers = parse_headers(lines[1:])
    # HTTP/1.1 requires Host, so one server can host several sites.
    if version == "HTTP/1.1" and "host" not in headers:
        raise BadRequest("HTTP/1.1 request without a Host header")
    return Request(method, path, query, version, headers)


def parse_request_line(line):
    """Split "GET /products?page=2 HTTP/1.1" into its four parts."""
    parts = line.split(" ")
    # "" in parts catches two spaces in a row, or one at either end.
    if len(parts) != 3 or "" in parts:
        raise BadRequest(f"bad request line {line!r}")
    method, target, version = parts

    if not (method.isascii() and method.isalpha() and method.isupper()):
        raise BadRequest(f"bad method {method!r}")
    if not target.startswith("/"):
        raise BadRequest(f"target {target!r} doesn't start with '/'")
    if version not in VERSIONS:
        raise BadRequest(f"unsupported version {version!r}")

    path, _, query = target.partition("?")
    return method, path, query, version


def parse_headers(lines):
    """Turn lines such as "Host: localhost" into a dict, names lowercased."""
    headers = {}
    for line in lines:
        # A line starting with a space or tab continues the one before. It's
        # obsolete, and the standard lets a server refuse it.
        if line[:1] in (" ", "\t"):
            raise BadRequest("header continuation lines aren't supported")

        name, colon, value = line.partition(":")
        if not colon:
            raise BadRequest(f"header line without ':' {line!r}")
        # A space before the colon is a known way to make a proxy and a
        # server read the same request differently (request smuggling).
        if not name or " " in name or "\t" in name:
            raise BadRequest(f"bad header name {name!r}")

        # Names aren't case-sensitive, so "Host" and "host" are the same.
        name = name.lower()
        value = value.strip(" \t")
        if name in headers:
            # The standard says repeats mean the same as one comma list.
            headers[name] += ", " + value
        else:
            headers[name] = value
    return headers
