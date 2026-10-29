# TODO

What tinyhttp needs, step by step. The steps are the ones in
`../TODO.md`, which has the plan for the whole project; this file
breaks tinyhttp's share of them into parts and tracks known gaps.

Related notes: [PRE_FORK.md](PRE_FORK.md) for why one connection at a
time breaks, and how pre-fork workers fix most of it.

Python's standard library only. gunicorn and Flask are never imported,
called or run from this repo, tests included; they're for testing only,
in `../tinyAmazonTest/`. See the rules in `../tinyAmazonTest/TODO.md`.

No shortcuts from the standard library either. `http.server`,
`socketserver` and `wsgiref` already do this repo's job, from reading a
request to calling the app, so none of them are used here, not even in
part. Write it with `socket`.

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
- [x] Part 3: pick the port, as gunicorn's `-b` does:
      `python -m tinyhttp --port 8001 module:name`, with 8000 when none is
      given. `main` takes the port instead of reading `PORT`. Needed by
      the tests in `../tinyAmazonTest/`, so they don't clash with a
      server already on 8000, and by step 5's load balancer, which runs
      two servers, on `:8001` and `:8002`. Decided while building it:
  - `argparse` reads the command line, as gunicorn's does: reading
    arguments isn't the server's job, and it gives `--help` and usage
    errors. The port and app go in either order
  - A port that isn't a number from 1 to 65535 is a usage error. No
    port `0` for "any free one": the tests pick a free port themselves
  - A port already in use exits with one line saying so, not a
    traceback, as it's likely with several servers running
  - The port only, not the host as `-b` takes too: it still listens on
    every interface

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
- [ ] A `304 Not Modified` gets `Content-Length: 0`, as `make_response`
      adds one to every reply. The standard says a `304` either leaves
      it out or gives the length the full reply would have had.
      Browsers ignore it, since a `304` never has a body.
- [ ] No `Date` header. The standard says a server with a clock must
      send one, the time of the reply in GMT, such as `Date: Thu, 29
      Oct 2026 16:00:00 GMT`; caches use it to work out a reply's age.
      `make_response` would add it, as it does `Content-Length`.
      Browsers cope without it.
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
