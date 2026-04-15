class ParkingMixin:
    """Contains logic for querying and creating parking categories."""

    def _q_parking_categories(self, token, type_filter=None):
        try:
            q = self._load_gql("graphql/parking/queries/all_parking_categories.graphql")
            
            filter_vars = {}
            if type_filter:
                filter_vars["type"] = type_filter
                
            data = self.execute_graphql(q, {"filter": filter_vars}, token)
            if "error" in data:
                return "[Parking Categories]: unavailable"
            return self._fmt(data, "Parking Categories")
        except Exception as e:
            return f"[Parking Categories]: unavailable ({e})"

    def create_parking_category(self, token, name, p_type, min_booking, schedule_type, payment_type, base_price=0, max_booking=None):
        """Create a new parking category using the CreateParkingCategory mutation."""
        try:
            q = self._load_gql("graphql/parking/mutations/create_parking_category.graphql")
            
            data = {
                "name": name,
                "type": p_type,
                "minBooking": int(min_booking),
                "scheduleType": schedule_type,
                "paymentType": payment_type,
                "basePrice": float(base_price)
            }
            if max_booking:
                data["maxBooking"] = int(max_booking)
                
            res = self.execute_graphql(q, {"data": data}, token)
            
            if "error" in res:
                return {"status": "error", "message": res["error"]}
                
            if res.get("createParkingCategory"):
                return {"status": "success", "message": "Parking category successfully created."}
            else:
                return {"status": "error", "message": "Failed to create parking category."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
