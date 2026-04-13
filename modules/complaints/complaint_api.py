class ComplaintMixin:
    """Contains logic for querying and creating complaints."""

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
            all_items = []
            cursor_id = None
            
            while True:
                filter_args = {"type": type_filter, "perPage": 20}
                if cursor_id:
                    filter_args["cursorId"] = cursor_id
                    
                variables = {"filter": filter_args}
                data = self.execute_graphql(q, variables, token)

                if "error" in data:
                    return f"[{type_filter} Complaints API Error]: {data['error']}\n"

                all_comp_data = data.get("allComplaints") or data.get("myComplaints")
                page_items = []
                has_next = False
                
                if isinstance(all_comp_data, dict):
                    page_items = all_comp_data.get("data", [])
                    has_next = all_comp_data.get("hasNext", False)
                elif isinstance(all_comp_data, list):
                    page_items = all_comp_data
                
                if not page_items:
                    break
                    
                all_items.extend(page_items)
                
                if not has_next:
                    break
                    
                # The cursor expects the raw string `id` (not `complaintId`) of the last item
                cursor_id = page_items[-1].get("id")
                
                if not cursor_id:
                    break
            
            if not all_items:
                return f"[{type_filter} Complaints]: No complaints found.\n"
                
            lines = [f"[{type_filter} Complaints]:"]
            for c in all_items:
                c_id = c.get('complaintId', c.get('id', 'Unknown'))
                status = c.get('status', 'Unknown')
                urgent = c.get('isUrgent', False)
                cat = c.get('category', {}).get('name', 'General') if isinstance(c.get('category'), dict) else 'General'
                
                # Extract creator name and flat safely
                cb = c.get('createdBy', {}) if isinstance(c.get('createdBy'), dict) else {}
                cb_usr = cb.get('user', {}) if isinstance(cb, dict) else {}
                creator_name = f"{cb_usr.get('firstName', '')} {cb_usr.get('lastName', '')}".strip() or "Unknown User"
                
                flat_info = ""
                cb_flat = cb.get('flat', {}) if isinstance(cb, dict) else {}
                if cb_flat:
                    f_num = cb_flat.get('flatNumber', '')
                    b_name = cb_flat.get('block', {}).get('blockName', '') if isinstance(cb_flat.get('block'), dict) else ''
                    if b_name and f_num:
                        flat_info = f" ({b_name}-{f_num})"
                    elif f_num:
                        flat_info = f" (Flat {f_num})"
                        
                creator = f"{creator_name}{flat_info}"
                
                lines.append(f"  - {c_id}: {cat} (Status: {status}, Urgent: {urgent}, Created By: {creator})")
                
            return "\n".join(lines) + "\n"
        except Exception as e:
            return f"[{type_filter} Complaints Error]: {e}\n"

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
