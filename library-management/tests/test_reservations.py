"""Tests for reservations (create, list/filter) and their interaction with checkout."""


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
