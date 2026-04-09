"""
api_handler.py — HomefyAPIHandler

Wraps Homefy's GraphQL API + 3 REST endpoints.
Chains relevant queries based on intent and returns a concise
context string that is injected into the AI system prompt.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPHQL_URL   = os.getenv("HOMEFY_GRAPHQL_URL", "http://localhost:4000/graphql")
REST_BASE_URL = os.getenv("HOMEFY_REST_BASE_URL", "http://localhost:4000")
DEFAULT_TOKEN = os.getenv("HOMEFY_AUTH_TOKEN", "")

TIMEOUT = 8  # seconds per request


class HomefyAPIHandler:
    """Executes Homefy GraphQL queries and REST calls and summarises results."""

    def __init__(self):
        self._query_cache = {}

    def _load_gql(self, filepath: str) -> str:
        """Helper to read .graphql files from disk."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(base_dir, filepath)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    # ── Low-level helpers ─────────────────────────────────────────────────────
    def _headers(self, token: str) -> dict:
        t = token or DEFAULT_TOKEN
        h = {"Content-Type": "application/json"}
        if t:
            h["Authorization"] = f"Bearer {t}" if not t.startswith("Bearer") else t
        return h

    def execute_graphql(self, query: str, variables: dict, token: str = "") -> dict:
        """Send a GraphQL request and return parsed JSON data."""
        payload = {"query": query, "variables": variables or {}}
        try:
            resp = requests.post(
                GRAPHQL_URL,
                json=payload,
                headers=self._headers(token),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                print(f"[GRAPHQL ERRORS]: {result['errors']}")
                with open("last_graphql_error.txt", "w") as f:
                    f.write(json.dumps(result['errors'], indent=2))
                return {"error": result["errors"]}
            return result.get("data", {})
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_msg += f" - {e.response.json()}"
                except Exception:
                    error_msg = f"{e} - {e.response.text}"
            print(f"[GRAPHQL HTTP ERROR]: {error_msg}")
            with open("last_graphql_error.txt", "w") as f:
                f.write(error_msg)
            return {"error": error_msg}
        except Exception as e:
            print(f"[GRAPHQL EXCEPTION]: {e}")
            return {"error": str(e)}

    def execute_rest(self, method: str, path: str, token: str = "", **kwargs) -> dict:
        """Send a REST request and return parsed JSON."""
        url = REST_BASE_URL.rstrip("/") + path
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(token),
                timeout=TIMEOUT,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def _fmt(self, data: dict, label: str) -> str:
        """Format a data dict as readable text for the AI prompt context."""
        if "error" in data:
            err_str = str(data['error']).lower()
            if "403" in err_str or "forbidden" in err_str or "unauthorized" in err_str:
                return f"[{label}]: No data registered for this account or access is restricted.\n"
            return f"[{label}]: unavailable ({data['error']})\n"
        return f"[{label}]:\n{json.dumps(data, indent=2, default=str)}\n"

    # ── Authentication / User Profile ───────────────────────────────────────────

    def get_access_token(self, request_id: str, token: str = "") -> dict:
        q = self._load_gql("graphql/auth/mutations/access_token.graphql")
        variables = {"data": {"requestId": request_id}}
        return self.execute_graphql(q, variables, token)

    def get_profile(self, token: str) -> dict:
        q = self._load_gql("graphql/auth/queries/get_profile.graphql")
        return self.execute_graphql(q, {}, token)

    def get_my_apartments(self, token: str) -> dict:
        q = self._load_gql("graphql/auth/queries/get_my_apartments.graphql")
        return self.execute_graphql(q, {}, token)

    def _q_my_profile(self, token: str) -> str:
        data = self.get_profile(token)
        me = data.get("me", {})
        if not me:
            return self._fmt(data, "My Profile")
        formatted = {
            "id": me.get("id"),
            "name": f"{me.get('firstName', '')} {me.get('lastName', '')}".strip() or "Not set",
            "firstName": me.get("firstName"),
            "lastName": me.get("lastName"),
            "phoneNumber": me.get("phoneNumber"),
            "email": me.get("email"),
        }
        return self._fmt(formatted, "My Profile")

    # ── GraphQL queries ───────────────────────────────────────────────────────

    def _q_my_bookings(self, token):
        q = self._load_gql("graphql/amenities/queries/all_bookings.graphql")
        try:
            res = self.execute_graphql(q, {"filter": {}}, token)
            # Inject receipt URLs so the LLM can surface them to the user
            bookings_data = res.get("allBookings", {})
            if isinstance(bookings_data, dict) and bookings_data.get("data"):
                for booking in bookings_data["data"]:
                    b_id = booking.get("id")
                    if b_id:
                        booking["receiptUrl"] = f"https://api-staging.homefy.co.in/receipts/bills/{b_id}?type=amenity"
            return self._fmt(res, "My Amenity Bookings & Receipts")
        except Exception as e:
            return f"[My Amenity Bookings]: unavailable ({e})"
    def get_amenity_slots(self, token: str, amenity_id: str, start_date: str, end_date: str) -> dict:
        try:
            q = self._load_gql("graphql/amenities/queries/get_amenity_slots.graphql")
            variables = {
                "amenityId": amenity_id,
                "startDate": start_date,
                "endDate": end_date
            }
            data = self.execute_graphql(q, variables, token)
            if "error" in data:
                return {"status": "error", "message": f"Failed to get slots: {data['error']}"}
            amenity = data.get("amenity", {})
            return {"status": "success", "amenity": amenity, "slots": amenity.get("slots", [])}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _q_all_amenities(self, token, apartment_id: str = ""):
        q = self._load_gql("graphql/amenities/queries/all_amenities.graphql")
        variables = {"filter": {}}
        data = self.execute_graphql(q, variables, token)
        
        # Format the data cleanly so the LLM does not get overwhelmed by giant JSON blocks or pagination info
        if "allAmenities" in data and isinstance(data["allAmenities"], dict):
            items = data["allAmenities"].get("data", [])
            lines = []
            for a in items:
                lines.append(f"  - Amenity ID: {a.get('id')} | Name: {a.get('name')} | Location: {a.get('location', 'N/A')}")
            
            if lines:
                return "[Available Amenities (List)]:\n" + "\n".join(lines) + "\n"
            else:
                return "[Available Amenities]: No amenities found currently.\n"
                
        return self._fmt(data, "Available Amenities")

    def get_all_amenities_raw(self, token: str, apartment_id: str = "") -> list:
        try:
            q = self._load_gql("graphql/amenities/queries/all_amenities.graphql")
            variables = {"filter": {}}
            data = self.execute_graphql(q, variables, token)
            if "error" in data:
                return []
            amenities_obj = data.get("allAmenities")
            if not isinstance(amenities_obj, dict):
                return []
            return amenities_obj.get("data", [])
        except Exception as e:
            print(f"[AMENITY RAW FILTER] Exception: {e}")
            return []

    def get_amenity_categories_raw(self, token: str) -> list:
        """Fetch amenity categories (Kids & Family, Sports & Fitness, etc.)"""
        try:
            q = self._load_gql("graphql/amenities/queries/get_amenity_categories.graphql")
            data = self.execute_graphql(q, {"filter": {}}, token)
            if "error" in data:
                return []
            cats = data.get("allCategories")
            if isinstance(cats, dict):
                return cats.get("data", [])
            return []
        except Exception:
            return []

    # Hardcoded fallback categories (in case the staging API is unstable)
    FALLBACK_CATEGORIES = [
        {"id": "cmfe0ilhs0006fjomxlgn8ggb", "name": "Electricity"},
        {"id": "cmfe0ilhs0007fjomsvb2hxh7", "name": "Cleaning"},
        {"id": "cmfe0ilht0008fjomj8czwzl1", "name": "Plumbing"},
        {"id": "cmfe0ilht0009fjomz4os9pv4", "name": "Parking"},
        {"id": "cmfe0ilht000afjom61tyfns6", "name": "Lifts"},
        {"id": "cmfe0ilht000bfjom50xmmbcf", "name": "House Keeping"},
        {"id": "cmfe0ilht000cfjomb1r4hlin", "name": "Security"},
        {"id": "cmfe0ilhu000dfjomlo19q1pc", "name": "Water"},
        {"id": "cmfe0ilhu000efjomr0p7v3tw", "name": "ClubHouse and Facilities"},
        {"id": "cmfe0ilhu000ffjomiaavpya8", "name": "Carpenter"},
        {"id": "cmfe0ilhu000gfjomsr7u2e39", "name": "Payment"},
        {"id": "cmfe0ilhu000hfjomfis5l6nf", "name": "Car Parking"},
        {"id": "cmfe0ilhv000ifjoma71ige3p", "name": "Common Area"},
        {"id": "cmfe0ilhv000jfjomds7u91xx", "name": "Other"},
    ]

    def _q_get_categories(self, token):
        """Fetch complaint categories from API, fallback to hardcoded list."""
        try:
            q = self._load_gql("graphql/complaints/queries/get_categories.graphql")
            cat_dict = {}
            for t in ["COMMUNITY", "PERSONAL"]:
                data = self.execute_graphql(q, {"filter": {"type": t}}, token)
                if "error" in data:
                    continue
                cats = data.get("allCategories", {})
                cat_list = cats.get("data", []) if isinstance(cats, dict) else (cats or [])
                for c in cat_list:
                    if "id" in c:
                        cat_dict[c["id"]] = c
            if cat_dict:
                return list(cat_dict.values())
        except Exception:
            pass
        # Fallback to hardcoded categories
        return self.FALLBACK_CATEGORIES


    def _q_all_complaints(self, token, type_filter="COMMUNITY"):
        try:
            q = self._load_gql("graphql/complaints/queries/all_complaints.graphql")
            variables = {
                "filter": {
                    "type": type_filter
                }
            }
            data = self.execute_graphql(q, variables, token)

            if "error" in data:
                return [{"API Error": data["error"]}]

            all_comp_data = data.get("allComplaints") or data.get("myComplaints")
            if isinstance(all_comp_data, dict):
                return all_comp_data.get("data", [])
            elif isinstance(all_comp_data, list):
                return all_comp_data
            
            return []
        except Exception:
            return []

    def _q_get_detailed_complaint(self, token, complaint_id):
        try:
            q = self._load_gql("graphql/complaints/queries/get_detailed_complaint.graphql")
            data = self.execute_graphql(q, {"complaintId": complaint_id}, token)
            if "error" in data:
                return {"error": data["error"]}
            return data.get("complaint", {})
        except Exception as e:
            return {"error": str(e)}

    def create_complaint(self, token: str, title: str, description: str, category_id: str, type_filter: str = "PERSONAL", location: str = "", is_urgent: bool = False) -> dict:
        try:
            q = self._load_gql("graphql/complaints/mutations/add_complaint.graphql")
            variables = {
                "data": {
                    "title": title,
                    "description": description,
                    "categoryId": category_id,
                    "type": type_filter,
                    "location": location,
                    "isUrgent": is_urgent
                }
            }
            data = self.execute_graphql(q, variables, token)
            if "error" in data:
                return {"status": "error", "message": f"Failed to raise complaint: {data['error']}"}
            c_data = data.get("createComplaint", {})
            return {"status": "success", "message": f"Complaint '{title}' raised successfully! ID: {c_data.get('complaintId')}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def create_amenity_booking(self, token: str, amenity_id: str, slot_ids: list, flat_id: str = "") -> dict:
        try:
            q = self._load_gql("graphql/amenities/mutations/create_amenity_booking.graphql")
            variables = {
                "data": {
                    "amenityId": amenity_id,
                    "slotIds": slot_ids
                }
            }
            if flat_id:
                variables["data"]["flatId"] = flat_id
                
            data = self.execute_graphql(q, variables, token)
            if "error" in data:
                return {"status": "error", "message": f"Failed to book amenity: {data['error']}"}
            b_data = data.get("createAmenityBooking", {})
            return {"status": "success", "message": f"Amenity booked successfully!", "data": b_data}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _q_my_bills(self, token):
        q = self._load_gql("graphql/community/queries/my_bills.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "My Bills")

    def _q_all_entries_by_date(self, token):
        q = self._load_gql("graphql/community/queries/all_entries_by_date.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Visitor Entries Today")

    def _q_all_announcements(self, token, unread_only=False):
        q = self._load_gql("graphql/announcements/queries/all_announcements.graphql")
        filter_vars = {}
        if unread_only:
            filter_vars["getUnread"] = True
        return self._fmt(self.execute_graphql(q, {"filter": filter_vars}, token), "Unread Announcements" if unread_only else "Announcements")

    def _q_get_detailed_announcement(self, token, announcement_id):
        try:
            q = self._load_gql("graphql/announcements/queries/get_detailed_announcement.graphql")
            data = self.execute_graphql(q, {"announcementId": announcement_id}, token)
            if "error" in data:
                return {"error": data["error"]}
            return data.get("announcement", {})
        except Exception as e:
            return {"error": str(e)}

    def _q_vehicles(self, token, role):
        if role in ["OWNER", "TENANT", "OWNER_FAMILY", "RESIDENT"]:
            q = self._load_gql("graphql/community/queries/my_vehicles.graphql")
            return self._fmt(self.execute_graphql(q, {}, token), "My Vehicles")
        else:
            q = self._load_gql("graphql/community/queries/all_vehicles.graphql")
            return self._fmt(self.execute_graphql(q, {}, token), "All Community Vehicles")

    def _q_parking_categories(self, token):
        try:
            q = self._load_gql("graphql/parking/queries/all_parking_categories.graphql")
            data = self.execute_graphql(q, {"filter": {}}, token)
            if "error" in data:
                return "[Parking Categories]: unavailable"
            return self._fmt(data, "Parking Categories")
        except Exception as e:
            return f"[Parking Categories]: unavailable ({e})"

    def _q_helpers(self, token, role):
        if role in ["OWNER", "TENANT", "OWNER_FAMILY", "RESIDENT"]:
            q = self._load_gql("graphql/community/queries/my_helpers.graphql")
            return self._fmt(self.execute_graphql(q, {}, token), "My Helpers")
        else:
            q = self._load_gql("graphql/community/queries/all_helpers.graphql")
            return self._fmt(self.execute_graphql(q, {}, token), "All Community Helpers")

    def _q_helpers_attendance(self, token):
        q = self._load_gql("graphql/community/queries/helpers_attendance.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Helpers Attendance")

    def _q_all_orders(self, token):
        q = self._load_gql("graphql/community/queries/all_orders.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "My Orders")

    def _q_all_sos(self, token):
        q = self._load_gql("graphql/community/queries/all_sos.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "SOS Alerts")

    def _q_all_forums(self, token):
        q = self._load_gql("graphql/community/queries/all_forums.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Community Forum Posts")

    def _q_all_polls(self, token):
        q = self._load_gql("graphql/community/queries/all_polls.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Active Polls")

    def create_amenity_booking(self, token: str, amenity_id: str, slot_ids: list, flat_id: str = "") -> dict:
        """Create an amenity booking via GraphQL mutation."""
        try:
            q = self._load_gql("graphql/amenities/mutations/create_amenity_booking.graphql")
            variables = {
                "data": {
                    "amenityId": amenity_id,
                    "slotIds": slot_ids,
                }
            }
            if flat_id:
                variables["data"]["flatId"] = flat_id
            
            print(f"\n[BOOKING] Sending mutation with variables: {json.dumps(variables, indent=2)}")
            raw = self.execute_graphql(q, variables, token)
            print(f"[BOOKING] Raw GraphQL response: {json.dumps(raw, indent=2, default=str)}")
            
            if "error" in raw:
                return {"status": "error", "message": str(raw["error"])}
            
            booking = raw.get("createAmenityBooking")
            
            # If booking is None or empty, the mutation silently failed on the server
            if not booking:
                return {
                    "status": "error",
                    "message": "Booking was not created. The server rejected the request (no booking returned). Check amenity_id, slot_ids, and flat_id are correct."
                }
            
            return {
                "status": "success",
                "booking": booking,
                "message": f"Booking confirmed! ID: {booking.get('id', 'N/A')}, Status: {booking.get('status', 'PENDING')}"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_blocks_and_flats(self, token: str) -> dict:
        """Return blocks and their flats from the user's apartment (parsed from myApartments)."""
        try:
            apts = self.get_my_apartments(token)
            apt_list = apts.get("myApartments", [])
            if not apt_list:
                return {"blocks": []}

            # Use the first apartment (the one currently logged in to)
            apt = apt_list[0]
            requests_list = apt.get("requests", [])

            blocks_map = {}
            for req in requests_list:
                flat = req.get("flat") or {}
                block = flat.get("block") or {}
                block_name = block.get("blockName", "")
                flat_number = flat.get("flatNumber", "")
                flat_id = flat.get("id", req.get("id", ""))  # fall back to request id if flat id missing
                if block_name:
                    if block_name not in blocks_map:
                        blocks_map[block_name] = []
                    blocks_map[block_name].append({
                        "flatNumber": flat_number,
                        "flatId": flat_id,
                        "requestId": req.get("id", "")
                    })

            blocks = [{"blockName": b, "flats": f} for b, f in sorted(blocks_map.items())]
            return {"blocks": blocks}
        except Exception as e:
            return {"blocks": [], "error": str(e)}

    def _q_family_members(self, token, role):
        if role in ["OWNER", "TENANT", "OWNER_FAMILY", "RESIDENT"]:
            q = self._load_gql("graphql/community/queries/my_flat_family.graphql")
            return self._fmt(self.execute_graphql(q, {}, token), "My Family Members (Flat)")
        else:
            q = self._load_gql("graphql/community/queries/all_family_members.graphql")
            return self._fmt(self.execute_graphql(q, {}, token), "All Community Family Members")

    def _q_all_pets(self, token):
        q = self._load_gql("graphql/community/queries/all_pets.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Registered Pets")

    def _q_all_meetings(self, token):
        q = self._load_gql("graphql/community/queries/all_meetings.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Meetings")

    def _q_all_flats(self, token):
        q = self._load_gql("graphql/community/queries/all_flats.graphql")
        variables = {
            "filter": {
                "blockId": "cmfe0l5i50002fj50daq25gsb",
                "perPage": 10,
                "pageNumber": 1
            }
        }
        return self._fmt(self.execute_graphql(q, variables, token), "Flats / Units")

    # ── REST calls ────────────────────────────────────────────────────────────
    def _r_coins_count(self, token):
        data = self.execute_rest("GET", "/reward-history/coins-count", token)
        return self._fmt(data, "Reward Coins Balance")

    def _r_reward_history(self, token):
        data = self.execute_rest("GET", "/reward-history/all-rewards", token)
        return self._fmt(data, "Reward History")

    def _r_user_ads(self, token):
        data = self.execute_rest("GET", "/user-ads/me", token)
        return self._fmt(data, "My Ads")

    # ── Intent → API chain map ────────────────────────────────────────────────
    def call_apis_in_sequence(self, intent: str, user_token: str, role: str = "RESIDENT", user_message: str = "", apartment_id: str = "") -> str:
        """
        Given an intent string, call the relevant Homefy APIs in sequence
        and return a combined context string for the AI prompt.
        """
        token = user_token
        context_parts = []

        if intent == "profile":
            context_parts.append(self._q_my_profile(token))

        elif intent == "complaints":
            try:
                cats = self._q_get_categories(token)
                if cats:
                    cat_lines = ["[Complaint Categories]:"]
                    for c in cats:
                        cat_lines.append(f"  - {c.get('name', 'Unknown')} (ID: {c.get('id')})")
                    context_parts.append("\n".join(cat_lines) + "\n")
                else:
                    context_parts.append("[Complaint Categories]: No categories available.\n")
                
                # Fetch both community and personal complaints
                comm = self._q_all_complaints(token, "COMMUNITY")
                pers = self._q_all_complaints(token, "PERSONAL")
                context_parts.append(self._fmt({"COMMUNITY": comm, "PERSONAL": pers}, "All Complaints"))

                import re
                comp_match = re.search(r'COM-[a-zA-Z]+-\d+', user_message)
                if comp_match:
                    comp_id = comp_match.group(0).upper()
                    detail = self._q_get_detailed_complaint(token, comp_id)
                    context_parts.append(self._fmt(detail, f"Detailed Complaint {comp_id}"))

            except Exception as e:
                context_parts.append(f"[Complaints]: unavailable ({e})")

        elif intent == "amenities":
            context_parts.append(self._q_all_amenities(token, apartment_id=apartment_id))
            context_parts.append(self._q_my_bookings(token))
            
            import re
            am_match = re.search(r'\b(cm[a-z0-9]{20,})\b', user_message, re.IGNORECASE)
            if am_match:
                am_id = am_match.group(1).lower()
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                start_date = now.strftime("%Y-%m-%dT00:00:00.000Z")
                end_date = (now + timedelta(days=2)).strftime("%Y-%m-%dT23:59:59.000Z")
                slots_data = self.get_amenity_slots(token, am_id, start_date, end_date)
                context_parts.append(self._fmt(slots_data, f"Detailed Slots for Amenity {am_id} (Next 48 Hours)"))

        elif intent == "bills":
            context_parts.append(self._q_my_bills(token))

        elif intent == "visitors":
            context_parts.append(self._q_all_entries_by_date(token))

        elif intent == "announcements":
            unread_only = "unread" in user_message.lower()
            context_parts.append(self._q_all_announcements(token, unread_only=unread_only))
            import re
            ann_match = re.search(r'\b(cm[a-z0-9]{20,})\b', user_message, re.IGNORECASE)
            if ann_match:
                ann_id = ann_match.group(1).lower()
                detail = self._q_get_detailed_announcement(token, ann_id)
                context_parts.append(self._fmt(detail, f"Detailed Announcement {ann_id}"))

        elif intent == "vehicles":
            context_parts.append(self._q_vehicles(token, role))
            context_parts.append(self._q_parking_categories(token))

        elif intent == "helpers":
            context_parts.append(self._q_helpers(token, role))
            context_parts.append(self._q_helpers_attendance(token))

        elif intent == "orders":
            context_parts.append(self._q_all_orders(token))

        elif intent == "rewards":
            context_parts.append(self._r_coins_count(token))
            context_parts.append(self._r_reward_history(token))

        elif intent == "sos":
            context_parts.append(self._q_all_sos(token))

        elif intent == "forum":
            context_parts.append(self._q_all_forums(token))
            context_parts.append(self._q_all_polls(token))

        elif intent == "family":
            context_parts.append(self._q_family_members(token, role))

        elif intent == "pets":
            context_parts.append(self._q_all_pets(token))

        elif intent == "meetings":
            context_parts.append(self._q_all_meetings(token))

        elif intent == "flats":
            context_parts.append(self._q_all_flats(token))

        return "\n".join(context_parts)
