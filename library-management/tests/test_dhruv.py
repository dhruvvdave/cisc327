"""Dhruv's tests for all existing Library Management features (see Table B).

Sections:
  1. Books and loans   - add/list/search/view/update/delete books, check out, return, look up loans
  2. Members           - register/list/view/update/delete members
  3. Renewals and fines
  4. Reservations
  5. Web UI pages

Tests whose docstring starts with "DEFECT" assert the behaviour the Assignment 1
requirements call for. They currently FAIL against the reference app on purpose;
each one is explained in the report (expected vs. observed).
"""
from datetime import date, timedelta

import pytest

from app import store



# ======================================================================
# 1. BOOKS AND LOANS
# ======================================================================


BOOK = {"title": "Clean Code", "author": "Robert C. Martin", "isbn": "978-0132350884", "total_copies": 2}


def add_book(client, **overrides):
    payload = {**BOOK, **overrides}
    response = client.post("/books", json=payload)
    assert response.status_code == 201
    return response.get_json()


def add_member(client, name="Sam", email="sam@example.com"):
    response = client.post("/members", json={"name": name, "email": email})
    assert response.status_code == 201
    return response.get_json()


# ---------------------------------------------------------------- books: add
def test_create_book_persists_and_is_retrievable(client):
    created = add_book(client)
    fetched = client.get(f"/books/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json() == created
    assert created["total_copies"] == created["available_copies"] == 2


def test_create_book_defaults_to_one_copy_when_total_copies_omitted(client):
    response = client.post("/books", json={"title": "T", "author": "A", "isbn": "1"})
    assert response.status_code == 201
    data = response.get_json()
    assert data["total_copies"] == 1
    assert data["available_copies"] == 1


def test_book_ids_increment_and_list_returns_all(client):
    first = add_book(client, isbn="1")
    second = add_book(client, isbn="2")
    assert second["id"] == first["id"] + 1
    assert len(client.get("/books").get_json()) == 2


def test_create_book_missing_required_field_returns_400(client):
    """DEFECT: missing 'isbn' raises KeyError -> HTTP 500 instead of a 400."""
    response = client.post("/books", json={"title": "No author or isbn"})
    assert response.status_code == 400


def test_create_book_negative_copies_rejected(client):
    """DEFECT: total_copies=-5 is accepted (201) and available_copies becomes -5."""
    response = client.post("/books", json={**BOOK, "total_copies": -5})
    assert response.status_code == 400


def test_create_book_duplicate_isbn_rejected(client):
    """DEFECT: two books can share an ISBN (no uniqueness check)."""
    add_book(client)
    response = client.post("/books", json=BOOK)
    assert response.status_code in (400, 409)


# ------------------------------------------------------- books: list/search
def test_search_matches_title_and_author_case_insensitively(client):
    add_book(client, title="Dune", author="Frank Herbert", isbn="1")
    add_book(client, title="Emma", author="Jane Austen", isbn="2")
    by_title = client.get("/books?search=DUNE").get_json()
    by_author = client.get("/books?search=austen").get_json()
    assert [b["title"] for b in by_title] == ["Dune"]
    assert [b["title"] for b in by_author] == ["Emma"]


def test_search_with_no_match_returns_empty_list(client):
    add_book(client)
    response = client.get("/books?search=zzz-nothing")
    assert response.status_code == 200
    assert response.get_json() == []


# ------------------------------------------------------------- books: view
def test_get_nonexistent_book_returns_404_with_error_message(client):
    response = client.get("/books/999")
    assert response.status_code == 404
    assert "error" in response.get_json()


# ----------------------------------------------------------- books: update
def test_update_book_changes_only_supplied_fields(client):
    book = add_book(client)
    response = client.put(f"/books/{book['id']}", json={"title": "Clean Code, 2nd Ed."})
    assert response.status_code == 200
    updated = client.get(f"/books/{book['id']}").get_json()
    assert updated["title"] == "Clean Code, 2nd Ed."
    assert updated["author"] == book["author"]
    assert updated["isbn"] == book["isbn"]
    assert updated["total_copies"] == book["total_copies"]


def test_update_nonexistent_book_returns_404(client):
    assert client.put("/books/999", json={"title": "x"}).status_code == 404


def test_update_total_copies_keeps_available_copies_consistent(client):
    """DEFECT: raising total_copies 2 -> 5 leaves available_copies at 2."""
    book = add_book(client)
    client.put(f"/books/{book['id']}", json={"total_copies": 5})
    updated = client.get(f"/books/{book['id']}").get_json()
    assert updated["available_copies"] == 5


def test_update_available_copies_cannot_exceed_total_or_go_negative(client):
    """DEFECT: available_copies can be set to -3 or above total_copies."""
    book = add_book(client)
    r = client.put(f"/books/{book['id']}", json={"available_copies": -3})
    assert r.status_code == 400


# ----------------------------------------------------------- books: delete
def test_delete_book_removes_it(client):
    book = add_book(client)
    assert client.delete(f"/books/{book['id']}").status_code == 204
    assert client.get(f"/books/{book['id']}").status_code == 404
    assert client.get("/books").get_json() == []


def test_delete_book_twice_returns_404_second_time(client):
    book = add_book(client)
    client.delete(f"/books/{book['id']}")
    assert client.delete(f"/books/{book['id']}").status_code == 404


def test_delete_book_with_active_loan_is_blocked(client):
    """DEFECT: a book with an unreturned loan can be deleted, orphaning the loan."""
    book = add_book(client)
    member = add_member(client)
    client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]})
    assert client.delete(f"/books/{book['id']}").status_code in (400, 409)


