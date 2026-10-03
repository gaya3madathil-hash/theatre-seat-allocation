# Curtain Call: Theatre Seat Allocation

A full stack project that shows a real use of the **linked list** data structure, written in **C**.

- **Backend:** C (`server.c`), POSIX sockets, no libraries. Exposes a small JSON API.
- **Frontend:** one HTML/CSS/JS page (`public/index.html`) served by the C server.
- **DSA concept:** singly linked lists.

## Features

- **Multiple shows:** a programme of three shows, each with its own date/time, seat map, ticket prices and bookings. Switch between them with the cards at the top; each card shows live availability.
- **Tiered prices per show:** Premium rows A-B, Standard rows C-D, Economy rows E-F. Prices differ by show:

  | Show | When | Premium | Standard | Economy |
  |---|---|---|---|---|
  | Midnight at the Mahal | Sat 10 Oct, 7:30 PM | ₹500 | ₹350 | ₹200 |
  | The Last Monsoon | Sun 11 Oct, 6:00 PM | ₹600 | ₹400 | ₹250 |
  | Jungle Tales (Matinee) | Sun 11 Oct, 11:00 AM | ₹300 | ₹200 | ₹120 |

- **Book for several people at once:** pick up to 10 seats, give each seat its own guest name, and book them in a single request. The booking is all-or-nothing: if any seat is taken, nothing is booked.
- **Cancellation:** cancel one ticket (tap a booked seat) or a whole booking. A **10% cancellation fee** is kept; the rest is refunded at the price that ticket was sold for. The seat is freed straight away.
- **Group seating:** enter names, choose a section, and the server finds a row with enough adjacent free seats.
- **Booking history:** each show lists its bookings with tickets, totals, and refunds. Booking numbers are unique across all shows.

## How the linked lists are used

```
shows -> Show 1 -> Show 2 -> Show 3 -> NULL
           |
           +-- hall:      Row A -> Row B -> ... -> Row F -> NULL
           |                |
           |                v
           |              Seat 1 -> Seat 2 -> ... -> Seat 10 -> NULL
           |
           +-- bookings:  Booking #1 -> Booking #4 -> ... -> NULL
                              |
                              v
                           Ticket A1 -> Ticket A2 -> ... -> NULL
```

| Feature | Linked list operation | Time |
|---|---|---|
| Build programme | Insert Show nodes at tail, each with its own hall | O(shows x rows x seats) |
| Find a show | Walk the show list | O(shows) |
| Find a seat | Traverse rows, then seats of that show | O(rows + seats) |
| Book n people at once | Validate n seats, then append a Booking node with n Ticket nodes | O(n x (rows + seats)) |
| Cancel a ticket / booking | Find Booking node in the show, walk its Ticket list, free the Seat node | O(bookings + tickets) |
| Seat a group together | Walk a row, track a run of free nodes | O(rows x seats) |
| Clear a show / everything | Free every node, rebuild | O(rows x seats + tickets) |

Nothing is stored in an array: shows, rows, seats, bookings and tickets are heap-allocated nodes joined by `next` pointers.

## API

Read-only calls use `GET`; everything that changes data must be `POST` (otherwise `405`). Every call takes an optional `show` (1, 2 or 3; default 1). Every response is the full JSON state of that show plus `ok`, `message`, and a `shows` summary list (title, time, seats free, cheapest price).

| Method | Path | Params |
|---|---|---|
| GET | `/api/seats` | `show` |
| POST | `/api/book` | `show`, `tickets` = `A1:Asha,A2:Ravi,C5:Meena` (seat:name pairs, 1 to 10) |
| POST | `/api/cancel` | `show`, `booking` (whole booking), plus optional `seat` (e.g. `A1`) for one ticket. `row` + `num` alone also works. |
| POST | `/api/auto` | `show`, `names` = `Asha,Ravi,Meena`, optional `tier` = `premium` / `standard` / `economy` / `any` |
| POST | `/api/reset` | `show` = one show's id (clears that show), or `all` (resets every show and numbering) |

Example:

```bash
curl -X POST "http://localhost:8080/api/book?show=2&tickets=A1:Asha,A2:Ravi"
# {"ok":1,"message":"Booking #1 confirmed for 2 people at The Last Monsoon. Total ₹1200.", ...}
curl -X POST "http://localhost:8080/api/cancel?show=2&booking=1&seat=A1"
# {"ok":1,"message":"Cancelled A1 (Asha) in booking #1. Refund ₹540 after the 10% fee.", ...}
```

A booking can only be cancelled through the show it belongs to.

## Run locally

```bash
make run          # or: gcc -O2 -o server server.c && ./server
# open http://localhost:8080
```

## Test

```bash
make test         # builds, starts the server on a free port, runs 26 API tests (needs python3)
```

## Deploy (Render, free tier)

1. Push this folder to a public GitHub repo.
2. On render.com choose **New > Web Service**, connect the repo, set **Runtime: Docker**.
3. Deploy. Render sets `PORT` automatically; copy the public URL into this README.

Live demo: https://theatre-seat-allocation-1.onrender.com

Note: bookings live in memory, so they reset when the service restarts. The server handles one request at a time, which is also what makes each group booking atomic.

## Changing the programme

Edit the `SHOW_DEFS` table at the top of `server.c` (title, date/time, three prices) and rebuild. The number of shows follows the table.
