# PulseNotify

Django REST Framework API for flight-price alerts, JWT authentication, PostgreSQL persistence, and asynchronous Celery jobs using Redis.

## Requirements

- Python 3.11+ (Python 3.12 is a safe choice)
- Docker Desktop
- Postman (for API scenarios)

## 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env`; replace `SECRET_KEY` and the database password. Do not commit `.env`.

If PostgreSQL is already using port 5432 on your machine, either stop the local PostgreSQL service or change the Compose mapping to `"5433:5432"` and set `POSTGRES_PORT=5433` in `.env`.

## 2. Start PostgreSQL and Redis

```bash
docker compose up -d
docker compose ps
```

This Compose file starts PostgreSQL and Redis. Django and the Celery worker/beat run locally, so the broker and database host values in `.env` use `127.0.0.1`.

## 3. Install and migrate

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py makemigrations pulse
python manage.py migrate
python manage.py check
python manage.py createsuperuser
```

`UserProfile` is automatically created for new users by a `post_save` signal. To grant admin-summary access to an application user, use Django shell:

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from pulse.models import UserProfile
u = get_user_model().objects.get(username="your_username")
u.profile.role = UserProfile.Role.ADMIN
u.profile.save()
```

The Django superuser flag does not automatically change `profile.role`; set the profile role explicitly for the API's admin summary.

## 4. Run the three processes

Use three terminals, each with `.venv` activated.

Terminal 1 — API server:

```bash
python manage.py runserver
```

Terminal 2 — Celery worker:

```bash
celery -A config worker --loglevel=info
```

Terminal 3 — Celery Beat scheduler:

```bash
celery -A config beat --loglevel=info
```

Beat schedules `pulse.tasks.check_prices` every 60 seconds. The task requests the local `/api/flights/price/` endpoint. When a threshold is reached, it calls `send_notification.delay(...)`; the worker creates a `NotificationLog` and marks the alert `triggered`.

## API endpoints

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register/` | Public | Register user and return JWT access token |
| POST | `/api/auth/login/` | Public | Authenticate and return JWT access token |
| POST | `/api/alerts/` | JWT | Create an alert for the authenticated user |
| GET | `/api/alerts/` | JWT | List only the authenticated user's alerts |
| DELETE | `/api/alerts/<id>/` | JWT | Deactivate own alert (does not delete row) |
| GET | `/api/flights/price/?route=DEL-BOM` | Public | Mock flight price |
| GET | `/api/admin/summary/` | JWT + admin profile role | Aggregate platform statistics |

### Example requests

Register:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"securepass123","email":"alice@example.com"}'
```

Create an alert (replace token):

```bash
curl -X POST http://127.0.0.1:8000/api/alerts/ \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"origin":"DEL","destination":"BOM","threshold_price":"4500.00"}'
```

The user's identity is taken from the JWT, never from request data.

## Postman collection

Import `postman/PulseNotify.postman_collection.json`. It includes the HTTP scenarios for registration, duplicate registration, login success/failure, protected alert creation, listing, deactivation, mock feed success/failure, and admin-summary access. The final scenario in the assignment is a database verification rather than an HTTP endpoint: after a notification fires, inspect the `pulse_notificationlog` table (or `notification_logs` if you customized `db_table`) in pgAdmin. With this model's default Django naming, the table is `pulse_notificationlog`.

Suggested run order:
1. Register a normal user and save `access` to the collection variable `userToken`.
2. Create/list/deactivate an alert.
3. For admin access, set one profile's role to `admin`, log in as that user, and save its `access` token to `adminToken`.
4. Keep the worker and beat running. For a deterministic smoke test, create an alert with a threshold above the maximum mock price for a known route, e.g. DEL-BOM threshold 9999. Wait up to 60 seconds, then verify a notification row and `triggered` alert status in PostgreSQL.

## Tests

```bash
python manage.py test
```

Tests cover threshold comparison, notification log creation, alert scoping, registration/profile creation, duplicate usernames, and admin-only access.

## Notes

- The brief calls for 13 scenarios; the notification-log check is performed in pgAdmin, not through a public API endpoint.
- Mock prices are random, so use a threshold above the route's maximum when manually verifying Celery.
- `send_notification` re-checks that the alert is still active and uses a transaction to avoid creating duplicate notifications for an already-triggered alert.
