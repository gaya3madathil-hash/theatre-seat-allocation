"""End-to-end tests: starts ./server on a free port and drives the JSON API."""
import json
import os
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.environ.get("SERVER_BIN", "./server")
proc = None
base = ""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def setUpModule():
    global proc, base
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([BIN], cwd=ROOT, env={**os.environ, "PORT": str(port)},
                            stdout=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


def tearDownModule():
    proc.terminate()
    proc.wait(timeout=5)


def call(path, method="POST", **params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{base}/api/{path}" + (f"?{qs}" if qs else ""), method=method)
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def seat(d, label, n):
    row = next(r for r in d["rows"] if r["label"] == label)
    return next(s for s in row["seats"] if s["n"] == n)


class TheatreTests(unittest.TestCase):
    def setUp(self):
        call("reset", show="all")      # every show empty, booking ids back to 1

    def test_prices_by_tier(self):
        d = call("seats", method="GET")
        self.assertEqual(d["total"], 60)
        self.assertEqual([r["price"] for r in d["rows"]], [500, 500, 350, 350, 200, 200])
        self.assertEqual([t["price"] for t in d["tiers"]], [500, 350, 200])

    def test_book_two_people_in_one_request(self):
        d = call("book", tickets="A1:Asha,A2:Ravi")
        self.assertTrue(d["ok"], d["message"])
        self.assertEqual(d["booked"], 2)
        self.assertEqual(d["sales"], 1000)
        b = d["bookings"][0]
        self.assertEqual([t["name"] for t in b["tickets"]], ["Asha", "Ravi"])
        self.assertEqual(seat(d, "A", 1)["name"], "Asha")
        self.assertEqual(seat(d, "A", 2)["name"], "Ravi")
        self.assertEqual(seat(d, "A", 1)["bk"], b["id"])

    def test_group_across_price_tiers(self):
        d = call("book", tickets="B5:Meena,C5:Kiran,F5:Dev")
        self.assertTrue(d["ok"], d["message"])
        self.assertIn("1050", d["message"])
        self.assertEqual(d["sales"], 500 + 350 + 200)

    def test_group_booking_is_all_or_nothing(self):
        call("book", tickets="A1:Asha")
        d = call("book", tickets="D1:Zed,A1:Clash,E1:Yan")
        self.assertFalse(d["ok"])
        self.assertEqual(d["booked"], 1)                 # nothing else got booked
        self.assertEqual(seat(d, "D", 1)["b"], 0)
        self.assertEqual(seat(d, "E", 1)["b"], 0)
        self.assertEqual(len(d["bookings"]), 1)          # failed attempt made no booking
        d = call("book", tickets="D1:Zed")
        self.assertEqual(d["bookings"][-1]["id"], 2)     # ids are not burned by failures

    def test_rejects_bad_requests(self):
        self.assertFalse(call("book", tickets="A1:X,A1:Y")["ok"])        # same seat twice
        self.assertFalse(call("book", tickets="A1:")["ok"])               # no name
        self.assertFalse(call("book", tickets="")["ok"])                  # nothing picked
        self.assertFalse(call("book", tickets="Z9:Nobody")["ok"])         # no such seat
        self.assertFalse(call("book", tickets="garbage")["ok"])
        many = ",".join(f"{r}{n}:P{r}{n}" for r in "AB" for n in range(1, 7))  # 12 seats
        d = call("book", tickets=many)
        self.assertFalse(d["ok"])
        self.assertEqual(d["booked"], 0)

    def test_cancel_one_ticket_refunds_minus_fee(self):
        call("book", tickets="A1:Asha,A2:Ravi")
        d = call("cancel", booking=1, seat="A1")
        self.assertTrue(d["ok"], d["message"])
        self.assertIn("450", d["message"])               # 500 - 10%
        self.assertEqual(seat(d, "A", 1)["b"], 0)
        self.assertEqual(seat(d, "A", 2)["b"], 1)        # the other person keeps their seat
        self.assertEqual(d["refunded"], 450)
        self.assertEqual(d["sales"], 500)
        # the freed seat can be booked again
        self.assertTrue(call("book", tickets="A1:Newcomer")["ok"])

    def test_cancel_whole_booking(self):
        call("book", tickets="B5:Meena,C5:Kiran,F5:Dev")
        d = call("cancel", booking=1)
        self.assertTrue(d["ok"], d["message"])
        self.assertEqual(d["refunded"], 450 + 315 + 180)
        self.assertEqual(d["booked"], 0)
        self.assertEqual(d["sales"], 0)
        self.assertTrue(all(t["cancelled"] for t in d["bookings"][0]["tickets"]))

    def test_cancel_by_seat_only(self):
        call("book", tickets="E3:Pia")
        d = call("cancel", row="E", num=3)
        self.assertTrue(d["ok"], d["message"])
        self.assertEqual(d["refunded"], 180)

    def test_cancel_errors(self):
        call("book", tickets="A1:Asha")
        self.assertTrue(call("cancel", booking=1)["ok"])
        self.assertFalse(call("cancel", booking=1)["ok"])             # already cancelled
        self.assertFalse(call("cancel", booking=1, seat="A1")["ok"])  # ticket already cancelled
        self.assertFalse(call("cancel", booking=99)["ok"])            # unknown booking
        self.assertFalse(call("cancel", row="A", num=5)["ok"])        # seat not booked
        self.assertFalse(call("cancel")["ok"])

    def test_cancelled_seat_is_not_cancelled_by_old_ticket(self):
        call("book", tickets="A1:Asha")
        call("cancel", booking=1)
        call("book", tickets="A1:Bela")                               # booking 2 now owns A1
        d = call("cancel", booking=1, seat="A1")                      # stale cancel of booking 1
        self.assertFalse(d["ok"])
        self.assertEqual(seat(d, "A", 1)["name"], "Bela")

    def test_auto_group_together(self):
        d = call("auto", names="Asha, Ravi, Meena", tier="economy")
        self.assertTrue(d["ok"], d["message"])
        self.assertIn("E1 to E3", d["message"])
        self.assertIn("600", d["message"])
        self.assertEqual([seat(d, "E", n)["name"] for n in (1, 2, 3)], ["Asha", "Ravi", "Meena"])

    def test_auto_skips_booked_seats(self):
        call("book", tickets="A3:Block")
        d = call("auto", names="P,Q,R,S,T,U,V,W", tier="premium")     # needs 8 in a row
        self.assertTrue(d["ok"], d["message"])
        self.assertIn("B1 to B8", d["message"])                       # row A has only 7 after A3

    def test_auto_failures(self):
        self.assertFalse(call("auto", names="")["ok"])
        self.assertFalse(call("auto", names="A", tier="gold")["ok"])
        self.assertFalse(call("auto", names=",".join("abcdefghijk"))["ok"])   # 11 people

    def test_mutations_require_post(self):
        for path in ("book", "cancel", "auto", "reset"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                call(path, method="GET")
            self.assertEqual(cm.exception.code, 405)

    def test_names_are_sanitised(self):
        d = call("book", tickets='A1:Ev"il\\name')
        self.assertTrue(d["ok"])
        self.assertEqual(seat(d, "A", 1)["name"], "Evilname")

    def test_unicode_name_roundtrip(self):
        d = call("book", tickets="A1:Zoë")
        self.assertEqual(seat(d, "A", 1)["name"], "Zoë")

    # ---------- multiple shows ----------

    def test_show_list(self):
        d = call("seats", method="GET")
        self.assertEqual([s["id"] for s in d["shows"]], [1, 2, 3])
        self.assertEqual(d["show"]["id"], 1)                       # default show
        self.assertEqual([s["from"] for s in d["shows"]], [200, 250, 120])
        self.assertTrue(all(s["free"] == 60 and s["total"] == 60 for s in d["shows"]))

    def test_each_show_has_its_own_prices(self):
        for sid, prices in ((1, [500, 350, 200]), (2, [600, 400, 250]), (3, [300, 200, 120])):
            d = call("seats", method="GET", show=sid)
            self.assertEqual(d["show"]["id"], sid)
            self.assertEqual([t["price"] for t in d["tiers"]], prices)
            self.assertEqual([r["price"] for r in d["rows"]], [prices[0]] * 2 + [prices[1]] * 2 + [prices[2]] * 2)
        d = call("book", show=2, tickets="A1:Asha,E1:Ravi")
        self.assertTrue(d["ok"], d["message"])
        self.assertEqual(d["sales"], 600 + 250)

    def test_seat_maps_are_independent(self):
        self.assertTrue(call("book", show=1, tickets="A1:Asha")["ok"])
        self.assertTrue(call("book", show=2, tickets="A1:Ravi")["ok"])   # same seat, other show
        d3 = call("seats", method="GET", show=3)
        self.assertEqual(seat(d3, "A", 1)["b"], 0)
        d1 = call("seats", method="GET", show=1)
        self.assertEqual(seat(d1, "A", 1)["name"], "Asha")
        self.assertEqual(d1["booked"], 1)
        d = call("seats", method="GET")
        self.assertEqual([s["free"] for s in d["shows"]], [59, 59, 60])
        self.assertFalse(call("book", show=1, tickets="A1:Clash")["ok"])  # still taken in show 1

    def test_booking_ids_are_unique_across_shows(self):
        self.assertEqual(call("book", show=2, tickets="A1:A")["bookings"][-1]["id"], 1)
        self.assertEqual(call("book", show=3, tickets="A1:B")["bookings"][-1]["id"], 2)
        self.assertEqual(call("book", show=1, tickets="A1:C")["bookings"][-1]["id"], 3)
        d = call("seats", method="GET", show=3)
        self.assertEqual([b["id"] for b in d["bookings"]], [2])     # only this show's bookings

    def test_cancel_only_works_inside_its_own_show(self):
        call("book", show=1, tickets="A1:Asha")
        d = call("cancel", show=2, booking=1)
        self.assertFalse(d["ok"])
        self.assertIn("not found for this show", d["message"])
        self.assertEqual(call("seats", method="GET", show=1)["booked"], 1)   # untouched
        self.assertTrue(call("cancel", show=1, booking=1)["ok"])

    def test_refund_uses_that_shows_price(self):
        call("book", show=3, tickets="A1:Kid,F1:Kid2")
        d = call("cancel", show=3, booking=1, seat="A1")
        self.assertIn("270", d["message"])                          # 300 - 10%
        d = call("cancel", show=3, booking=1)
        self.assertEqual(d["refunded"], 270 + 108)                  # 120 - 10% = 108

    def test_auto_group_uses_show_pricing(self):
        d = call("auto", show=3, names="Asha,Ravi,Meena", tier="economy")
        self.assertTrue(d["ok"], d["message"])
        self.assertIn("360", d["message"])                          # 3 x 120
        self.assertEqual(call("seats", method="GET", show=1)["booked"], 0)

    def test_reset_one_show_keeps_the_others(self):
        call("book", show=1, tickets="A1:Asha")
        call("book", show=2, tickets="A1:Ravi")
        d = call("reset", show=1)
        self.assertEqual(d["booked"], 0)
        self.assertEqual(call("seats", method="GET", show=2)["booked"], 1)

    def test_unknown_show_is_rejected(self):
        for sid in (0, 9, 42):
            d = call("book", show=sid, tickets="A1:Asha")
            self.assertFalse(d["ok"])
        self.assertEqual(call("seats", method="GET", show=1)["booked"], 0)

    def test_serves_index(self):
        with urllib.request.urlopen(base + "/") as r:
            self.assertIn("Curtain Call", r.read().decode())


if __name__ == "__main__":
    unittest.main(verbosity=2)
