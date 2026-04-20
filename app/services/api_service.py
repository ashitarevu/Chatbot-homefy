"""
api_handler.py — HomefyAPIHandler

Wraps Homefy's GraphQL API + REST endpoints by assembling modular Mixins.
Chains relevant queries based on intent and returns a concise
context string that is injected into the AI system prompt.
"""

from modules.base.api_client import BaseAPIClient
from modules.auth.auth_api import AuthMixin
from modules.amenities.amenity_api import AmenityMixin
from modules.complaints.complaint_api import ComplaintMixin
from modules.community.community_api import CommunityMixin
from modules.meetings.meeting_api import MeetingMixin
from modules.finance.finance_api import FinanceMixin
from modules.maintenance.maintenance_api import MaintenanceMixin
from modules.parking.parking_api import ParkingMixin
from modules.announcements.announcement_api import AnnouncementMixin


class HomefyAPIHandler(BaseAPIClient, AuthMixin, AmenityMixin, ComplaintMixin, CommunityMixin, MeetingMixin, FinanceMixin, MaintenanceMixin, ParkingMixin, AnnouncementMixin):
    """Executes Homefy GraphQL queries and REST calls and summarises results."""

    # ── Intent → API chain map ────────────────────────────────────────────────
    def call_apis_in_sequence(self, intent: str, user_token: str, role: str = "RESIDENT", user_message: str = "", apartment_id: str = "") -> str:
        """
        Given an intent string, call the relevant Homefy APIs in sequence
        and return a combined context string for the AI prompt.
        """
        token = user_token
        context_parts = []

        if intent == "profile":
            context_parts.append(self._q_my_profile(token))

        elif intent in ["community_complaints", "personal_complaints"]:
            try:
                cats = self._q_get_categories(token)
                if cats:
                    cat_lines = ["[Complaint Categories]:"]
                    for c in cats:
                        cat_lines.append(f"  - {c.get('name', 'Unknown')} (ID: {c.get('id')})")
                    context_parts.append("\n".join(cat_lines) + "\n")
                else:
                    context_parts.append("[Complaint Categories]: No categories available.\n")
                
                type_filter = "COMMUNITY" if intent == "community_complaints" else "PERSONAL"
                comps = self._q_all_complaints(token, type_filter)
                context_parts.append(comps)

                import re
                comp_match = re.search(r'COM-[a-zA-Z]+-\d+', user_message)
                if comp_match:
                    comp_id = comp_match.group(0).upper()
                    detail = self._q_get_detailed_complaint(token, comp_id)
                    context_parts.append(self._fmt(detail, f"Detailed Complaint {comp_id}"))

            except Exception as e:
                context_parts.append(f"[{intent.replace('_', ' ').title()}]: unavailable ({e})")

        elif intent == "amenities":
            context_parts.append(self._q_all_amenities(token, apartment_id=apartment_id))

            # Admins see all community bookings; residents see only their own
            ADMIN_ROLES = {"APARTMENT_ADMIN", "FACILITY_MANAGER", "FINANCE_ADMIN"}
            if role in ADMIN_ROLES:
                # Detect status filter from user's message
                msg_lower = user_message.lower()
                if "pending" in msg_lower:
                    booking_status = "PENDING"
                elif "cancelled" in msg_lower or "canceled" in msg_lower:
                    booking_status = "CANCELLED"
                elif "completed" in msg_lower:
                    booking_status = "COMPLETED"
                else:
                    booking_status = "CONFIRMED"
                context_parts.append(self._q_all_bookings(token, status=booking_status))
            else:
                context_parts.append(self._q_my_bookings(token))
            
            import re
            am_match = re.search(r'\b(cm[a-z0-9]{20,})\b', user_message, re.IGNORECASE)
            if am_match:
                am_id = am_match.group(1).lower()
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                start_date = now.strftime("%Y-%m-%dT00:00:00.000Z")
                end_date = (now + timedelta(days=2)).strftime("%Y-%m-%dT23:59:59.000Z")
                slots_data = self.get_amenity_slots(token, am_id, start_date, end_date)
                context_parts.append(self._fmt(slots_data, f"Detailed Slots for Amenity {am_id} (Next 48 Hours)"))

        elif intent == "bills":
            context_parts.append(self._q_other_bills(token))

        elif intent == "visitors":
            context_parts.append(self._q_all_entries_by_date(token))

        elif intent == "announcements":
            try:
                # Fetch categories for the context/LLM
                cats = self._q_get_announcement_categories(token)
                if cats:
                    cat_lines = ["[Announcement Categories]:"]
                    for c in cats:
                        cat_lines.append(f"  - {c.get('name', 'Unknown')} (ID: {c.get('id')})")
                    context_parts.append("\n".join(cat_lines) + "\n")
                else:
                    context_parts.append("[Announcement Categories]: No categories available.\n")

                # Detect if user mentioned a category ID or Name
                category_id = None
                if cats:
                    msg_lower = user_message.lower()
                    for c in cats:
                        c_id = c.get("id", "").lower()
                        c_name = c.get("name", "").lower()
                        if c_id in msg_lower or c_name in msg_lower:
                            category_id = c.get("id")
                            break

                unread_only = "unread" in user_message.lower()
                context_parts.append(self._q_all_announcements(token, unread_only=unread_only, category_id=category_id))
                
                import re
                ann_match = re.search(r'\b(cm[a-z0-9]{20,})\b', user_message, re.IGNORECASE)
                if ann_match:
                    ann_id = ann_match.group(1).lower()
                    detail = self._q_get_detailed_announcement(token, ann_id)
                    context_parts.append(self._fmt(detail, f"Detailed Announcement {ann_id}"))
            except Exception as e:
                context_parts.append(f"[Announcements Error]: {e}")

        elif intent == "vehicles":
            context_parts.append(self._q_vehicles(token, role))

        elif intent == "parking_resident":
            context_parts.append(self._q_parking_categories(token, type_filter="RESIDENT"))

        elif intent == "parking_other":
            context_parts.append(self._q_parking_categories(token, type_filter="OTHER"))

        elif intent == "helpers":
            context_parts.append(self._q_helpers(token, role))
            context_parts.append(self._q_helpers_attendance(token))

        elif intent == "orders":
            context_parts.append(self._q_all_orders(token))

        elif intent == "rewards":
            context_parts.append(self._r_coins_count(token))
            context_parts.append(self._r_reward_history(token))

        elif intent == "sos":
            context_parts.append(self._q_all_sos(token))

        elif intent == "forum":
            context_parts.append(self._q_all_forums(token))
            context_parts.append(self._q_all_polls(token))

        elif intent == "family":
            context_parts.append(self._q_family_members(token, role))

        elif intent == "pets":
            context_parts.append(self._q_all_pets(token))

        elif intent == "meetings":
            # 1. Detect intent to schedule/create FIRST to avoid unnecessary API calls
            msg_lower = user_message.lower()
            if any(x in msg_lower for x in ["schedule", "create", "add", "new meeting"]):
                if role not in ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"]:
                    return "🚫 User can't create meeting, only Admins are allowed."
                # Return the marker for the frontend to render the form
                return "__MEETING_FORM_MARKER__"

            # 2. Otherwise fetch meetings
            context_parts.append(self._q_all_meetings(token, apartment_id=apartment_id))
            raw_meetings = self.get_meetings_raw(token, apartment_id=apartment_id)
            if raw_meetings:
                context_parts.append("\n[RAW MEETING DATA FOR BUTTONS]:")
                context_parts.append(str(raw_meetings))
            
            import re
            meet_match = re.search(r'\b(cm[a-z0-9]{20,})\b', user_message, re.IGNORECASE)
            if meet_match:
                meet_id = meet_match.group(1).lower()
                detail = self._q_get_detailed_meeting(token, meet_id, apartment_id=apartment_id)
                context_parts.append(self._fmt(detail, f"Detailed Meeting {meet_id}"))

        elif intent == "flats":
            context_parts.append(self._q_all_flats(token))

        elif intent == "maintenance":
            context_parts.append(self._q_all_maintenances(token))

        return "\n".join(context_parts)
