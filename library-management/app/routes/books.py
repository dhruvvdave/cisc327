from flask import Blueprint, jsonify, request

from app import store
from app.models.book import Book

books_bp = Blueprint("books", __name__, url_prefix="/books")

##list_books
## Inputs:N/A
#Output: A list of books
## Description: Lists every book within th esearch terms
@books_bp.route("", methods=["GET"])
def list_books():
    results = list(store.books.values())
    search = request.args.get("search", "").lower()
    if search:
        results = [b for b in results if search in b.title.lower() or search in b.author.lower()]
    return jsonify([b.to_dict() for b in results])



##create_books
##Inputs: N/A
##Outputs: A book element
##Description: Creates a new book
@books_bp.route("", methods=["POST"])
def create_book():
    data = request.get_json()
    book_id = store.next_id("book")
    book = Book(
        id=book_id,
        title=data["title"],
        author=data["author"],
        isbn=data["isbn"],
        total_copies=data.get("total_copies", 1),
        available_copies=data.get("total_copies", 1),
    )
    store.books[book_id] = book
    return jsonify(book.to_dict()), 201


##get_books
##Inputs: a Book ID
##Outputs: A book Element
##Description: Finds a book based off it's ID, and returns that book
@books_bp.route("/<int:book_id>", methods=["GET"])
def get_book(book_id):
    book = store.books.get(book_id)
    if book is None:
        return jsonify({"error": "Book not found"}), 404
    return jsonify(book.to_dict())


##update_books
##Inputs: A book ID
##Outputs: A Book element
##Description: Finds a book based off it's ID and updates it's information
@books_bp.route("/<int:book_id>", methods=["PUT"])
def update_book(book_id):
    book = store.books.get(book_id)
    if book is None:
        return jsonify({"error": "Book not found"}), 404
    data = request.get_json()
    book.title = data.get("title", book.title)
    book.author = data.get("author", book.author)
    book.isbn = data.get("isbn", book.isbn)
    book.total_copies = data.get("total_copies", book.total_copies)
    book.available_copies = data.get("available_copies", book.available_copies)
    return jsonify(book.to_dict())


##delete_books
##Inputs: A book ID
##Outputs: N/A
##Description: Finds a book by ID and Deletes it.
@books_bp.route("/<int:book_id>", methods=["DELETE"])
def delete_book(book_id):
    book = store.books.pop(book_id, None)
    if book is None:
        return jsonify({"error": "Book not found"}), 404
    return "", 204
