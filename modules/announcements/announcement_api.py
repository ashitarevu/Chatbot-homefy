class AnnouncementMixin:
    """Contains logic for all announcement-related queries."""

    def _q_all_announcements(self, token, unread_only=False, category_id=None):
        try:
            q = self._load_gql("graphql/announcements/queries/all_announcements.graphql")
            all_items = []
            cursor_id = None
            
            while True:
                filter_args = {"perPage": 20}
                if unread_only:
                    filter_args["getUnread"] = True
                if category_id:
                    filter_args["categoryId"] = category_id
                if cursor_id:
                    filter_args["cursorId"] = cursor_id
                    
                variables = {"filter": filter_args}
                data = self.execute_graphql(q, variables, token)

                if "error" in data:
                    return f"[Announcements API Error]: {data['error']}\n"

                all_ann_data = data.get("allAnnouncements")
                page_items = []
                has_next = False
                
                if isinstance(all_ann_data, dict):
                    page_items = all_ann_data.get("data", [])
                    has_next = all_ann_data.get("hasNext", False)
                elif isinstance(all_ann_data, list):
                    page_items = all_ann_data
                
                if not page_items:
                    break
                    
                all_items.extend(page_items)
                
                if not has_next:
                    break
                    
                cursor_id = page_items[-1].get("id")
                if not cursor_id:
                    break
            
            if not all_items:
                title = "Unread Announcements" if unread_only else "Announcements"
                if category_id:
                    title += f" (Category: {category_id})"
                return f"[{title}]: No announcements found.\n"
                
            lines = [f"[{'Unread ' if unread_only else ''}Announcements]:"]
            for a in all_items:
                a_id = a.get('id', 'Unknown')
                a_title = a.get('title', 'No Title')
                a_type = a.get('type', 'ALL')
                cat = a.get('announcementCategory', {}).get('name', 'General') if isinstance(a.get('announcementCategory'), dict) else 'General'
                is_read = a.get('isRead', False)
                
                read_status = " (Read)" if is_read else " (Unread)"
                lines.append(f"  - {a_id}: {a_title} [{cat}] (Target: {a_type}){read_status}")
                
            return "\n".join(lines) + "\n"
        except Exception as e:
            return f"[Announcements Error]: {e}\n"

    def _q_get_announcements_raw(self, token, unread_only=False, category_id=None, mine_only=False, user_id=None):
        """Fetch announcements and return as raw data."""
        try:
            q = self._load_gql("graphql/announcements/queries/all_announcements.graphql")
            all_items = []
            cursor_id = None
            
            while True:
                filter_args = {"perPage": 20}
                if unread_only:
                    filter_args["getUnread"] = True
                if category_id:
                    filter_args["categoryId"] = category_id
                if cursor_id:
                    filter_args["cursorId"] = cursor_id
                    
                variables = {"filter": filter_args}
                data = self.execute_graphql(q, variables, token)
                if "error" in data: return []

                all_ann_data = data.get("allAnnouncements")
                page_items = []
                has_next = False
                
                if isinstance(all_ann_data, dict):
                    page_items = all_ann_data.get("data", [])
                    has_next = all_ann_data.get("hasNext", False)
                elif isinstance(all_ann_data, list):
                    page_items = all_ann_data
                
                if not page_items: break
                all_items.extend(page_items)
                if not has_next: break
                cursor_id = page_items[-1].get("id")
                if not cursor_id: break
            
            # --- Client-side filtering for 'My Announcements' ---
            if mine_only and user_id:
                all_items = [a for a in all_items if a.get("createdBy", {}).get("id") == user_id]
            
            return all_items
        except Exception:
            return []

    def _q_get_detailed_announcement(self, token, announcement_id):
        try:
            q = self._load_gql("graphql/announcements/queries/get_detailed_announcement.graphql")
            data = self.execute_graphql(q, {"announcementId": announcement_id}, token)
            if "error" in data:
                return {"error": data["error"]}
            return data.get("announcement", {})
        except Exception as e:
            return {"error": str(e)}

    def _q_get_announcement_categories(self, token):
        """Fetch announcement categories from API."""
        try:
            q = self._load_gql("graphql/announcements/queries/get_categories.graphql")
            data = self.execute_graphql(q, {"filter": {"type": "ANNOUNCEMENT"}}, token)
            if "error" in data:
                return []
            cats = data.get("allCategories", {})
            return cats.get("data", []) if isinstance(cats, dict) else (cats or [])
        except Exception:
            return []

    def add_announcement(self, token: str, title: str, description: str, category_id: str, ann_type: str = "ALL") -> dict:
        """Handle creating a new announcement via GraphQL."""
        try:
            q = self._load_gql("graphql/announcements/mutations/add_announcement.graphql")
            variables = {
                "data": {
                    "title": title,
                    "description": description,
                    "categoryId": category_id,
                    "type": ann_type
                }
            }
            data = self.execute_graphql(q, variables, token)
            if "error" in data:
                return {"status": "error", "message": f"Failed to add announcement: {data['error']}"}
            
            ann_data = data.get("createAnnouncement", {})
            return {"status": "success", "message": f"Announcement '{title}' added successfully! ID: {ann_data.get('id')}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
