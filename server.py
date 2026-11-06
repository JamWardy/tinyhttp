"""The server: socket, bind, listen, accept, read, respond."""

import errno
import select
import socket
import sys
import time
import traceback

from tinyhttp.request import BadRequest, body_length, keep_alive, parse_head
from tinyhttp.wsgi import build_environ, get_response

HOST = ""     # Every network interface, so other machines can reach it too.
PORT = 8000

# The most bytes we'll read looking for the end of the headers, blank line
# included. Without a limit, a client could send headers forever and we'd
# keep them all in memory. gunicorn's limits come to about the same.
MAX_HEAD_SIZE = 8192

# Seconds an idle connection is kept for its next request, as gunicorn's
# --keep-alive. 0 closes every connection after one request.
KEEP_ALIVE = 2

# The most idle connections kept at once, as gunicorn's gthread worker
# caps them, so every socket stays under select()'s limit of 1023.
MAX_IDLE = 1000


def main(app, port=PORT, host=HOST, keep_alive_timeout=KEEP_ALIVE):
    """Serve the WSGI app on host and port, one request at a time, for ever.

    host is an address such as "127.0.0.1", or "" for every interface.
    """
    # AF_INET is IPv4 and SOCK_STREAM is TCP: a reliable stream of bytes.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Without this, restarting soon after stopping fails with "Address
        # already in use", while the old connections wait out TIME_WAIT.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                sys.exit(f"tinyhttp: port {port} is already in use")
            # Such as a host that isn't one of this machine's addresses.
            sys.exit(f"tinyhttp: can't listen on {host}:{port}: {error}")
        # The kernel queues up to this many connections that have finished
        # the TCP handshake but that we haven't accepted yet.
        listener.listen(16)
        # The port it really got, which port 0 leaves to the system.
        port = listener.getsockname()[1]
        print(f"tinyhttp: listening on http://{host or 'localhost'}:{port}",
              flush=True)

        # Connections waiting for their next request:
        # {conn: (address, deadline)}.
        idle = {}
        while True:
            # Wait for a new client, or the next request on an idle
            # connection, until the nearest idle one is due to close.
            timeout = None
            if idle:
                nearest = min(deadline for _, deadline in idle.values())
                timeout = max(0, nearest - time.monotonic())
            readable, _, _ = select.select([listener, *idle], [], [], timeout)

            for conn in readable:
                if conn is listener:
                    # A new socket for talking to that one client. The
                    # listener keeps listening.
                    conn, address = listener.accept()
                    kept = False
                else:
                    address, _ = idle.pop(conn)
                    kept = True
                if serve(conn, address, app, kept,
                         keep_alive_timeout and len(idle) < MAX_IDLE):
                    idle[conn] = (address,
                                  time.monotonic() + keep_alive_timeout)
                else:
                    conn.close()

            # Closed quietly, with no 408, as gunicorn and nginx do.
            now = time.monotonic()
            for conn, (_, deadline) in list(idle.items()):
                if deadline <= now:
                    del idle[conn]
                    conn.close()


def serve(conn, address, app, kept, may_keep):
    """Serve conn's requests until it closes or waits for its next one.

    kept says conn has served a request before, and may_keep whether it
    can stay open after this one. Returns True to keep it open.
    """
    rest = b""
    try:
        while True:
            rest = handle(conn, address, app, rest, kept, may_keep)
            if rest is None:
                return False
            if not rest:
                return True
            # The client sent its next request before this reply. Those
            # bytes are already read, so select() won't report them: serve
            # them now.
            kept = True
    except OSError as error:
        # Such as a reset, or a reply to a client that's gone. Only this
        # connection is lost, not the server and every idle one with it.
        log(f"{address[0]}:{address[1]}", f"connection failed ({error})")
        return False