# --------------------------------------------------------- loans: check out
def test_checkout_creates_loan_and_decrements_available_copies(client):
    book = add_book(client)
    member = add_member(client)
    response = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]})
    assert response.status_code == 201
    loan = response.get_json()
    assert loan["book_id"] == book["id"]
    assert loan["member_id"] == member["id"]
    assert loan["return_date"] is None
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 1


def test_checkout_due_date_is_14_days_after_loan_date(client):
    from datetime import date, timedelta

    book = add_book(client)
    member = add_member(client)
    loan = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]}).get_json()
    assert loan["loan_date"] == date.today().isoformat()
    assert loan["due_date"] == (date.today() + timedelta(days=14)).isoformat()


def test_checkout_nonexistent_book_returns_404(client):
    member = add_member(client)
    assert client.post("/loans", json={"book_id": 999, "member_id": member["id"]}).status_code == 404


def test_checkout_nonexistent_member_returns_404(client):
    """DEFECT: member_id is never validated, so a loan is created for member 999."""
    book = add_book(client)
    response = client.post("/loans", json={"book_id": book["id"], "member_id": 999})
    assert response.status_code == 404


def test_checkout_fails_when_no_copies_available(client):
    """DEFECT: checkout is allowed with 0 copies; available_copies goes to -1."""
    book = add_book(client, total_copies=1)
    first, second = add_member(client, "A", "a@x.com"), add_member(client, "B", "b@x.com")
    assert client.post("/loans", json={"book_id": book["id"], "member_id": first["id"]}).status_code == 201
    response = client.post("/loans", json={"book_id": book["id"], "member_id": second["id"]})
    assert response.status_code in (400, 409)
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 0


# ------------------------------------------------------------ loans: return
def test_return_sets_return_date_and_restores_available_copies(client):
    from datetime import date

    book = add_book(client)
    member = add_member(client)
    loan = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]}).get_json()
    response = client.put(f"/loans/{loan['id']}/return")
    assert response.status_code == 200
    assert response.get_json()["return_date"] == date.today().isoformat()
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 2


def test_return_same_loan_twice_is_rejected_and_does_not_double_count(client):
    book = add_book(client)
    member = add_member(client)
    loan = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]}).get_json()
    client.put(f"/loans/{loan['id']}/return")
    second = client.put(f"/loans/{loan['id']}/return")
    assert second.status_code == 400
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 2


def test_return_nonexistent_loan_returns_404(client):
    assert client.put("/loans/999/return").status_code == 404


def test_return_after_book_deleted_does_not_crash(client):
    """DEFECT: returning a loan whose book was deleted raises AttributeError (HTTP 500)."""
    book = add_book(client)
    member = add_member(client)
    loan = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]}).get_json()
    client.delete(f"/books/{book['id']}")
    response = client.put(f"/loans/{loan['id']}/return")
    assert response.status_code < 500


# ------------------------------------------------------------ loans: lookup
def test_loans_filter_by_book_id(client):
    b1, b2 = add_book(client, isbn="1"), add_book(client, isbn="2")
    member = add_member(client)
    client.post("/loans", json={"book_id": b1["id"], "member_id": member["id"]})
    client.post("/loans", json={"book_id": b2["id"], "member_id": member["id"]})
    result = client.get(f"/loans?book_id={b1['id']}").get_json()
    assert [l["book_id"] for l in result] == [b1["id"]]


