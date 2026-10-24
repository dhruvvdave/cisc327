"""Tests for loan renewal and fine calculation."""
from datetime import date, timedelta

from app import store


def make_loan(client, copies=2):
    book = client.post("/books", json={"title": "T", "author": "A", "isbn": "1", "total_copies": copies}).get_json()
    member = client.post("/members", json={"name": "M", "email": "m@example.com"}).get_json()
    loan = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]}).get_json()
    return book, member, loan


# ------------------------------------------------------------------ renew
def test_renew_extends_due_date_by_loan_period(client):
    _, _, loan = make_loan(client)
    response = client.put(f"/loans/{loan['id']}/renew")
    assert response.status_code == 200
    expected = date.fromisoformat(loan["due_date"]) + timedelta(days=14)
    assert response.get_json()["due_date"] == expected.isoformat()


def test_renew_does_not_change_available_copies(client):
    book, _, loan = make_loan(client)
    client.put(f"/loans/{loan['id']}/renew")
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 1


def test_renew_returned_loan_is_rejected(client):
    _, _, loan = make_loan(client)
    client.put(f"/loans/{loan['id']}/return")
    response = client.put(f"/loans/{loan['id']}/renew")
    assert response.status_code == 400


def test_renew_unknown_loan_returns_404(client):
    assert client.put("/loans/999/renew").status_code == 404


def test_renew_is_limited_to_a_maximum_number_of_times(client):
    """DEFECT: no renewal limit; a loan can be renewed forever."""
    _, _, loan = make_loan(client)
    statuses = [client.put(f"/loans/{loan['id']}/renew").status_code for _ in range(10)]
    assert 400 in statuses or 409 in statuses


# ------------------------------------------------------------------- fine
def test_fine_is_zero_when_not_overdue(client):
    _, _, loan = make_loan(client)
    response = client.get(f"/loans/{loan['id']}/fine")
    assert response.status_code == 200
    assert response.get_json() == {"loan_id": loan["id"], "fine_amount": 0.0}


def test_fine_is_25_cents_per_day_overdue(client):
    _, _, loan = make_loan(client)
    store.loans[loan["id"]].due_date = date.today() - timedelta(days=10)
    assert client.get(f"/loans/{loan['id']}/fine").get_json()["fine_amount"] == 2.5


def test_fine_is_zero_on_the_due_date(client):
    _, _, loan = make_loan(client)
    store.loans[loan["id"]].due_date = date.today()
    assert client.get(f"/loans/{loan['id']}/fine").get_json()["fine_amount"] == 0.0


def test_fine_unknown_loan_returns_404(client):
    assert client.get("/loans/999/fine").status_code == 404


def test_fine_stops_growing_after_book_is_returned(client):
    """DEFECT: fine uses today's date even for returned loans.

    Due 10 days ago, returned 8 days ago -> 2 days late -> $0.50, fixed.
    The app reports $2.50 (10 days) and would keep growing.
    """
    _, _, loan = make_loan(client)
    stored = store.loans[loan["id"]]
    stored.due_date = date.today() - timedelta(days=10)
    stored.return_date = date.today() - timedelta(days=8)
    assert client.get(f"/loans/{loan['id']}/fine").get_json()["fine_amount"] == 0.5
