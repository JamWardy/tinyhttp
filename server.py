"""The server: socket, bind, listen, accept, read, respond."""

import socket

HOST = ""     # Every network interface, so other machines can reach it too.
PORT = 8000

# The most bytes we'll read looking for the end of the headers, blank line
# included. Without a limit, a client could send headers forever and we'd
# keep them all in memory. gunicorn's limits come to about the same.
MAX_HEAD_SIZE = 8192


class BadRequest(Exception):
    """The client sent something we can't treat as an HTTP request."""


def main():
    # AF_INET is IPv4 and SOCK_STREAM is TCP: a reliable stream of bytes.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Without this, restarting soon after stopping fails with "Address
        # already in use", while the old connections wait out TIME_WAIT.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        # The kernel queues up to this many connections that have finished
        # the TCP handshake but that we haven't accepted yet.
        listener.listen(16)
        print(f"tinyhttp: listening on http://localhost:{PORT}", flush=True)

        while True:
            # Blocks until a client connects, then returns a new socket for
            # talking to that one client. The listener keeps listening.
            conn, address = listener.accept()
            with conn:
                handle(conn, address)


def handle(conn, address):
    client = f"{address[0]}:{address[1]}"
    try:
        head = read_head(conn)
    except BadRequest as error:
        log(client, f"400 ({error})")
        conn.sendall(make_response("400 Bad Request", f"{error}\n"))
        close_gently(conn)
        return
    if head is None:
        log(client, "closed before sending a request")
        return

    first_line = head.split(b"\r\n", 1)[0].decode("latin-1")
    log(client, first_line)
    conn.sendall(make_response("200 OK", "hello from tinyhttp\n"))


def read_head(conn):
    """Read the request line and headers: everything up to the blank line.

    Returns them as bytes, without the blank line, or None if the client
    closed the connection first. Raises BadRequest if they don't fit in
    MAX_HEAD_SIZE.
    """
    buffer = b""
    while True:
        end = buffer.find(b"\r\n\r\n")
        if end != -1 and end + 4 <= MAX_HEAD_SIZE:
            # Any bytes after the blank line are the start of the body,
            # which nothing reads until requests can have one.
            return buffer[:end]
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


def make_response(status, body):
    """Build a whole response as bytes, from a status such as "200 OK"."""
    body = body.encode("utf-8")
    # Lines end in \r\n, as HTTP requires, and a blank line separates the
    # headers from the body. Content-Length counts bytes, not characters.
    head = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return head.encode("latin-1") + body


def log(client, message):
    # flush, so the line appears now even when output goes to a file.
    print(f"{client} {message}", flush=True)
