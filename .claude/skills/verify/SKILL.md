---
name: verify
description: Build, run and drive the Dandelionz Django API locally to observe changed behaviour at the HTTP surface.
---

# Verifying the Dandelionz backend

The surface is HTTP. Drive endpoints with `curl` against a local dev server.
There is no local Postgres on this machine and the user does not run one — use
the SQLite test settings for the server too.

## Launch

```bash
cd C:/Users/PC/Documents/Dandelionz
python manage.py migrate --run-syncdb --settings=e_commerce_api.test_settings
python manage.py runserver 8009 --noreload --settings=e_commerce_api.test_settings
```

`--run-syncdb` is required: `store/` has no local migrations (they are generated
on the VPS, see the migrations-not-tracked note), so its tables only exist if
syncdb creates them. `users/` and `transactions/` do have local migrations.

`test_settings` points `NAME` at `test_db.sqlite3` in the repo root. **Delete
that file when finished** — it is not the test runner's database (the runner
uses an in-memory one) and leaving it behind causes confusing stale-schema runs
later.

## Seeding

Creating any user trips a pre-existing bug: a `post_save` signal creates a
`Wallet`, but `Wallet.spendable_balance` is NOT NULL with no default, so it
raises `IntegrityError`. Disconnect the signal first:

```python
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from transactions import signals as tx_signals
post_save.disconnect(tx_signals.create_wallet_on_user_creation, sender=get_user_model())
```

Also note a `post_save` signal auto-creates a `Vendor` for VENDOR-role users —
fetch that row rather than creating a second one, or you hit a unique-constraint
error.

Products need `approval_status='approved'` and `publish_status='submitted'` to
appear publicly. Seed at least one product that is *not* approved, to confirm it
stays out of every public response.

## Flows worth driving

```bash
B=http://127.0.0.1:8009
curl -s "$B/store/products/?search=Sneakers"              # relevance ranking
curl -s "$B/store/products/?search=Umbro"                 # brand match
curl -s "$B/store/products/?search=waterproof"            # tag match
curl -s "$B/store/products/?search=Running&ordering=price" # explicit sort must win
curl -s "$B/store/products/suggestions/?q=Foot"           # typeahead
curl -s "$B/store/recommendations/?type=trending&limit=5"
curl -s "$B/store/recommendations/?type=related&product=<slug>"
curl -s "$B/store/recommendations/?type=for-you"          # anonymous -> trending
curl -s -X POST "$B/store/events/" -H 'Content-Type: application/json' \
     -d '{"product":"<slug>","event_type":"view"}'        # expect 202
```

Responses are `{"success": true, "data": ...}`. The product list is **not**
paginated (no `DEFAULT_PAGINATION_CLASS`, no `pagination_class`), so `data` is a
flat array and its length is the true total.

## Gotchas

- Always pass `--settings=e_commerce_api.test_settings`. Without it,
  `django.setup()` tries to reach Postgres and fails.
- The suite has ~37 pre-existing failures/errors, mostly the wallet signal above.
  Do not read those as regressions.
- Public endpoints must never expose products that are not approved+submitted.
  Probe this every time, including via `?type=related&product=<unapproved-slug>`.
