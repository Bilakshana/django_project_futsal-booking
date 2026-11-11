# Futsal Court Booking System

Django + DRF API where a player **holds a slot -> pays an advance with Khalti -> booking is confirmed**.
Celery (Redis broker) handles slot generation, hold expiry, reminders and wallet credits.

Roles: `player`, `owner`, `admin`. Apps: `accounts`, `courts`, `bookings`, `payments`, `wallet`.

## Setup

Needs Python 3.12+ and a running Redis (`redis://localhost:6379/0`).
On Windows run Redis with Docker (`docker run -p 6379:6379 redis`), WSL, or Memurai.

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp sample.env .env              # Windows: copy sample.env .env  -- then edit .env
```

Put your **Khalti sandbox secret key** in `.env` as `KHALTI_TOKEN` (get one at https://test-admin.khalti.com).
`.env` is git-ignored; never commit it.

```bash
python manage.py migrate
python manage.py createsuperuser
```

## Run (three terminals, plus Redis)

```bash
python manage.py runserver
```

```bash
# Linux/macOS
celery -A config worker -l info
# Windows (prefork isn't supported there)
celery -A config worker -l info --pool=solo
```

```bash
celery -A config beat -l info
```

Optional monitoring UI at http://localhost:5555:

```bash
celery -A config flower
```

Docs: http://localhost:8000/api/swagger/ - admin: http://localhost:8000/admin/

Beat runs (`CELERY_BEAT_SCHEDULE`, stored by django-celery-beat):
`generate_daily_slots` 00:05 nightly, `send_booking_reminder` every 5 min, `mark_completed_bookings` every 10 min.

## Tests

```bash
python manage.py test
```

Tests need neither Redis nor Khalti: Celery runs eagerly on an in-memory broker and Khalti calls are mocked.

## Booking flow

1. `POST /api/accounts/register/` (role `player` or `owner`), then `POST /api/login/` for a JWT (`Authorization: Bearer <access>`).
2. Owner: `POST /api/courts/` -> the court's next 7 days of slots are generated straight away.
3. Player: `GET /api/courts/<id>/slots/?date=YYYY-MM-DD&status=available`.
4. Player: `POST /api/bookings/hold/` `{"slot": <id>}` -> slot becomes `held`, booking `pending`, and a `payment_id` is returned. `release_held_slot` is queued with `countdown=600`.
5. Player: `POST /api/payment/initiate/<payment_id>/` -> returns Khalti's `payment_url`; open it and pay with a [sandbox test account](https://docs.khalti.com/khalti-epayment/#test-credentials).
6. Khalti redirects the browser to `/payment/callback/?pidx=...`. The server **ignores the query-string status** and calls Khalti's `POST /epayment/lookup/`; only if that says `Completed` for exactly the expected amount is the booking confirmed (slot -> `booked`) and `credit_wallet` queued.
7. `credit_wallet` credits the court owner's `balance` and writes a `Statement` (`GET /api/wallet/statements/`).

Other endpoints: `GET /api/bookings/` (role-scoped), `POST /api/bookings/<id>/cancel/` (unpaid only), `GET /api/accounts/me/`, `GET /api/accounts/list/` (admin).

## Design notes

- **No double booking:** `hold_slot` runs in `transaction.atomic()` and `select_for_update()`s the Slot row; `UNIQUE(court, date, start_time)` on `Slot` and a partial unique constraint (one live booking per slot) are the database-level backstop.
- **Callback is idempotent:** completed payments return early without calling Khalti; otherwise the Booking, Slot and Paymentlog rows are locked (always in that order) inside `transaction.atomic()` and re-checked. `Statement` has `UNIQUE(types, reference)`, so a payment can't be credited twice.
- **Late payments:** if Khalti confirms a payment after the hold expired, the booking is revived when the slot is still free; if someone else took it, the log becomes `refund_required` (money received, owner not credited, refund by hand in the Khalti dashboard).
- Tasks are dispatched with `transaction.on_commit`, so a worker never sees a row that isn't committed yet.

## Known limits

- SQLite ignores `select_for_update` (it serialises writers instead). Use PostgreSQL (see `sample.env`) for real concurrent load; the constraints protect you either way.
- Refunds are not automated, and cancelling a *paid* booking is not supported.
- Not exercised against a live Redis or the live Khalti sandbox in development: automated tests mock both. Do one sandbox payment end to end before demoing.
