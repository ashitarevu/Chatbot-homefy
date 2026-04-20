import json

class FinanceMixin:
    """Contains logic for querying financial records like bills, coins, and rewards."""

    def _q_my_bills(self, token):
        q = self._load_gql("graphql/community/queries/my_bills.graphql")
        return self._fmt(self.execute_graphql(q, {}, token), "My Bills (Maintenance)")

    def _q_get_bills_raw(self, token):
        """Fetch all user bills as raw data."""
        try:
            q = self._load_gql("graphql/community/queries/my_bills.graphql")
            res = self.execute_graphql(q, {}, token)
            bills_obj = res.get("myBills", {})
            return bills_obj.get("data", []) if isinstance(bills_obj, dict) else []
        except Exception:
            return []

    def _q_bill_categories_raw(self, token) -> list:
        """Fetch all bill categories (type=BILL) — Rental, Electricity, Gas Bill, etc."""
        try:
            q = self._load_gql("graphql/finance/queries/bill_categories.graphql")
            data = self.execute_graphql(q, {"filter": {"type": "BILL"}}, token)
            if "error" in data:
                return []
            cats = data.get("allCategories", {})
            if isinstance(cats, dict):
                return cats.get("data", [])
            return []
        except Exception as e:
            print(f"[BILL CATEGORIES] Error: {e}")
            return []

    def _q_other_bills(self, token):
        """Fetch all user bills and group them by category (Electricity, Gas, Rental etc)."""
        import json
        try:
            # 1. Fetch bill categories (Rental, Electricity Bill, Gas Bill …)
            categories = self._q_bill_categories_raw(token)
            cat_map = {c["id"]: c["name"] for c in categories}

            # 2. Fetch ALL bills for the user
            q = self._load_gql("graphql/community/queries/my_bills.graphql")
            res = self.execute_graphql(q, {}, token)

            bills_obj = res.get("myBills", {})
            bills = bills_obj.get("data", []) if isinstance(bills_obj, dict) else []

            # 3. Group bills by category name
            by_cat: dict = {c["name"]: [] for c in categories} # prefill all categories
            for b in bills:
                cat_name = (
                    b.get("category", {}).get("name", "")
                    if isinstance(b.get("category"), dict)
                    else ""
                )
                if not cat_name:
                    cat_name = cat_map.get(b.get("categoryId", ""), "Uncategorised")
                
                if cat_name not in by_cat:
                    by_cat[cat_name] = []
                by_cat[cat_name].append(b)

            # 4. Build context block
            lines = ["[My Bills Grouped By Category]:"]
            
            for cat_name, cat_bills in by_cat.items():
                lines.append(f"\n  {cat_name}:")
                if not cat_bills:
                    lines.append("    - No bills found for this category.")
                else:
                    for b in cat_bills:
                        status = b.get("status", "Unknown")
                        amount = b.get("totalAmount", b.get("amount", 0))
                        bill_id = b.get("billId", b.get("id", "N/A"))
                        last_date = (b.get("lastDate") or "N/A")[:10]
                        overdue = " ⚠️ OVERDUE" if b.get("isOverDue") else ""
                        lines.append(
                            f"    - [{bill_id}] ₹{amount} | Status: {status} | Due: {last_date}{overdue}"
                        )

            return "\n".join(lines) + "\n"
        except Exception as e:
            return f"[Bills]: unavailable ({e})"

    def create_bill(self, token, amount, category_id, flat_id, last_date, applicable_to, notes=None):
        """Create a new user bill utilizing the CreateBill mutation."""
        try:
            q = self._load_gql("graphql/finance/mutations/create_bill.graphql")
            
            data = {
                "amount": float(amount),
                "categoryId": category_id,
                "flatId": flat_id,
                "lastdate": last_date,
                "applicableTo": applicable_to
            }
            if notes:
                data["notes"] = notes
                
            res = self.execute_graphql(q, {"data": data}, token)
            
            if "error" in res:
                return {"status": "error", "message": res["error"]}
                
            # Usually createBill returns true/false or the new ID
            if res.get("createBill"):
                return {"status": "success", "message": "Bill successfully generated."}
            else:
                return {"status": "error", "message": "Failed to generate the bill."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _r_coins_count(self, token):
        data = self.execute_rest("GET", "/reward-history/coins-count", token)
        return self._fmt(data, "Reward Coins Balance")

    def _r_reward_history(self, token):
        data = self.execute_rest("GET", "/reward-history/all-rewards", token)
        return self._fmt(data, "Reward History")

    def _r_user_ads(self, token):
        data = self.execute_rest("GET", "/user-ads/me", token)
        return self._fmt(data, "My Ads")
