import logging
import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from .models import NotificationLog, PriceAlert
from .price_logic import should_trigger_alert

logger = logging.getLogger(__name__)


@shared_task
def check_prices():
    # Query only active alerts, then fetch one price per distinct route.
    active_alerts = PriceAlert.objects.filter(status=PriceAlert.Status.ACTIVE)
    routes = active_alerts.values_list("origin", "destination").distinct()
    base_url = settings.PRICE_FEED_BASE_URL.rstrip("/")
    for origin, destination in routes:
        route = f"{origin}-{destination}"
        try:
            response = requests.get(
                f"{base_url}/api/flights/price/",
                params={"route": route},
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning("Price feed returned %s for %s", response.status_code, route)
                continue
            current_price = response.json().get("price")
            if current_price is None:
                logger.warning("Price feed omitted price for %s", route)
                continue
        except (requests.RequestException, ValueError) as exc:
            logger.exception("Unable to fetch price for %s: %s", route, exc)
            continue

        route_alerts = active_alerts.filter(origin=origin, destination=destination)
        for alert in route_alerts.iterator():
            if should_trigger_alert(float(current_price), float(alert.threshold_price)):
                # Required async dispatch: never call send_notification directly.
                send_notification.delay(alert.id, current_price)


@shared_task
def send_notification(alert_id, triggered_price):
    # Re-check state because the alert may have been deactivated after check_prices ran.
    with transaction.atomic():
        try:
            alert = PriceAlert.objects.select_for_update().get(pk=alert_id)
        except PriceAlert.DoesNotExist:
            logger.warning("Alert %s no longer exists", alert_id)
            return "alert-not-found"
        if alert.status != PriceAlert.Status.ACTIVE:
            return "alert-not-active"

        message = (
            f"Price alert triggered! {alert.origin}-{alert.destination} is now "
            f"₹{triggered_price} - below your threshold of ₹{alert.threshold_price}"
        )
        NotificationLog.objects.create(
            alert=alert,
            triggered_price=triggered_price,
            message=message,
        )
        alert.status = PriceAlert.Status.TRIGGERED
        alert.save(update_fields=["status"])
    return "notification-created"
