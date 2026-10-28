# TODO

What tinyhttp needs, step by step. The steps are the ones in
`../TODO.md`, which has the plan for the whole project; this file
breaks tinyhttp's share of them into parts and tracks known gaps.

Related notes: [PRE_FORK.md](PRE_FORK.md) for why one connection at a
time breaks, and how pre-fork workers fix most of it.

## Step 1: the web server, up and running

- [x] Part 1: the package, so `python -m tinyhttp` starts it
- [x] Part 2: socket, bind, listen, accept, and the same reply to
      every request
- [x] Part 3: read the whole head, up to the blank line, with a size
      limit, a `400` when it's too big, and a lingering close so the
      client gets the `400`
- [x] Part 4: parse the request line and headers into a `Request`
      (`request.py`), with a `400` for anything malformed

## Step 2: WSGI

- [x] Part 1: read the request body: `Content-Length` bytes, starting
      with what `read_head` read past the blank line, up to 1 MB.
      `Request` carries it, for `environ["wsgi.input"]`. A bad length,
      too long a body, or a chunked one gets `400`
- [x] Part 2: WSGI, the server's side only (`wsgi.py`): build
      `environ` from the `Request`, call `app(environ, start_response)`,
      and write what it returns, or `500` if the app fails.
      `python -m tinyhttp module:name` picks the app, as gunicorn does;
      with none named it runs `echo.py`, which replies with what it was
      given. Test it with the webapp once it exists

## Known gaps

Follow-ups, nice to have. tinyhttp is a simple server to learn from, so
full HTTP compliance and precise error statuses aren't goals; nothing in
the plan needs these.

- [ ] No read timeout: a client that connects and sends nothing holds
      the server forever (see `PRE_FORK.md`). `conn.settimeout(...)`
      before `read_head`, and `408 Request Timeout` when it fires.
- [ ] Two `Host` headers get joined into `"a, b"`, like any repeated
      header. The standard says that's a `400`.
- [ ] Every error is `400`, with a message saying why. More precise
      statuses would be `413 Content Too Large` for a body over the
      limit, `501 Not Implemented` for chunked bodies, and `505 HTTP
      Version Not Supported` for `HTTP/2.0`. That needs errors to carry
      their status.
- [ ] Bodies are marked out only by `Content-Length`, the size up
      front, in requests and responses. HTTP/1.1 has other ways, which
      tinyhttp doesn't support. This is a simple server to learn from,
      not a match for nginx's or gunicorn's.
  - Requests: `Transfer-Encoding: chunked`, a body sent as pieces that
    each start with their size, ending with an empty one, is refused
    with `400`. HTTP/1.1 says every server must understand it, but
    nothing in the plan sends one: forms and the JSON API send
    `Content-Length`.
  - Responses: the server collects the app's whole body before sending
    it, so `Content-Length` is always known. It never sends a chunked
    response, which streams a body as it's made, or ends a body by
    closing the connection, as HTTP/1.0 did. So a large or slow
    response waits in memory until it's done, where gunicorn would
    stream it. Fine for pages and small JSON.
- [ ] Replies to `HEAD` include the body. The server treats every
      method the same, but HTTP says a `HEAD` reply has the headers a
      `GET` would get and no body. gunicorn drops the body itself, since
      apps such as Flask build it anyway.
- [ ] `Expect: 100-continue` is ignored. curl sends it for bodies over
      1 MB and waits a second for `100 Continue` before sending the body
      anyway. Nothing in the plan sends bodies that big (no uploads, and
      browsers never send `Expect`), and bodies over the 1 MB limit are
      refused from the header alone. Add it if uploads arrive.
- [ ] Give `close_gently` a total time limit, not only a byte cap. The
      1-second timeout only fires after a second of silence, so a client
      sending 1 byte every 0.9 seconds keeps us draining for hours
      before reaching 64 KB. nginx's `lingering_time` caps the whole
      drain at 30 seconds; a deadline from `time.monotonic()` would do
      the same.
