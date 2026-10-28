# One connection at a time vs pre-fork workers

tinyhttp's server (`server.py`) handles one connection at a time, in
one process. gunicorn, by default, runs several worker processes forked
from one master. This note says what goes wrong with one at a time, how
pre-forking fixes most of it, and what it leaves for later.

## One at a time: what tinyhttp has

`main` runs one loop, and does one thing at a time:

```python
while True:
    conn, address = listener.accept()   # wait for a client
    with conn:
        handle(conn, address)           # read, reply, close
```

While it's in `handle`, nothing calls `accept()`. New clients still
connect, because the kernel finishes their handshake and queues them on
the listener, but they wait in that queue until `handle` returns.

That's fine while every client sends its request at once. It breaks when
one doesn't:

1. `python3 -m tinyhttp`
2. In a second terminal, `nc localhost 8000`, and type nothing.
3. In a third, `curl localhost:8000/`. It hangs.
4. Ctrl-C the `nc`, and the curl finishes at once.

The server is stuck in `recv` in `read_head`, waiting for bytes `nc`
never sends. One idle connection costs the client nothing and stops the
whole server. Opening many slow connections on purpose is the Slowloris
attack (2009).

## Pre-fork workers: the alternative

A master process makes the listener, then copies itself with `fork()`
into several workers before any client arrives, hence "pre-fork".

```
master    socket(), bind(), listen(), then fork() × 4
          then only watches the workers: restarts any that die or hang

worker 1 ─┐
worker 2 ─┤  each runs the loop above:
worker 3 ─┤    while True: conn = listener.accept(); handle(conn)
worker 4 ─┘
```

- **`fork()` copies the whole process**, open sockets included. Every
  worker inherits the same listener, so all of them can `accept()` on
  it.
- **The kernel gives each connection to one worker that's waiting in
  `accept()`**, so a free worker. One stuck in `recv` for a slow client
  isn't waiting, so it gets nothing new.
- **The master never handles requests.** gunicorn's master also kills
  a worker that's been silent longer than `--timeout` (30 seconds by
  default) and starts a fresh one, so a stuck worker comes back.
- **Processes, not threads.** Python's GIL lets only one thread run
  Python code at a time, while each process has its own interpreter and
  runs truly in parallel. A crash in one worker also can't take down
  the rest. The cost is memory, though `fork()` shares the copied pages
  until one side writes to them (copy-on-write).

`handle` and the loop don't change. What changes is how many processes
run them.

## Side by side

| | One at a time | Pre-fork, N workers |
|---|---|---|
| Requests handled at once | 1 | N |
| Slow clients to stop everyone | 1 | N |
| Uses more than one CPU core | No | Yes |
| A crash in `handle` | Stops the server | Stops one worker; the master starts another |
| Memory | One process | N processes, sharing pages until written |
| Code | The loop in `main` | The same loop, plus a master that forks and watches |

## What pre-forking doesn't fix

It turns "one slow client stops everyone" into "N slow clients stop
everyone". N is small, because each worker is a whole process:
gunicorn's docs suggest 2 to 4 per CPU core. An attacker only needs to
open a few more `nc`s. The fixes for that are in `../TODO.md`:

- **A read timeout**, in this folder's `TODO.md` under Known gaps.
  Each slow client then holds a worker for seconds, not forever.
- **An event loop** (step 5, Performance), as nginx does: one process
  waits on many connections at once with `select` or `kqueue`, so a
  slow one costs a few bytes of memory, not a whole worker.
- **A reverse proxy** (step 5, "In front of the shop"): it reads each
  request in full before passing it on, so the workers behind it only
  see complete requests. That's why gunicorn's docs say to run it
  behind nginx.

"Requests at once" under Decisions in `../TODO.md` gives the order
these come in.