def test_loans_filter_by_member_id_returns_that_members_loans(client):
    """DEFECT: the member_id filter compares against book_id (loans.py line ~19)."""
    book = add_book(client, total_copies=3)
    m1, m2 = add_member(client, "A", "a@x.com"), add_member(client, "B", "b@x.com")
    client.post("/loans", json={"book_id": book["id"], "member_id": m1["id"]})
    client.post("/loans", json={"book_id": book["id"], "member_id": m2["id"]})
    result = client.get(f"/loans?member_id={m2['id']}").get_json()
    assert [l["member_id"] for l in result] == [m2["id"]]


def test_loans_without_filters_lists_all_including_returned(client):
    book = add_book(client)
    member = add_member(client)
    loan = client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]}).get_json()
    client.put(f"/loans/{loan['id']}/return")
    result = client.get("/loans").get_json()
    assert len(result) == 1 and result[0]["return_date"] is not None


# ======================================================================
# 2. MEMBERS
# ======================================================================


MEMBER = {"name": "Ada Lovelace", "email": "ada@example.com"}


def create_member(client, **overrides):
    response = client.post("/members", json={**MEMBER, **overrides})
    assert response.status_code == 201
    return response.get_json()


def test_create_member_returns_fields_and_membership_date(client):
    from datetime import date

    member = create_member(client)
    assert member["id"] == 1
    assert member["name"] == "Ada Lovelace"
    assert member["email"] == "ada@example.com"
    assert member["membership_date"] == date.today().isoformat()


def test_list_members_empty_then_populated(client):
    assert client.get("/members").get_json() == []
    create_member(client)
    create_member(client, name="Grace Hopper", email="grace@example.com")
    assert [m["name"] for m in client.get("/members").get_json()] == ["Ada Lovelace", "Grace Hopper"]


def test_get_member_by_id_and_unknown_id_returns_404(client):
    member = create_member(client)
    assert client.get(f"/members/{member['id']}").get_json() == member
    response = client.get("/members/999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_update_member_changes_only_supplied_fields(client):
    member = create_member(client)
    response = client.put(f"/members/{member['id']}", json={"email": "new@example.com"})
    assert response.status_code == 200
    updated = client.get(f"/members/{member['id']}").get_json()
    assert updated["email"] == "new@example.com"
    assert updated["name"] == "Ada Lovelace"
    assert updated["membership_date"] == member["membership_date"]


def test_update_unknown_member_returns_404(client):
    assert client.put("/members/999", json={"name": "x"}).status_code == 404


def test_delete_member_removes_it_and_second_delete_is_404(client):
    member = create_member(client)
    assert client.delete(f"/members/{member['id']}").status_code == 204
    assert client.get(f"/members/{member['id']}").status_code == 404
    assert client.delete(f"/members/{member['id']}").status_code == 404


def test_create_member_missing_email_returns_400(client):
    """DEFECT: a missing required field raises KeyError -> HTTP 500."""
    assert client.post("/members", json={"name": "No Email"}).status_code == 400


def test_create_member_rejects_invalid_email(client):
    """DEFECT: any string is accepted as an email address."""
    assert client.post("/members", json={"name": "Bad", "email": "not-an-email"}).status_code == 400


def test_create_member_rejects_duplicate_email(client):
    """DEFECT: two members can register with the same email."""
    create_member(client)
    assert client.post("/members", json=MEMBER).status_code in (400, 409)


def test_delete_member_with_active_loan_is_blocked(client):
    """DEFECT: a member who still has a book can be deleted, orphaning the loan."""
    book = client.post("/books", json={"title": "T", "author": "A", "isbn": "1"}).get_json()
    member = create_member(client)
    client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]})
    assert client.delete(f"/members/{member['id']}").status_code in (400, 409)


# ======================================================================
# 3. RENEWALS AND FINES
# ======================================================================


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


# ======================================================================
# 4. RESERVATIONS
# ======================================================================


def setup_book_and_members(client, copies=1):
    book = client.post("/books", json={"title": "T", "author": "A", "isbn": "1", "total_copies": copies}).get_json()
    m1 = client.post("/members", json={"name": "A", "email": "a@example.com"}).get_json()
    m2 = client.post("/members", json={"name": "B", "email": "b@example.com"}).get_json()
    return book, m1, m2


