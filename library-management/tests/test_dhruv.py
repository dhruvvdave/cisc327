"""Dhruv's tests for existing Library Management features (Table B).

Features covered:
  Books: list/search, add, view, update, delete
  Loans: check out, return, look up loans

Tests marked DEFECT assert the behaviour a reasonable requirement would expect.
They currently FAIL against the reference app and are kept on purpose; each is
explained in the report (expected vs. observed). Rename the file if your
branch/file uses a different name (tests/test_<your-name>.py).
"""
import pytest

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
