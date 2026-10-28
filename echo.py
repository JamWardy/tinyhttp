"""A WSGI app that replies with what it was given.

The server runs it when no app is named. It reads only from environ, so
its reply shows what the server built: a quick check of the server, or a
way to see what a client sends.
"""


def app(environ, start_response):
    # The PEP says not to read past CONTENT_LENGTH.
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length)

    lines = [
        f"method:   {environ['REQUEST_METHOD']}",
        f"path:     {environ['PATH_INFO']}",
        f"query:    {environ['QUERY_STRING']}",
        f"protocol: {environ['SERVER_PROTOCOL']}",
        "headers:",
    ]
    for key, value in environ.items():
        if key.startswith("HTTP_") or key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            lines.append(f"  {key}: {value}")
    lines.append(f"body:     {len(body)} bytes")
    if body:
        lines.append(f"  {body[:100]!r}")
    text = "\n".join(lines) + "\n"

    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [text.encode("utf-8")]
