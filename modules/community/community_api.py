class CommunityMixin:
    """Contains logic for all community-related queries (announcements, helpers, vehicles, etc)."""

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
