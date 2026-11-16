"""Notification simulator Assignment 3.

Place this file beside run.py in your selected project folder, then use
``import notification_service`` from application code.

This module does not send real emails or make network calls. Successful
notifications are stored in memory and disappear when Python exits. It is
a teaching simulator for a single process, not a production delivery system.
The application decides when to notify someone and how to handle failure.

Examples of recipients in the supplied templates:
    Library:          member.email
    Equipment rental: renter.email
    Inventory:        supplier.contact_email or a chosen staff address

For application tests, stub send_notification to return True or False, or
mock it to verify the recipient, subject, and message. Assert the resulting
application behavior too. Patch the dependency where your application uses it.
Use clear_notifications before and after tests that use the real simulator.
"""

# --- Riverside Library customizations (Assignment 3) -------------------------
# Function names, parameters and True/False return values are unchanged.
SUBJECT_PREFIX = "[Riverside Library] "

OVERDUE_MESSAGE_TEMPLATE = (
    "Hello {name},\n\n"
    "Your loan of \"{title}\" was due on {due_date} and is now "
    "{days_overdue} day(s) overdue. The current fine is ${fine:.2f}.\n"
    "Please return it as soon as possible.\n\n"
    "Riverside Library"
)

_notifications = []


def build_overdue_message(name: str, title: str, due_date: str,
                          days_overdue: int, fine: float) -> str:
    """Fill in the overdue-loan reminder template."""
    return OVERDUE_MESSAGE_TEMPLATE.format(
        name=name, title=title, due_date=due_date,
        days_overdue=days_overdue, fine=fine,
    )


def is_service_available() -> bool:
    """Return True for this local simulator.

    Tests may stub this function to return False to simulate an outage.
    No external service is contacted and no random failures are introduced.
    """
    return True


def send_notification(recipient: str, subject: str, message: str) -> bool:
    """Record a simulated notification and return True on success.

    Return False without recording anything if any argument is not a string,
    is empty or whitespace, the recipient has no "@" (a Riverside Library
    customization), or the simulated service is unavailable. Valid values
    are stored as supplied, with SUBJECT_PREFIX added to the subject.
    Repeated sends are recorded separately. True means the simulator
    recorded the message, not that email was delivered.
    """
    if not all(isinstance(value, str) and value.strip()
               for value in (recipient, subject, message)):
        return False

    if "@" not in recipient:
        return False

    if not is_service_available():
        return False

    _notifications.append({
        "recipient": recipient,
        "subject": SUBJECT_PREFIX + subject,
        "message": message,
    })
    return True


def get_notifications() -> list:
    """Return all recorded notifications in sending order.

    Return copies of the records so callers cannot modify the stored history.
    Each record has recipient, subject, and message string fields.
    """
    return [notification.copy() for notification in _notifications]


def clear_notifications() -> None:
    """Remove all recorded notifications, for example between test cases."""
    _notifications.clear()
