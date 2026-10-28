# TODO

What tinyhttp needs, step by step. The steps are the ones in
`../TODO.md`, which has the plan for the whole project; this file
breaks tinyhttp's share of them into parts and tracks known gaps.

## Step 1: the web server, up and running

- [x] Part 1: the package, so `python -m tinyhttp` starts it
- [x] Part 2: socket, bind, listen, accept, and the same reply to
      every request
- [x] Part 3: read the whole head, up to the blank line, with a size
      limit, a `400` when it's too big, and a lingering close so the
      client gets the `400`
- [x] Part 4: parse the request line and headers into a `Request`
      (`request.py`), with a `400` for anything malformed
- [ ] Part 5: routing: `GET /health` gets `200`, unknown paths `404`.
      Remove `describe()` from `server.py`
- [ ] Part 6: break it on purpose with `nc` and type nothing; write
      down what happens to other clients

## Step 2: static files and WSGI

Only tinyhttp's share; the rest is in `../TODO.md`.

- [ ] Read the request body. Today it's thrown away: `read_head` drops
      any bytes after the blank line and nothing reads the rest. Then
      the normal path closes with body bytes unread, so the kernel
      resets the connection and the client can lose our reply.
  - Read `Content-Length` bytes: the leftovers from `read_head` first,
    then more `recv`s
  - A size limit, with `413 Content Too Large` past it
  - `Transfer-Encoding: chunked` gets `501` until it's supported
  - `Request` carries the body, for `environ["wsgi.input"]`
- [ ] Serve files under `/static/`, never outside the folder
- [ ] WSGI: build `environ` from the `Request`, call the app, and
      write what it returns

## Known gaps

- [ ] Two `Host` headers get joined into `"a, b"`, like any repeated
      header. The standard says that's a `400`.
- [ ] Every error is `400`. A well-formed but unsupported version
      such as `HTTP/2.0` should be `505 HTTP Version Not Supported`,
      which needs errors to carry their status.
- [ ] Give `close_gently` a total time limit, not only a byte cap. The
      1-second timeout only fires after a second of silence, so a client
      sending 1 byte every 0.9 seconds keeps us draining for hours
      before reaching 64 KB. nginx's `lingering_time` caps the whole
      drain at 30 seconds; a deadline from `time.monotonic()` would do
      the same.
