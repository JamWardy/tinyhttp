# How tinyhttp works

A WSGI server in Python, as gunicorn is: `python -m tinyhttp --host
127.0.0.1 --port 8001 --keep-alive 2 module:app`.

## The loop

One process runs one request at a time, as gunicorn's `gthread` worker
does with one thread. `select()` waits on the listener and on every
idle connection, one waiting for its next request:

- A new connection is accepted and its first request served at once.
- An idle connection that turns readable has its next request served.
- After either, a connection that stays open goes back to the idle set.

Serving a request blocks until it's done, so a client that connects
and sends nothing still holds everyone (see `PRE_FORK.md`). An idle
connection holds no one.

## Keep-alive

- HTTP/1.1 keeps the connection unless the request's `Connection` says
  `close`. HTTP/1.0 closes it unless `Connection` says `keep-alive`.
- A kept HTTP/1.1 reply has no `Connection` header, and a kept HTTP/1.0
  one has `Connection: keep-alive`. Any other reply has `Connection:
  close`, and the connection closes after it.
- It also closes after a `400`, a `500`, or a body cut short, and when
  `--keep-alive` is `0` or 1000 connections are already idle, as
  gunicorn's `gthread` caps them, so every socket stays under
  `select()`'s limit of 1023.
- Requests sent before the last reply (pipelined) are served in order.
- An idle connection is closed after `--keep-alive` seconds (2 by
  default, as gunicorn's), quietly, with no `408`. The shop's `justfile`
  passes 75, longer than tinyproxy keeps an idle connection, so it's
  tinyproxy that closes one, never a request racing tinyhttp's close.
- A reply to `HEAD` has `GET`'s headers and no body, as a body would be
  read as the start of the next reply.