def test_create_reservation_returns_unfulfilled_reservation(client):
    from datetime import date

    book, m1, _ = setup_book_and_members(client)
    response = client.post("/reservations", json={"book_id": book["id"], "member_id": m1["id"]})
    assert response.status_code == 201
    data = response.get_json()
    assert data["book_id"] == book["id"]
    assert data["member_id"] == m1["id"]
    assert data["fulfilled"] is False
    assert data["reservation_date"] == date.today().isoformat()


def test_create_reservation_unknown_book_returns_404(client):
    _, m1, _ = setup_book_and_members(client)
    assert client.post("/reservations", json={"book_id": 999, "member_id": m1["id"]}).status_code == 404


def test_create_reservation_unknown_member_returns_404(client):
    book, _, _ = setup_book_and_members(client)
    assert client.post("/reservations", json={"book_id": book["id"], "member_id": 999}).status_code == 404


def test_list_reservations_filters_by_book_and_member(client):
    book, m1, m2 = setup_book_and_members(client)
    client.post("/reservations", json={"book_id": book["id"], "member_id": m1["id"]})
    client.post("/reservations", json={"book_id": book["id"], "member_id": m2["id"]})
    assert len(client.get("/reservations").get_json()) == 2
    assert len(client.get(f"/reservations?book_id={book['id']}").get_json()) == 2
    only_m2 = client.get(f"/reservations?member_id={m2['id']}").get_json()
    assert [r["member_id"] for r in only_m2] == [m2["id"]]


def test_list_reservations_empty_initially(client):
    assert client.get("/reservations").get_json() == []


def test_checkout_blocked_for_other_member_when_book_is_reserved(client):
    """DEFECT: checkout ignores reservations, so member B can take the book reserved by A."""
    book, m1, m2 = setup_book_and_members(client)
    client.post("/reservations", json={"book_id": book["id"], "member_id": m1["id"]})
    response = client.post("/loans", json={"book_id": book["id"], "member_id": m2["id"]})
    assert response.status_code in (400, 403, 409)


def test_reserving_a_book_twice_by_same_member_is_rejected(client):
    """DEFECT: the same member can create unlimited duplicate reservations."""
    book, m1, _ = setup_book_and_members(client)
    client.post("/reservations", json={"book_id": book["id"], "member_id": m1["id"]})
    response = client.post("/reservations", json={"book_id": book["id"], "member_id": m1["id"]})
    assert response.status_code in (400, 409)


# ======================================================================
# 5. WEB UI
# ======================================================================


def test_home_and_list_pages_load(client):
    for path in ("/", "/ui/books", "/ui/members", "/ui/loans"):
        assert client.get(path).status_code == 200


def test_add_book_through_form_then_shows_in_api_and_page(client):
    response = client.post(
        "/ui/books",
        data={"title": "Dune", "author": "Frank Herbert", "isbn": "1", "total_copies": "3"},
    )
    assert response.status_code == 302
    assert "Dune" in client.get("/ui/books").get_data(as_text=True)
    assert client.get("/books/1").get_json()["available_copies"] == 3


def test_delete_book_through_ui(client):
    client.post("/ui/books", data={"title": "Dune", "author": "F", "isbn": "1", "total_copies": "1"})
    client.post("/ui/books/1/delete")
    assert client.get("/books").get_json() == []


def test_add_and_delete_member_through_ui(client):
    client.post("/ui/members", data={"name": "Ada", "email": "ada@example.com"})
    assert "Ada" in client.get("/ui/members").get_data(as_text=True)
    client.post("/ui/members/1/delete")
    assert client.get("/members").get_json() == []


def test_checkout_and_return_through_ui_updates_stock(client):
    client.post("/ui/books", data={"title": "Dune", "author": "F", "isbn": "1", "total_copies": "1"})
    client.post("/ui/members", data={"name": "Ada", "email": "ada@example.com"})
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})
    assert client.get("/books/1").get_json()["available_copies"] == 0
    client.post("/ui/loans/1/return")
    assert client.get("/books/1").get_json()["available_copies"] == 1
    assert client.get("/loans/1/fine").status_code == 200


