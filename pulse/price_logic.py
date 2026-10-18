def should_trigger_alert(current_price, threshold_price):
    """Return True when the observed price is at or below the user's threshold."""
    return current_price <= threshold_price
