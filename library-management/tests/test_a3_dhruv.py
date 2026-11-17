"""Assignment 3 tests: overdue reminder notifications and loan/UI coverage.

Success path (stub True and mock), failure path (stub False), non-trigger
paths (mock asserts no call), the customized notification service, and
coverage-directed tests for loans, the web UI, reservations and members.

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


def _make_loan(client, *, days_overdue=3, email="sam@example.com"):
    book = client.post("/books", json={
        "title": "Clean Code", "author": "Robert Martin", "isbn": "222",
        "total_copies": 2}).get_json()
    member = client.post("/members", json={"name": "Sam", "email": email}).get_json()
    loan = client.post("/loans", json={
        "book_id": book["id"], "member_id": member["id"]}).get_json()
    store.loans[loan["id"]].due_date = date.today() - timedelta(days=days_overdue)
    return book, member, loan


# ------------------------------------------------------- failed notification

def test_stub_failure_reports_not_notified_and_loan_stays_unreminded(client):
    _, _, loan = _make_loan(client)

    with patch("app.routes.loans.send_notification", return_value=False):
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    body = response.get_json()
    assert body["notified"] is False
    assert body["reminded"] is False
    assert store.loans[loan["id"]].reminded is False
    assert store.loans[loan["id"]].return_date is None


def test_failed_send_is_still_attempted_once_with_member_email(client):
    _, _, loan = _make_loan(client, email="sam@example.com")

    with patch("app.routes.loans.send_notification", return_value=False) as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 200
    assert response.get_json()["notified"] is False
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "sam@example.com"
    assert mock_send.call_args.args[1] == "Overdue book reminder"


def test_reminder_can_be_retried_after_a_failure(client):
    _, _, loan = _make_loan(client)

    with patch("app.routes.loans.send_notification", side_effect=[False, True]) as mock_send:
        first = client.put(f"/loans/{loan['id']}/remind")
        assert store.loans[loan["id"]].reminded is False
        second = client.put(f"/loans/{loan['id']}/remind")

    assert first.get_json()["notified"] is False
    assert second.get_json()["notified"] is True
    assert store.loans[loan["id"]].reminded is True
    assert mock_send.call_count == 2


def test_simulated_service_outage_is_reported_without_recording_anything(client):
    notification_service.clear_notifications()
    try:
        _, _, loan = _make_loan(client)
        with patch("notification_service.is_service_available", return_value=False):
            response = client.put(f"/loans/{loan['id']}/remind")

        assert response.status_code == 200
        assert response.get_json()["notified"] is False
        assert store.loans[loan["id"]].reminded is False
        assert notification_service.get_notifications() == []
    finally:
        notification_service.clear_notifications()


def test_member_with_invalid_email_is_not_notified(client):
    notification_service.clear_notifications()
    try:
        _, member, loan = _make_loan(client)
        store.members[member["id"]].email = "not-an-email"
        response = client.put(f"/loans/{loan['id']}/remind")

        assert response.status_code == 200
        assert response.get_json()["notified"] is False
        assert store.loans[loan["id"]].reminded is False
        assert notification_service.get_notifications() == []
    finally:
        notification_service.clear_notifications()


# ------------------------------------------------------------ non-trigger paths

def test_loan_not_yet_due_sends_no_notification(client):
    _, _, loan = _make_loan(client, days_overdue=-5)

    with patch("app.routes.loans.send_notification") as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 409
    assert response.get_json() == {"error": "Loan is not overdue"}
    assert store.loans[loan["id"]].reminded is False
    mock_send.assert_not_called()


def test_loan_due_today_is_not_overdue_and_sends_no_notification(client):
    _, _, loan = _make_loan(client, days_overdue=0)

    with patch("app.routes.loans.send_notification") as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 409
    assert store.loans[loan["id"]].reminded is False
    mock_send.assert_not_called()


def test_returned_loan_sends_no_notification(client):
    _, _, loan = _make_loan(client)
    client.put(f"/loans/{loan['id']}/return")

    with patch("app.routes.loans.send_notification") as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 400
    assert response.get_json() == {"error": "Loan already returned"}
    assert store.loans[loan["id"]].reminded is False
    mock_send.assert_not_called()


def test_unknown_loan_returns_404_and_sends_no_notification(client):
    with patch("app.routes.loans.send_notification") as mock_send:
        response = client.put("/loans/999/remind")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Loan not found"}
    mock_send.assert_not_called()


def test_loan_whose_member_no_longer_exists_sends_no_notification(client):
    _, member, loan = _make_loan(client)
    store.members.pop(member["id"])

    with patch("app.routes.loans.send_notification") as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Member not found"}
    assert store.loans[loan["id"]].reminded is False
    mock_send.assert_not_called()


def test_renewing_an_overdue_loan_makes_it_ineligible_for_a_reminder(client):
    _, _, loan = _make_loan(client, days_overdue=3)
    assert client.put(f"/loans/{loan['id']}/renew").status_code == 200

    with patch("app.routes.loans.send_notification") as mock_send:
        response = client.put(f"/loans/{loan['id']}/remind")

    assert response.status_code == 409
    assert store.loans[loan["id"]].reminded is False
    mock_send.assert_not_called()


# ------------------------------------- coverage-directed (books/members/UI/etc.)

def test_ui_return_twice_does_not_double_count_stock(client):
    book, _, loan = _make_loan(client, days_overdue=0)
    client.post(f"/ui/loans/{loan['id']}/return")
    after_first = store.books[book["id"]].available_copies
    response = client.post(f"/ui/loans/{loan['id']}/return")

    assert response.status_code == 302
    assert after_first == 2
    assert store.books[book["id"]].available_copies == 2


def test_ui_return_of_unknown_loan_redirects_and_changes_nothing(client):
    book, _, _ = _make_loan(client, days_overdue=0)

    response = client.post("/ui/loans/999/return")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/loans")
    assert store.books[book["id"]].available_copies == 1


def test_ui_return_when_book_was_deleted_still_marks_loan_returned(client):
    book, _, loan = _make_loan(client, days_overdue=0)
    store.books.pop(book["id"])

    response = client.post(f"/ui/loans/{loan['id']}/return")

    assert response.status_code == 302
    assert store.loans[loan["id"]].return_date == date.today()


def test_ui_delete_of_unknown_book_and_member_is_harmless(client):
    book, member, _ = _make_loan(client, days_overdue=0)

    assert client.post("/ui/books/999/delete").status_code == 302
    assert client.post("/ui/members/999/delete").status_code == 302
    assert list(store.books) == [book["id"]]
    assert list(store.members) == [member["id"]]


def test_reservation_filters_combine_book_and_member(client):
    b1 = client.post("/books", json={"title": "A", "author": "x", "isbn": "1"}).get_json()
    b2 = client.post("/books", json={"title": "B", "author": "y", "isbn": "2"}).get_json()
    m1 = client.post("/members", json={"name": "M1", "email": "m1@x.com"}).get_json()
    m2 = client.post("/members", json={"name": "M2", "email": "m2@x.com"}).get_json()
    for b, m in [(b1, m1), (b1, m2), (b2, m1)]:
        client.post("/reservations", json={"book_id": b["id"], "member_id": m["id"]})

    result = client.get(f"/reservations?book_id={b1['id']}&member_id={m1['id']}").get_json()

    assert len(result) == 1
    assert (result[0]["book_id"], result[0]["member_id"]) == (b1["id"], m1["id"])


def test_member_update_changes_email_and_is_visible_on_the_members_page(client):
    member = client.post("/members", json={"name": "Sam", "email": "old@x.com"}).get_json()
    client.put(f"/members/{member['id']}", json={"email": "new@x.com"})

    page = client.get("/ui/members").get_data(as_text=True)

    assert "new@x.com" in page
    assert "old@x.com" not in page