def test_ui_checkout_refused_when_no_copies_left(client):
    """DEFECT: the UI checkout form has no stock check; available_copies goes to -1."""
    client.post("/ui/books", data={"title": "Dune", "author": "F", "isbn": "1", "total_copies": "1"})
    client.post("/ui/members", data={"name": "Ada", "email": "ada@example.com"})
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})
    assert client.get("/books/1").get_json()["available_copies"] >= 0


# ======================================================================
# 6. ENHANCEMENT: CHECK-OUT VALIDATION (feature/checkout-validation, R17)
# ======================================================================
# A check-out is refused (and changes nothing) when the book or member does not
# exist, when no copies are left, or when the remaining copies are reserved for
# other members. A member with their own reservation may check the book out,
# which marks that reservation as fulfilled.


def _checkout(client, book_id, member_id):
    return client.post("/loans", json={"book_id": book_id, "member_id": member_id})


def test_checkout_refused_with_409_and_state_unchanged_when_no_copies_left(client):
    book = add_book(client, total_copies=1)
    first, second = add_member(client, "A", "a@x.com"), add_member(client, "B", "b@x.com")
    assert _checkout(client, book["id"], first["id"]).status_code == 201

    response = _checkout(client, book["id"], second["id"])

    assert response.status_code == 409
    assert "error" in response.get_json()
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 0
    assert len(client.get("/loans").get_json()) == 1  # no second loan was created


def test_checkout_unknown_member_returns_404_and_keeps_stock(client):
    book = add_book(client, total_copies=2)
    response = _checkout(client, book["id"], 999)
    assert response.status_code == 404
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 2
    assert client.get("/loans").get_json() == []


def test_checkout_missing_or_non_integer_ids_return_400(client):
    assert client.post("/loans", json={"book_id": 1}).status_code == 400
    assert client.post("/loans", json={"book_id": "one", "member_id": 1}).status_code == 400
    assert client.post("/loans", data="not json").status_code == 400


def test_checkout_blocked_for_non_reserving_member_when_last_copy_is_reserved(client):
    book = add_book(client, total_copies=1)
    reserver, other = add_member(client, "R", "r@x.com"), add_member(client, "O", "o@x.com")
    client.post("/reservations", json={"book_id": book["id"], "member_id": reserver["id"]})

    response = _checkout(client, book["id"], other["id"])

    assert response.status_code == 409
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 1


def test_reserving_member_can_check_out_and_reservation_is_fulfilled(client):
    book = add_book(client, total_copies=1)
    reserver = add_member(client, "R", "r@x.com")
    client.post("/reservations", json={"book_id": book["id"], "member_id": reserver["id"]})

    response = _checkout(client, book["id"], reserver["id"])

    assert response.status_code == 201
    reservation = client.get(f"/reservations?member_id={reserver['id']}").get_json()[0]
    assert reservation["fulfilled"] is True
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 0


def test_spare_copy_beyond_reservations_can_still_be_borrowed(client):
    """2 copies, 1 reservation by someone else: one copy stays free for others."""
    book = add_book(client, total_copies=2)
    reserver, other, third = (add_member(client, n, f"{n}@x.com") for n in ("R", "O", "T"))
    client.post("/reservations", json={"book_id": book["id"], "member_id": reserver["id"]})

    assert _checkout(client, book["id"], other["id"]).status_code == 201   # takes the spare copy
    assert _checkout(client, book["id"], third["id"]).status_code == 409   # last copy is reserved
    assert client.get(f"/books/{book['id']}").get_json()["available_copies"] == 1


def test_checkout_works_again_after_the_book_is_returned(client):
    book = add_book(client, total_copies=1)
    first, second = add_member(client, "A", "a@x.com"), add_member(client, "B", "b@x.com")
    loan = _checkout(client, book["id"], first["id"]).get_json()
    assert _checkout(client, book["id"], second["id"]).status_code == 409

    client.put(f"/loans/{loan['id']}/return")

    assert _checkout(client, book["id"], second["id"]).status_code == 201


def test_web_ui_checkout_follows_the_same_rules(client):
    client.post("/ui/books", data={"title": "Dune", "author": "F", "isbn": "1", "total_copies": "1"})
    client.post("/ui/members", data={"name": "Ada", "email": "ada@example.com"})
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})  # no copies left
    client.post("/ui/loans", data={"book_id": "1", "member_id": "99"})  # unknown member
    assert len(client.get("/loans").get_json()) == 1
    assert client.get("/books/1").get_json()["available_copies"] == 0
