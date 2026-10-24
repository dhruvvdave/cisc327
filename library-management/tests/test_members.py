"""Tests for member management features (create, list, view, update, delete)."""

MEMBER = {"name": "Ada Lovelace", "email": "ada@example.com"}


def add_member(client, **overrides):
    response = client.post("/members", json={**MEMBER, **overrides})
    assert response.status_code == 201
    return response.get_json()


def test_create_member_returns_fields_and_membership_date(client):
    from datetime import date

    member = add_member(client)
    assert member["id"] == 1
    assert member["name"] == "Ada Lovelace"
    assert member["email"] == "ada@example.com"
    assert member["membership_date"] == date.today().isoformat()


def test_list_members_empty_then_populated(client):
    assert client.get("/members").get_json() == []
    add_member(client)
    add_member(client, name="Grace Hopper", email="grace@example.com")
    assert [m["name"] for m in client.get("/members").get_json()] == ["Ada Lovelace", "Grace Hopper"]


def test_get_member_by_id_and_unknown_id_returns_404(client):
    member = add_member(client)
    assert client.get(f"/members/{member['id']}").get_json() == member
    response = client.get("/members/999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_update_member_changes_only_supplied_fields(client):
    member = add_member(client)
    response = client.put(f"/members/{member['id']}", json={"email": "new@example.com"})
    assert response.status_code == 200
    updated = client.get(f"/members/{member['id']}").get_json()
    assert updated["email"] == "new@example.com"
    assert updated["name"] == "Ada Lovelace"
    assert updated["membership_date"] == member["membership_date"]


def test_update_unknown_member_returns_404(client):
    assert client.put("/members/999", json={"name": "x"}).status_code == 404


def test_delete_member_removes_it_and_second_delete_is_404(client):
    member = add_member(client)
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
    add_member(client)
    assert client.post("/members", json=MEMBER).status_code in (400, 409)


def test_delete_member_with_active_loan_is_blocked(client):
    """DEFECT: a member who still has a book can be deleted, orphaning the loan."""
    book = client.post("/books", json={"title": "T", "author": "A", "isbn": "1"}).get_json()
    member = add_member(client)
    client.post("/loans", json={"book_id": book["id"], "member_id": member["id"]})
    assert client.delete(f"/members/{member['id']}").status_code in (400, 409)
