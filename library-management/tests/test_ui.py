"""Tests for the plain-HTML web UI pages (/, /ui/books, /ui/members, /ui/loans)."""


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
