"""The server: socket, bind, listen, accept, read, respond."""

import socket

HOST = ""     # Every network interface, so other machines can reach it too.
PORT = 8000

# The same reply for every request until the request gets parsed. Lines end
# in \r\n, as HTTP requires, and a blank line separates headers from body.
BODY = b"hello from tinyhttp\n"
RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: " + str(len(BODY)).encode("ascii") + b"\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    + BODY
)


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
    # One recv may not hold the whole request; reading it properly is part
    # 3. We read anyway, because closing a socket with unread data makes the
    # kernel reset the connection, and the client may never see our reply.
    request = conn.recv(4096)
    first_line = request.split(b"\r\n", 1)[0].decode("latin-1")
    # flush, so the log line appears now even when output goes to a file.
    print(f"{address[0]}:{address[1]} {first_line}", flush=True)
    # send may write only part of the data; sendall loops until it's all out.
    conn.sendall(RESPONSE)
