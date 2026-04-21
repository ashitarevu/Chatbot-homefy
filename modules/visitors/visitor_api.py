import datetime

class VisitorMixin:
    """Contains logic for visitor-related queries."""

    def _q_all_entries_by_date(self, token):
        # Migrated from community_api.py (Legacy)
        q = self._load_gql("graphql/community/queries/all_entries_by_date.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "Visitor Entries Today")

    def _q_get_visitors_raw(self, token):
        """Fetch visitor entries for today as a raw list using the admin query."""
        try:
            q = self._load_gql("graphql/visitors/queries/all_entries_for_admin.graphql")
            
            # Calculate today's start and end dates in UTC ISO format (or IST if preferred, but assuming UTC by default)
            now = datetime.datetime.utcnow()
            
            # For exact 24hr coverage requested by GraphQL query format:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999000).strftime('%Y-%m-%dT%H:%M:%S.999Z')
            
            variables = {
                "filter": {
                    "startDate": start_date,
                    "endDate": end_date,
                    "perPage": 10,  # Or increase if more are needed
                    "pageNumber": 1,
                    "type": "VISITOR"
                }
            }
            
            data = self.execute_graphql(q, variables, token)
            if "error" in data: 
                print(f"GraphQL Error in _q_get_visitors_raw: {data['error']}")
                return []
            
            entries_obj = data.get("allEntriesForAdmin")
            if isinstance(entries_obj, dict):
                return entries_obj.get("data", [])
            return []
        except Exception as e:
            print(f"Error fetching visitor logs: {e}")
            return []
