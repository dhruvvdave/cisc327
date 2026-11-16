"""Assignment 3 tests: notification success path and loan workflow.

Notification success path (stub + mock) for the overdue reminder, plus
coverage-directed tests for the loan workflow (loans.py / loan model).

send_notification is patched where the application uses it:
app.routes.loans.send_notification.
"""
from datetime import date, timedelta
from unittest.mock import patch

import notification_service
from app import store


def _setup_loan(client, *, days_overdue=3, title="Dune", name="Ada Lovelace",
                email="ada@example.com", copies=1):
    """Create a book, member and loan; backdate the due date by days_overdue."""
    book = client.post("/books", json={
        "title": title, "author": "Frank Herbert", "isbn": "111",
        "total_copies": copies}).get_json()
    member = client.post("/members", json={"name": name, "email": email}).get_json()
    loan = client.post("/loans", json={
        "book_id": book["id"], "member_id": member["id"]}).get_json()
    store.loans[loan["id"]].due_date = date.today() - timedelta(days=days_overdue)
    return book, member, loan


# ---------------------------------------------------------------- notifications

def test_overdue_reminder_sent_with_expected_arguments(client):
    _, _, loan = _setup_loan(client, days_overdue=3)
    due = (date.today() - timedelta(days=3)).isoformat()

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    body = response.get_json()
    assert body["notified"] is True
    assert body["reminded"] is True
    assert store.loans[loan["id"]].reminded is True
    mock_send.assert_called_once()
    recipient, subject, message = mock_send.call_args.args
    assert recipient == "ada@example.com"
    assert subject == "Overdue book reminder"
    assert "Ada Lovelace" in message
    assert '"Dune"' in message
    assert due in message
    assert "3 day(s) overdue" in message
    assert "$0.75" in message


def test_stub_success_marks_loan_reminded_and_reports_notified(client):
    _, _, loan = _setup_loan(client)

    with patch("app.routes.loans.send_notification", return_value=True):
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    assert response.get_json()["notified"] is True
    listed = client.get("/loans").get_json()
    assert [l["reminded"] for l in listed] == [True]


def test_reminder_goes_to_members_current_email(client):
    _, member, loan = _setup_loan(client)
    client.put(f"/members/{member['id']}", json={"email": "new@example.com"})

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    assert response.get_json()["notified"] is True
    assert mock_send.call_args.args[0] == "new@example.com"
    mock_send.assert_called_once()


def test_loan_one_day_overdue_is_reminded_with_one_day_fine(client):
    _, _, loan = _setup_loan(client, days_overdue=1)

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    assert response.get_json()["reminded"] is True
    message = mock_send.call_args.args[2]
    assert "1 day(s) overdue" in message
    assert "$0.25" in message
    mock_send.assert_called_once()


def test_reminding_one_loan_does_not_mark_other_loans(client):
    _, _, loan1 = _setup_loan(client, title="Dune")
    _, _, loan2 = _setup_loan(client, title="Emma", name="Bob", email="bob@example.com")

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        client.put(f"/loans/{loan1['id']}/remind")

    assert store.loans[loan1["id"]].reminded is True
    assert store.loans[loan2["id"]].reminded is False
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "ada@example.com"


def test_real_simulator_records_prefixed_notification(client):
    notification_service.clear_notifications()
    try:
        _, _, loan = _setup_loan(client)
        response = client.put(f"/loans/{loan['id']}/remind")

        assert response.status_code == 200
        assert response.get_json()["notified"] is True
        sent = notification_service.get_notifications()
        assert len(sent) == 1
        assert sent[0]["recipient"] == "ada@example.com"
        assert sent[0]["subject"] == "[Riverside Library] Overdue book reminder"
        assert "Dune" in sent[0]["message"]
    finally:
        notification_service.clear_notifications()


def test_missing_book_title_falls_back_to_generic_wording(client):
    book, _, loan = _setup_loan(client)
    client.delete(f"/books/{book['id']}")

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    assert response.get_json()["reminded"] is True
    assert '"a library book"' in mock_send.call_args.args[2]


# ------------------------------------------------- customized notification module

def test_service_rejects_recipient_without_at_sign_and_records_nothing():
    notification_service.clear_notifications()
    try:
        assert notification_service.send_notification("not-an-email", "s", "m") is False
        assert notification_service.get_notifications() == []
    finally:
        notification_service.clear_notifications()


def test_service_returns_false_when_unavailable():
    notification_service.clear_notifications()
    try:
        with patch("notification_service.is_service_available", return_value=False):
            assert notification_service.send_notification("a@b.com", "s", "m") is False
        assert notification_service.get_notifications() == []
    finally:
        notification_service.clear_notifications()


# ------------------------------------------------------- coverage-directed (loans)

def test_new_loan_json_starts_not_reminded_with_zero_renewals(client):
    _, _, loan = _setup_loan(client, days_overdue=0)
    assert loan["reminded"] is False
    assert loan["renewal_count"] == 0
    assert loan["return_date"] is None


def test_renewal_at_the_limit_boundary_second_ok_third_refused(client):
    _, _, loan = _setup_loan(client, days_overdue=0)
    original_due = store.loans[loan["id"]].due_date

    first = client.put(f"/loans/{loan['id']}/renew")
    second = client.put(f"/loans/{loan['id']}/renew")
    third = client.put(f"/loans/{loan['id']}/renew")

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 409)
    assert second.get_json()["renewal_count"] == 2
    assert store.loans[loan["id"]].due_date == original_due + timedelta(days=28)


def test_returned_book_can_be_checked_out_by_a_different_member(client):
    book, _, loan = _setup_loan(client, days_overdue=0)
    other = client.post("/members", json={"name": "Bob", "email": "bob@example.com"}).get_json()
    client.put(f"/loans/{loan['id']}/return")

    response = client.post("/loans", json={"book_id": book["id"], "member_id": other["id"]})

    assert response.status_code == 201
    assert response.get_json()["member_id"] == other["id"]
    assert store.books[book["id"]].available_copies == 0
