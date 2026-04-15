class MaintenanceMixin:
    """Contains logic for querying community maintenance records."""

    def _q_all_maintenances(self, token, page_number=1, per_page=10):
        """Fetch all community maintenance records."""
        q = self._load_gql("graphql/maintenance/queries/all_maintenances.graphql")
        variables = {
            "filter": {
                "pageNumber": page_number,
                "perPage": per_page
            }
        }
        return self._fmt(self.execute_graphql(q, variables, token), "Maintenances")

    def get_maintenances_raw(self, token: str, page_number=1, per_page=10) -> list:
        """Fetch all community maintenance records as a raw list of dictionaries."""
        try:
            q = self._load_gql("graphql/maintenance/queries/all_maintenances.graphql")
            variables = {
                "filter": {
                    "pageNumber": page_number,
                    "perPage": per_page
                }
            }
            data = self.execute_graphql(q, variables, token)
            if "error" in data:
                return []
            maintenances_obj = data.get("allMaintenances")
            if isinstance(maintenances_obj, dict):
                return maintenances_obj.get("data", [])
            return []
        except Exception:
            return []
