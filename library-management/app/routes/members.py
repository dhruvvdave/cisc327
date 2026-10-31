from flask import Blueprint, jsonify, request

from app import store
from app.models.member import Member

members_bp = Blueprint("members", __name__, url_prefix="/members")

##list_members
##Inputs: N/A
##Output: A list of every Member
##Description: Returns a list of every member in the system
@members_bp.route("", methods=["GET"])
def list_members():
    return jsonify([m.to_dict() for m in store.members.values()])


##create_member
##Inputs: N/A
##Outputs: A new Member Element
## Description: Takes data from the JSON, creates a new member element, and returns the new Member to a JSON dictionary
@members_bp.route("", methods=["POST"])
def create_member():
    data = request.get_json()
    member_id = store.next_id("member")
    member = Member(id=member_id, name=data["name"], email=data["email"])
    store.members[member_id] = member
    return jsonify(member.to_dict()), 201


##get_member
##Inputs: A member ID, int
##Output: A member element
##Descrition: Gets a memebr ID and returns the associated memeber to JSON
##Notes: Seems to cause an infinite recursion when called, and returns to a dictionary
@members_bp.route("/<int:member_id>", methods=["GET"])
def get_member(member_id):
    member = store.members.get(member_id)
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    return jsonify(member.to_dict())


##update_members
##Inputs: A member ID, int
#Output: A member element
##Description: Finds a member based off their ID, and then changes valeus within the Element
##Notes: Seems nonfuntional
@members_bp.route("/<int:member_id>", methods=["PUT"])
def update_member(member_id):
    member = store.members.get(member_id)
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    data = request.get_json()
    member.name = data.get("name", member.name)
    member.email = data.get("email", member.email)
    return jsonify(member.to_dict())


##delete_memebrs
##Inputs: A member ID
##Output: N/A
##Description: Deletes a member with associated ID
@members_bp.route("/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    member = store.members.pop(member_id, None)
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    return "", 204
