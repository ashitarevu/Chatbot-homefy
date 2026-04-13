class AuthMixin:
    """Contains logic for authentication, tokens, and apartment fetching."""

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
