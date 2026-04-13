import json

class AmenityMixin:
    """Contains logic for querying and booking amenities."""

    def _q_my_bookings(self, token):
        """Fetch the current user's own amenity bookings (resident role)."""
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

    def _q_all_bookings(self, token, status: str = "CONFIRMED", page: int = 1, per_page: int = 10):
        """Fetch all amenity bookings for admins with optional status filter and pagination."""
        q = self._load_gql("graphql/amenities/queries/all_bookings.graphql")
        try:
            variables = {
                "filter": {
                    "type": "AMENITY",
                    "perPage": per_page,
                    "pageNumber": page,
                    "parkingCategoryId": None,
                    "status": status,
                }
            }
            res = self.execute_graphql(q, variables, token)
            bookings_data = res.get("allBookings", {})
            if isinstance(bookings_data, dict) and bookings_data.get("data"):
                for booking in bookings_data["data"]:
                    b_id = booking.get("id")
                    if b_id:
                        booking["receiptUrl"] = f"https://api-staging.homefy.co.in/receipts/bills/{b_id}?type=amenity"
            label = f"All Amenity Bookings [{status}] (Page {page})"
            return self._fmt(res, label)
        except Exception as e:
            return f"[All Amenity Bookings]: unavailable ({e})"

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
        variables = {"filter": {"perPage": 30}}
        data = self.execute_graphql(q, variables, token, apartment_id=apartment_id)
        
        with open("last_amenity_debug.txt", "w") as f:
            f.write(json.dumps(data, indent=2))
        
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
            variables = {"filter": {"perPage": 30}}
            data = self.execute_graphql(q, variables, token, apartment_id=apartment_id)
            print(f"[AMENITY RAW FILTER] Raw GraphQL response: {json.dumps(data, indent=2, default=str)}")
            if "error" in data:
                return []
            amenities_obj = data.get("allAmenities")
            print(f"[AMENITY RAW FILTER] Amenities object: {json.dumps(amenities_obj, indent=2, default=str)}") 
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
