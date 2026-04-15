class MeetingMixin:
    """Contains logic for querying community meetings."""

    def _q_all_meetings(self, token, apartment_id=""):
        """Fetch all community meetings."""
        q = self._load_gql("graphql/meetings/queries/all_meetings.graphql")
        return self._fmt(self.execute_graphql(q, {}, token, apartment_id=apartment_id), "Meetings")

    def _q_get_detailed_meeting(self, token, meeting_id, apartment_id=""):
        """Fetch detailed information about a specific meeting."""
        try:
            q = self._load_gql("graphql/meetings/queries/get_meeting_details.graphql")
            data = self.execute_graphql(q, {"meetingId": meeting_id}, token, apartment_id=apartment_id)
            if "error" in data:
                return {"error": data["error"]}
            return data.get("meeting", {})
        except Exception as e:
            return {"error": str(e)}

    def get_meetings_raw(self, token: str, apartment_id="") -> list:
        """Fetch all community meetings as a raw list of dictionaries."""
        try:
            q = self._load_gql("graphql/meetings/queries/all_meetings.graphql")
            data = self.execute_graphql(q, {}, token, apartment_id=apartment_id)
            if "error" in data:
                return []
            meetings_obj = data.get("allMeetings")
            if isinstance(meetings_obj, dict):
                return meetings_obj.get("data", [])
            return []
        except Exception:
            return []

    def create_meeting(self, token, data, apartment_id=""):
        """Create a new community meeting using the CreateMeeting mutation."""
        try:
            q = self._load_gql("graphql/meetings/mutations/create_meeting.graphql")
            
            # Map frontend names to GraphQL names if different
            # Screenshot shows: Title, Location, Start Time, End Time, Link, Description
            # I will pass the raw data dict as provided by the frontend
            res = self.execute_graphql(q, {"data": data}, token, apartment_id=apartment_id)
            
            if "error" in res:
                # If error is from GraphQL errors list
                if isinstance(res["error"], list) and len(res["error"]) > 0:
                    msg = res["error"][0].get("message", "Unknown error")
                    return {"status": "error", "message": msg}
                return {"status": "error", "message": str(res["error"])}
                
            if res.get("createMeeting"):
                return {"status": "success", "message": "Meeting successfully scheduled."}
            else:
                return {"status": "error", "message": "Failed to create the meeting."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