def handle(conn, address, app, rest, kept, may_keep):
    """Serve one request, starting with rest, bytes already read from conn.

    Returns the bytes read past the request if conn stays open, or None to
    close it.
    """
    client = f"{address[0]}:{address[1]}"
    try:
        received = read_head(conn, rest)
        if received is None:
            # Closing between requests is how a kept connection ends.
            if not kept:
                log(client, "closed before sending a request")
            return None
        head, rest = received
        request = parse_head(head)
        length = body_length(request.headers)
    except BadRequest as error:
        # Where the request ends is unknown, so the connection can't go on.
        log(client, f"400 ({error})")
        conn.sendall(error_response("400 Bad Request", str(error)))
        close_gently(conn)
        return None

    received = read_body(conn, rest, length)
    if received is None:
        log(client, "closed before sending the whole body")
        return None
    request.body, rest = received

    try:
        environ = build_environ(request, conn.getsockname(), address)
        status, headers, body = get_response(app, environ)
    except Exception:
        # A bug in the app mustn't stop the server: log it, answer 500, and
        # carry on with the next connection.
        log(client, f"{request.method} {request.path} 500, the app failed:")
        traceback.print_exc()
        conn.sendall(error_response("500 Internal Server Error",
                                    "internal server error"))
        return None

    keep = may_keep and keep_alive(request)
    if not keep:
        connection = "close"
    elif request.version == "HTTP/1.0":
        # 1.0 closes unless told otherwise, so say it stays open.
        connection = "keep-alive"
    else:
        connection = None
    response = make_head(status, headers, len(body), connection)
    # A HEAD reply has GET's headers and no body. Sending one anyway would
    # be read as the start of the next reply on a kept connection.
    if request.method != "HEAD":
        response += body

    log(client, f"{request.method} {request.path} {status.split(' ')[0]}")
    conn.sendall(response)
    return rest if keep else None


def read_head(conn, buffer=b""):
    """Read the request line and headers: everything up to the blank line.

    buffer is what's already been read from conn, past the last request.
    Returns (head, rest): the head as bytes, without the blank line, and
    any bytes that came after it, which are the start of the body. Returns
    None if the client closed the connection first. Raises BadRequest if
    the head doesn't fit in MAX_HEAD_SIZE.
    """
    while True:
        end = buffer.find(b"\r\n\r\n")
        if end != -1 and end + 4 <= MAX_HEAD_SIZE:
            # A recv can take the head and the start of the body together,
            # so hand back what's past the blank line for read_body.
            return buffer[:end], buffer[end + 4:]
        # Either there's no blank line yet and no room left for one, or
        # there is one but it ends past the limit.
        if len(buffer) >= MAX_HEAD_SIZE:
            raise BadRequest(f"headers longer than {MAX_HEAD_SIZE} bytes")
        # recv returns as soon as any bytes arrive, not a whole request, so
        # keep adding to the buffer until the blank line shows up.
        chunk = conn.recv(4096)
        if not chunk:
            # b"" means the client closed its side. Half a request is no
            # use, and there's no one left to send an error to.
            return None
        buffer += chunk


def read_body(conn, rest, length):
    """Read a body of length bytes, starting with rest from read_head.

    Returns (body, rest): the body, and any bytes past it, which are the
    start of the next request. Returns None if the client closed the
    connection first.
    """
    body = rest
    while len(body) < length:
        chunk = conn.recv(4096)
        if not chunk:
            return None
        body += chunk
    return body[:length], body[length:]


def close_gently(conn):
    """Let the client read our reply when we stopped reading its request.

    Closing a socket with unread data in its buffer makes the kernel reset
    the connection, and the reset can throw away the reply before the
    client reads it. So say we've finished sending, then read and discard
    what the client still sends, up to a limit, before the caller closes.
    nginx calls this a lingering close.
    """
    conn.shutdown(socket.SHUT_WR)
    conn.settimeout(1)
    discarded = 0
    try:
        while discarded < 64 * 1024:
            chunk = conn.recv(4096)
            if not chunk:
                break
            discarded += len(chunk)
    except OSError:
        # Timed out or reset: the client had its chance.
        pass


def make_head(status, headers, length, connection):
    """Build a response's status line and headers as bytes.

    status is such as "200 OK", headers a list of (name, value) pairs, and
    length the body's size in bytes. connection is the Connection header's
    value, or None for none. Content-Length and Connection are the server's
    to set, so any the app gave are replaced.
    """
    lines = [f"HTTP/1.1 {status}"]
    for name, value in headers:
        if name.lower() not in ("content-length", "connection"):
            lines.append(f"{name}: {value}")
    # Content-Length counts bytes, not characters.
    lines.append(f"Content-Length: {length}")
    if connection is not None:
        lines.append(f"Connection: {connection}")
    # Lines end in \r\n, as HTTP requires, and a blank line separates the
    # headers from the body. The PEP says header text is latin-1.
    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("latin-1")


def error_response(status, message):
    """A plain-text response for the server's own errors, such as a 400.

    The connection closes after it.
    """
    headers = [("Content-Type", "text/plain; charset=utf-8")]
    body = f"{message}\n".encode("utf-8")
    return make_head(status, headers, len(body), "close") + body


def log(client, message):
    # flush, so the line appears now even when output goes to a file.
    print(f"{client} {message}", flush=True)
