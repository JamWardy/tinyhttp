"""The server: socket, bind, listen, accept, read, respond."""

import errno
import socket
import sys
import traceback

from tinyhttp.request import BadRequest, body_length, parse_head
from tinyhttp.wsgi import build_environ, get_response

HOST = ""     # Every network interface, so other machines can reach it too.
PORT = 8000

# The most bytes we'll read looking for the end of the headers, blank line
# included. Without a limit, a client could send headers forever and we'd
# keep them all in memory. gunicorn's limits come to about the same.
MAX_HEAD_SIZE = 8192


def main(app, port=PORT):
    """Serve the WSGI app on port, one connection at a time, for ever."""
    # AF_INET is IPv4 and SOCK_STREAM is TCP: a reliable stream of bytes.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Without this, restarting soon after stopping fails with "Address
        # already in use", while the old connections wait out TIME_WAIT.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((HOST, port))
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            sys.exit(f"tinyhttp: port {port} is already in use")
        # The kernel queues up to this many connections that have finished
        # the TCP handshake but that we haven't accepted yet.
        listener.listen(16)
        print(f"tinyhttp: listening on http://localhost:{port}", flush=True)

        while True:
            # Blocks until a client connects, then returns a new socket for
            # talking to that one client. The listener keeps listening.
            conn, address = listener.accept()
            with conn:
                handle(conn, address, app)


def handle(conn, address, app):
    client = f"{address[0]}:{address[1]}"
    try:
        received = read_head(conn)
        if received is None:
            log(client, "closed before sending a request")
            return
        head, rest = received
        request = parse_head(head)
        length = body_length(request.headers)
    except BadRequest as error:
        log(client, f"400 ({error})")
        conn.sendall(error_response("400 Bad Request", str(error)))
        close_gently(conn)
        return

    body = read_body(conn, rest, length)
    if body is None:
        log(client, "closed before sending the whole body")
        return
    request.body = body

    try:
        environ = build_environ(request, conn.getsockname(), address)
        status, headers, body = get_response(app, environ)
        response = make_response(status, headers, body)
    except Exception:
        # A bug in the app mustn't stop the server: log it, answer 500, and
        # carry on with the next connection.
        log(client, f"{request.method} {request.path} 500, the app failed:")
        traceback.print_exc()
        conn.sendall(error_response("500 Internal Server Error",
                                    "internal server error"))
        return

    log(client, f"{request.method} {request.path} {status.split(' ')[0]}")
    conn.sendall(response)


def read_head(conn):
    """Read the request line and headers: everything up to the blank line.

    Returns (head, rest): the head as bytes, without the blank line, and
    any bytes that came after it, which are the start of the body. Returns
    None if the client closed the connection first. Raises BadRequest if
    the head doesn't fit in MAX_HEAD_SIZE.
    """
    buffer = b""
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

    Returns the body, or None if the client closed the connection first.
    """
    body = rest
    while len(body) < length:
        chunk = conn.recv(4096)
        if not chunk:
            return None
        body += chunk
    # Anything past length would be a second request on this connection,
    # which "Connection: close" tells the client not to send.
    return body[:length]


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


def make_response(status, headers, body):
    """Build a whole response as bytes.

    status is such as "200 OK", headers a list of (name, value) pairs, and
    body bytes. Content-Length and Connection are the server's to set, so
    any the app gave are replaced.
    """
    lines = [f"HTTP/1.1 {status}"]
    for name, value in headers:
        if name.lower() not in ("content-length", "connection"):
            lines.append(f"{name}: {value}")
    # Content-Length counts bytes, not characters.
    lines.append(f"Content-Length: {len(body)}")
    lines.append("Connection: close")
    # Lines end in \r\n, as HTTP requires, and a blank line separates the
    # headers from the body. The PEP says header text is latin-1.
    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("latin-1") + body


def error_response(status, message):
    """A plain-text response for the server's own errors, such as a 400."""
    headers = [("Content-Type", "text/plain; charset=utf-8")]
    return make_response(status, headers, f"{message}\n".encode("utf-8"))


def log(client, message):
    # flush, so the line appears now even when output goes to a file.
    print(f"{client} {message}", flush=True)
