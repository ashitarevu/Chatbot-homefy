"""
chatbot.py — HomefyChatbot

Manages conversation history per session and routes messages
through intent detection → Homefy API calls → LLM response.
"""

import os
import json
from dotenv import load_dotenv
from api_handler import HomefyAPIHandler

load_dotenv()

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Homefy Assistant, a smart and friendly AI chatbot for the [Homefy 
residential community management platform. You help residents and society managers with:

• Amenity bookings (swimming pool, gym, clubhouse, etc.)
• Complaint registration and tracking
• Visitor and entry management
• Bill payments and reward points
• Society announcements and meetings
• Vehicle management and parking
• Helpers and staff attendance
• SOS emergency alerts
• Community forum, polls, and discussions                                                                                                
• Orders from the community store/marketplace
• Family members, pets, and flat information

Always be polite, concise, and helpful. When you have real data from the system (provided in the 
context), use it directly in your answer. If information is not available, guide the user on how 
to find it in the app.

If the user greets you, introduce yourself briefly as the Homefy Assistant.
Do NOT make up data — only reference what is provided in the API context.
Keep responses short and easy to read. Use bullet points for lists.

--- OUT OF SCOPE QUERIES ---
If the user asks questions that are NOT related to Homefy or managing a residential community (e.g., coding, general knowledge, math, politics, etc.), you MUST politely decline.
Reply exactly or similar to: "I'm Homefy Assistant. I can only help you with tasks related to your Homefy community, such as bookings, complaints, and visitors. I can't answer other questions."

--- RESPONSE FORMATTING RULES ---
1. NEVER use markdown tables. Always use numbered lists.
2. For complaints, group them by type (Community / Personal) and show each as:
   <number>. <CategoryName> (Status: <STATUS>, Urgent: <true/false>) [Created By: <CreatorName>] - <ComplaintID>
   Example:
   **Community Complaints:**
   1. Water (Status: PENDING, Urgent: true) [Created By: John Doe (Block A - 101)] - COM-IHA-0169
   2. Plumbing (Status: WORK_IN_PROGRESS, Urgent: false) [Created By: Jane Smith (Flat 202)] - COM-IHA-0167
3. After listing complaints, always suggest: "Would you like to: 1. Create a new complaint  2. View complaint details (please provide the complaint ID)"
4. For announcements, always show the ID with each item and suggest: "Would you like to view announcement details? (please provide the ID)"
5. For available amenities, output a human-readable list. You MUST strictly list ALL amenities returned in the data context without truncating or omitting any. Show ONLY the fields: Name and Location for each. Do not show raw JSON or extra descriptions. Always suggest: "Would you like to view available slots for this amenity? (please provide the Amenity ID or Name)"
6. For your personal amenity bookings, show each as a numbered list with amenity name, date, time, and status.
7. For bills, group them by category (e.g. Rental, Electricity, Gas Bill). For each bill show: Bill ID, Amount (₹), Status, Due Date. Highlight ⚠️ OVERDUE bills prominently.
8. For community meetings, if you are listing multiple upcoming meetings, you MUST respond exactly with the special marker and a JSON payload: `__MEETING_SELECTION_MARKER__|[{"id": "...", "label": "..."}]`. Do NOT add any extra text or pleasantries. If you are showing details for just ONE meeting, format it as a clean text summary.
9. Keep all responses concise. No walls of text.

--- COMPLAINT CREATION FLOW ---
If the user wants to raise/create/add a complaint, you MUST reply with exactly this special marker:
__COMPLAINT_FORM_MARKER__

--- MEETING CREATION FLOW ---
If the user wants to schedule/create/add/new a meeting, you MUST reply with exactly this special marker:
__MEETING_FORM_MARKER__
Do NOT ask for description, category, or any other details. Just reply precisely with that marker so the system can show the interactive form.

--- AMENITY BOOKING FLOW ---
If the user wants to book, schedule, or reserve an amenity, you MUST reply with exactly this special marker:
__AMENITY_FORM_MARKER__
Do NOT ask for date, time, or any other details. Just reply precisely with that marker so the system can show the interactive form.

--- BILL CREATION FLOW ---
If the user wants to generate, create, or add a bill (Rental, Electricity, Maintenance, etc.), you MUST reply with exactly this special marker:
__BILL_FORM_MARKER__
Do NOT ask for amounts, categories, or flats. Just reply precisely with that marker so the system can show the interactive form.

--- PARKING CREATION FLOW ---
If the user wants to add, create, or register a new parking category, you MUST reply with exactly this special marker:
__PARKING_FORM_MARKER__
Do NOT ask for details. Just reply precisely with that marker so the system can show the interactive form.
"""

# ── Model config ───────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")

MAX_HISTORY = 20   # keep last 20 messages per session

class HomefyChatbot:
    """Stateful chatbot with per-session conversation memory."""

    def __init__(self):
        self.sessions: dict[str, list[dict]] = {}  # session_id → message history
        self.api_handler = HomefyAPIHandler()
        self.auth_tokens = {}
        self.user_roles = {}
        self.apartment_ids: dict[str, str] = {}  # session_id → apartment ID
        self._init_model()

    # ── Model initialisation ──────────────────────────────────────────────────
    def _init_model(self):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama"
        )
        self.model_name = OLLAMA_MODEL
        print(f"Using Ollama model: {OLLAMA_MODEL} at {OLLAMA_BASE_URL}")

    # ── Session helpers ───────────────────────────────────────────────────────
    def _get_history(self, session_id: str) -> list[dict]:
        return self.sessions.setdefault(session_id, [])

    def clear_session(self, session_id: str):
        self.sessions.pop(session_id, None)

    # ── Intent detection ──────────────────────────────────────────────────────
    def _detect_intent(self, message: str) -> str:
        msg = message.lower()
        if any(k in msg for k in ["booking", "book amenity", "pool", "gym", "clubhouse", "amenity", "amenities"]):
            return "amenities"
        if "community_complaints_req" in msg or "community complaints" in msg:
            return "community_complaints"
        if "personal_complaints_req" in msg or "personal complaints" in msg:
            return "personal_complaints"
        if any(k in msg for k in ["complaint", "complaints", "my complaints", "issues", "complaints_menu"]):
            return "complaints_menu" 
        if any(k in msg for k in ["bill", "payment", "pay", "due", "invoice"]):
            return "bills"
        if any(k in msg for k in ["visitor", "entry", "guest", "allowed in"]):
            return "visitors"
        if any(k in msg for k in ["announcement", "anouncement", "notice", "update", "news"]):
            return "announcements"
        if "parking_resident_req" in msg:
            return "parking_resident"
        if "parking_other_req" in msg:
            return "parking_other"
        if any(k in msg for k in ["vehicle", "car", "bike", "parking", "park my", "parking slot", "parking space", "parking category", "two wheeler", "four wheeler"]):
            return "vehicles"
        if any(k in msg for k in ["helper", "maid", "cleaner", "cook", "attendence", "attendance"]):
            return "helpers"
        if any(k in msg for k in ["order", "shop", "store", "product", "cart", "buy"]):
            return "orders"
        if any(k in msg for k in ["reward", "coin", "point", "earn"]):
            return "rewards"
        if any(k in msg for k in ["sos", "emergency", "help!", "danger", "urgent"]):
            return "sos"
        if any(k in msg for k in ["forum", "post", "discussion", "poll", "vote"]):
            return "forum"
        if any(k in msg for k in ["family", "member", "resident"]):
            return "family"
        if any(k in msg for k in ["pet", "dog", "cat", "animal"]):
            return "pets"
        if any(k in msg for k in ["meeting", "agm", "committee"]):
            return "meetings"
        if any(k in msg for k in ["flat", "unit", "floor"]):
            return "flats"
        if any(k in msg for k in ["maintenance", "maintenance bill"]):
            return "maintenance"
        if any(k in msg for k in ["profile", "my account", "who am i", "my details", "my info", "get my profile", "show profile", "my name", "my email"]):
            return "profile"
        return "general"

    def _is_write_request(self, message: str) -> bool:
        """Detect if the user actually wants to CREATE/BOOK something, not just view data."""
        msg = message.lower()

        # These phrases look like write-requests but are actually read requests — exclude them first
        read_overrides = [
            "show booking", "show my booking", "view booking", "my booking",
            "see booking", "list booking", "all booking", "check booking",
            "booking status", "bookings", "show amenity booking",
        ]
        if any(r in msg for r in read_overrides):
            return False

        write_keywords = [
            "book", "create", "raise", "register", "add", "make a complaint",
            "file a complaint", "submit", "want to book", "schedule", "i want to raise",
            "i want to create", "can you book", "please book", "make a booking",
            "form"
        ]
        return any(w in msg for w in write_keywords)

    # ── LLM call ─────────────────────────────────────────────────────────────
    def _call_llm(self, messages: list[dict]):
        kwargs = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message

    # ── Main chat method ──────────────────────────────────────────────────────
    def chat(self, session_id: str, user_message: str, user_token: str = "") -> str:
        history = self._get_history(session_id)
        
        # ── State Machine Check ───────────────────────────────────────────────
        if not hasattr(self, 'session_states'):
            self.session_states = {}

        # ── Always use stored token if user has already logged in ─────────────
        # This ensures profile, complaints, and ALL other intents work
        # without asking to login again every time.
        stored_token = getattr(self, 'auth_tokens', {}).get(session_id, "")
        if stored_token:
            user_token = stored_token
            
        current_state = self.session_states.get(session_id, {}).get("state", "normal")
        state_data = self.session_states.get(session_id, {})
        
        msg_lower = user_message.lower().strip()
        
        # Handle cancellation ANYWHERE
        if current_state != "normal" and msg_lower == "cancel":
            self.session_states[session_id] = {"state": "normal"}
            reply = "Login cancelled. How can I help you?"
            self._update_history(session_id, user_message, reply)
            return reply
            
        # Handle Logout ANYWHERE
        if msg_lower in ["logout", "exit", "sign out", "log out"]:
            self.session_states.pop(session_id, None)
            if hasattr(self, 'auth_tokens'):
                self.auth_tokens.pop(session_id, None)
            if hasattr(self, 'user_roles'):
                self.user_roles.pop(session_id, None)
            if hasattr(self, 'apartment_ids'):
                self.apartment_ids.pop(session_id, None)
            self.sessions.pop(session_id, None) # Clear conversation history too
            return "You have been fully logged out of the chatbot session. To start a new session, you can type 'login' followed by your phone number."
            
        # Handle Role Choice — MUST be before the login trigger to avoid LOGIN_AS_ADMIN matching "login"
        if current_state == "awaiting_role_choice":
            chosen_role = user_message.strip()
            is_admin = (chosen_role == "LOGIN_AS_ADMIN")
            self.session_states[session_id] = {
                "state": "awaiting_phone",
                "login_as_admin": is_admin
            }
            role_label = "Admin" if is_admin else "User"
            reply = f"Great! Logging in as **{role_label}**.\n\nPlease enter your 10-digit registered phone number."
            self._update_history(session_id, user_message, reply)
            return reply

        # Trigger login flow — only fires in normal state to avoid false matches
        phone_candidates = ''.join(filter(str.isdigit, user_message))
        if current_state == "normal" and (
            "login" in msg_lower or "sign in" in msg_lower or "authenticate" in msg_lower
            or (len(phone_candidates) == 10 and not user_token)
        ):
            if len(phone_candidates) == 10:
                # User provided phone number directly after choosing role
                import auth
                res = auth.send_otp(phone_candidates)
                if "error" in res:
                    self.session_states[session_id] = {"state": "normal"}
                    reply = f"Failed to send OTP: {res['error']}. Let's start over."
                else:
                    token = res.get("result", {}).get("token") or res.get("token")
                    self.session_states[session_id] = {
                        "state": "awaiting_otp",
                        "phone": phone_candidates,
                        "temp_token": token
                    }
                    reply = f"I've sent a 6-digit OTP to +91-{phone_candidates}. Please enter it here."
                self._update_history(session_id, user_message, reply)
                return reply
            else:
                # Show role selection buttons first
                options_json = [
                    {"id": "LOGIN_AS_USER", "label": "👤 User"},
                    {"id": "LOGIN_AS_ADMIN", "label": "🔑 Admin"}
                ]
                marker_str = f"__ROLE_SELECTION_MARKER__|{json.dumps(options_json)}"
                self.session_states[session_id] = {"state": "awaiting_role_choice"}
                self._update_history(session_id, user_message, "Are you logging in as a User or an Admin?")
                return marker_str

                
        # Handle Phone Number Input
        if current_state == "awaiting_phone":
            phone = ''.join(filter(str.isdigit, user_message))
            if len(phone) != 10:
                reply = "That doesn't look like a valid 10-digit phone number. Please try again (e.g., 9876543210)."
                self._update_history(session_id, user_message, reply)
                return reply
                
            # Preserve the login_as_admin flag across all state transitions
            login_as_admin = state_data.get("login_as_admin", None)
            
            # Send OTP
            import auth
            res = auth.send_otp(phone)
            if "error" in res:
                self.session_states[session_id] = {"state": "normal"}
                reply = f"Failed to send OTP: {res['error']}. Let's start over. How can I help you?"
            else:
                token = res.get("result", {}).get("token") or res.get("token")
                self.session_states[session_id] = {
                    "state": "awaiting_otp",
                    "phone": phone,
                    "temp_token": token,
                    "login_as_admin": login_as_admin  # carry forward
                }
                reply = f"I've sent a 6-digit OTP to +91-{phone}. Please enter it here."
                
            self._update_history(session_id, user_message, reply)
            return reply
            
        # Handle OTP Verification
        if current_state == "awaiting_otp":
            code = ''.join(filter(str.isdigit, user_message))
            if len(code) != 6:
                reply = "Please enter the 6-digit OTP I sent to your phone."
                self._update_history(session_id, user_message, reply)
                return reply
                
            temp_token = state_data.get("temp_token")
            import auth
            res = auth.verify_otp(code, temp_token)
            
            if "error" in res:
                reply = f"Verification failed ({res['error']}). Please try entering the OTP again, or type 'cancel' to stop."
                self._update_history(session_id, user_message, reply)
                return reply
                
            initial_token = res.get("access_token")
            if not initial_token:
                self.session_states[session_id] = {"state": "normal"}
                reply = "Verification succeeded but the API didn't return a token. Please try again later."
                self._update_history(session_id, user_message, reply)
                return reply
                
            # Fetch apartments to let user choose
            apartments = self.api_handler.get_my_apartments(initial_token)
            apts_list = apartments.get("myApartments", [])
            
            if not apts_list:
                self.session_states[session_id] = {"state": "normal"}
                reply = "Login successful, but no apartments are registered to this phone number."
                self._update_history(session_id, user_message, reply)
                return reply
            
            # Read the role flag carried forward from earlier states
            login_as_admin = state_data.get("login_as_admin", None)
            
            user_roles = ["OWNER", "OWNER_FAMILY", "TENANT"]
            admin_roles = ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"]

            # Only show APPROVED or ACTIVE requests — filter out REJECTED, PENDING, etc.
            allowed_statuses = {"APPROVED", "ACTIVE"}
            valid_apts = []
            for apt in apts_list:
                active_reqs = [
                    r for r in apt.get("requests", [])
                    if r.get("accessStatus", "").upper() in allowed_statuses
                ]
                if active_reqs:
                    apt_copy = apt.copy()
                    apt_copy["requests"] = active_reqs
                    valid_apts.append(apt_copy)

            if not valid_apts:
                self.session_states[session_id] = {"state": "normal"}
                reply = "Login successful, but no approved apartments are registered to this phone number."
                self._update_history(session_id, user_message, reply)
                return reply


            # ALWAYS show apartment selection so the user consciously picks which apartment
            options_json = []
            for apt in valid_apts:
                options_json.append({
                    "id": apt.get("id"),
                    "label": apt.get("name", "Unknown Apartment")
                })
                
            self.session_states[session_id] = {
                "state": "awaiting_apartment_choice",
                "valid_apts": valid_apts,
                "initial_token": initial_token,
                "login_as_admin": login_as_admin,  # carry forward
                "user_roles_list": user_roles,
                "admin_roles_list": admin_roles
            }
            
            marker_str = f"__APARTMENT_SELECTION_MARKER__|{json.dumps(options_json)}"
            self._update_history(session_id, user_message, "✅ OTP verified! Please select your apartment.")
            return marker_str


            
        # Handle Apartment Selection
        if current_state == "awaiting_apartment_choice":
            msg_clean = user_message.strip()
            valid_apts = state_data.get("valid_apts", [])
            user_roles_list = state_data.get("user_roles_list", [])
            login_as_admin = state_data.get("login_as_admin", None)  # read carried flag
            initial_token = state_data.get("initial_token")
            
            chosen_apt = next((a for a in valid_apts if a.get("id") == msg_clean), None)
            
            if not chosen_apt:
                try:
                    choice = int(''.join(filter(str.isdigit, user_message))) - 1
                    if 0 <= choice < len(valid_apts):
                        chosen_apt = valid_apts[choice]
                except ValueError:
                    pass
            
            if not chosen_apt:
                reply = "Please select a valid apartment."
                self._update_history(session_id, user_message, reply)
                return reply
            
            user_roles_list = state_data.get("user_roles_list", ["OWNER", "OWNER_FAMILY", "TENANT"])
            admin_roles_list = state_data.get("admin_roles_list", ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"])

            if login_as_admin:
                # Admin: filter to admin-role requests in this apartment, pick the first one
                admin_reqs = [r for r in chosen_apt.get("requests", []) if r.get("accessType", "") in admin_roles_list]
                if not admin_reqs:
                    reply = "No admin access found for this apartment. Please select another or contact support."
                    self._update_history(session_id, user_message, reply)
                    return reply
                return self._finalize_login(session_id, user_message, chosen_apt, admin_reqs[0], initial_token)
            else:
                # User: filter to user-role requests (flats) and show them as buttons
                user_reqs = [r for r in chosen_apt.get("requests", []) if r.get("accessType", "") in user_roles_list]
                if not user_reqs:
                    # Re-show apartment selection so they can try again
                    options_json = [{"id": apt.get("id"), "label": apt.get("name", "Unknown Apartment")} for apt in valid_apts]
                    marker_str = f"__APARTMENT_SELECTION_MARKER__|{json.dumps(options_json)}"
                    self._update_history(session_id, user_message, "No user flats found. Please select another apartment.")
                    reply = f"❌ You don't have **User** (Resident/Owner) access to **{chosen_apt.get('name', 'this apartment')}**.\n\nThis apartment only has Admin access for your account. Please go back and log in as **🔑 Admin** instead, or select a different apartment.\n\n" + marker_str
                    return reply
                apt_copy = chosen_apt.copy()
                apt_copy["requests"] = user_reqs
                return self._handle_flat_display(session_id, user_message, apt_copy, initial_token, user_roles_list)

            
        # Handle Flat Selection
        if current_state == "awaiting_flat_choice":
            msg_clean = user_message.strip()
            chosen_apt = state_data.get("chosen_apt", {})
            reqs = chosen_apt.get("requests", [])
            
            chosen_flat = next((f for f in reqs if f.get("id") == msg_clean), None)
            
            if not chosen_flat:
                try:
                    choice = int(''.join(filter(str.isdigit, user_message))) - 1
                    if 0 <= choice < len(reqs):
                        chosen_flat = reqs[choice]
                except ValueError:
                    pass
            
            if not chosen_flat:
                reply = "Please select a valid flat."
                self._update_history(session_id, user_message, reply)
                return reply
                
            return self._finalize_login(session_id, user_message, chosen_apt, chosen_flat, state_data.get("initial_token"))

        # Bypass LLM intent classification if the message is exactly a Meeting ID
        import re
        if re.search(r'^cm[a-z0-9]{20,}$', user_message.strip().lower()):
            intent = "meetings"
            print(f"[{session_id}] Bypassed LLM Intent (Meeting ID match): meetings")
        else:
            intent = self._detect_intent(user_message)

        # ── Form Shortcuts ───────────────────────────────────────────
        if self._is_write_request(user_message):
            if intent in ["complaints_menu", "community_complaints", "personal_complaints"]:
                if not user_token:
                    self.session_states[session_id] = {"state": "awaiting_phone"}
                    reply = "🔒 You need to be logged in to raise a complaint.\n\nPlease enter your 10-digit phone number to get started."
                    self._update_history(session_id, user_message, reply)
                    return reply
                user_role = getattr(self, "user_roles", {}).get(session_id, "")
                admin_roles = ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"]
                is_admin = user_role in admin_roles
                
                # We no longer block admins completely, we open the form and let the frontend hide the Personal option
                marker_str = f"__COMPLAINT_FORM_MARKER__|{json.dumps({'isAdmin': is_admin})}"
                self._update_history(session_id, user_message, "I've opened the complaint form for you. Please fill in the details and submit.")
                return marker_str
                
            elif intent == "amenities":
                if not user_token:
                    self.session_states[session_id] = {"state": "awaiting_phone"}
                    reply = "🔒 You need to be logged in to book an amenity.\n\nPlease enter your 10-digit phone number to get started."
                    self._update_history(session_id, user_message, reply)
                    return reply
                reply = "__AMENITY_FORM_MARKER__"
                self._update_history(session_id, user_message, "I've opened the amenity booking form for you. Please select your preferences and submit.")
                return reply
                
            elif intent == "bills":
                if not user_token:
                    self.session_states[session_id] = {"state": "awaiting_phone"}
                    reply = "🔒 You need to be logged in to generate a bill.\n\nPlease enter your 10-digit phone number to get started."
                    self._update_history(session_id, user_message, reply)
                    return reply
                user_role = getattr(self, "user_roles", {}).get(session_id, "")
                admin_roles = ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"]
                if user_role not in admin_roles:
                    reply = "🚫 Sorry, only Admins and Finance Managers can generate bills."
                    self._update_history(session_id, user_message, reply)
                    return reply
                reply = "__BILL_FORM_MARKER__"
                self._update_history(session_id, user_message, "I've opened the bill generation form for you. Please fill in the details and submit.")
                return reply

            elif intent == "vehicles":
                if not user_token:
                    self.session_states[session_id] = {"state": "awaiting_phone"}
                    reply = "🔒 You need to be logged in to create a parking category.\n\nPlease enter your 10-digit phone number to get started."
                    self._update_history(session_id, user_message, reply)
                    return reply
                reply = "__PARKING_FORM_MARKER__"
                self._update_history(session_id, user_message, "I've opened the parking category form for you. Please fill in the details and submit.")
                return reply

        # ── Normal Chat Flow ──────────────────────────────────────────────────
        if intent == "complaints_menu" and not self._is_write_request(user_message):
            if not user_token:
                self.session_states[session_id] = {"state": "awaiting_phone"}
                reply = "🔒 You need to be logged in to view complaints.\n\nPlease enter your 10-digit phone number to get started."
                self._update_history(session_id, user_message, reply)
                return reply
            
            # Admins only see Community Complaints — Personal Complaints are flat-specific
            user_role = getattr(self, "user_roles", {}).get(session_id, "")
            admin_roles = ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"]
            if user_role in admin_roles:
                options_json = [
                    {"id": "COMMUNITY_COMPLAINTS_REQ", "label": "🏘️ Community Complaints"}
                ]
            else:
                options_json = [
                    {"id": "COMMUNITY_COMPLAINTS_REQ", "label": "🏘️ Community Complaints"},
                    {"id": "PERSONAL_COMPLAINTS_REQ", "label": "🏠 Personal (Flat) Complaints"}
                ]
            marker_str = f"__COMPLAINT_TYPE_MARKER__|{json.dumps(options_json)}"
            self._update_history(session_id, user_message, "Which type of complaints would you like to view?")
            return marker_str

        if intent == "vehicles" and not self._is_write_request(user_message) and "parking" in user_message.lower() and "PARKING_" not in user_message:
            if not user_token:
                self.session_states[session_id] = {"state": "awaiting_phone"}
                reply = "🔒 You need to be logged in to view parking.\n\nPlease enter your 10-digit phone number to get started."
                self._update_history(session_id, user_message, reply)
                return reply
                
            options_json = [
                {"id": "PARKING_RESIDENT_REQ", "label": "Resident Parking Categories"},
                {"id": "PARKING_OTHER_REQ", "label": "Other Parking Categories"}
            ]
            marker_str = f"__PARKING_TYPE_MARKER__|{json.dumps(options_json)}"
            self._update_history(session_id, user_message, "Which type of parking categories would you like to view?")
            return marker_str

        api_context = ""
        if intent != "general":
            if not user_token:
                self.session_states[session_id] = {"state": "awaiting_phone"}
                reply = "🔒 You need to be logged in to view your personalized information.\n\nPlease enter your 10-digit phone number to get started."
                self._update_history(session_id, user_message, reply)
                return reply
                
            try:
                user_role = getattr(self, "user_roles", {}).get(session_id, "RESIDENT")
                apartment_id = getattr(self, "apartment_ids", {}).get(session_id, "")
                api_context = self.api_handler.call_apis_in_sequence(
                    intent, user_token, role=user_role, user_message=user_message,
                    apartment_id=apartment_id
                )
            except Exception as e:
                api_context = f"(API data unavailable: {e})"

        # 2. Build messages list for LLM
        system_content = SYSTEM_PROMPT
        if api_context:
            system_content += f"\n\n--- LIVE DATA FROM HOMEFY SYSTEM ---\n{api_context}\n---"

        with open("logs/last_api_context.txt", "w", encoding="utf-8") as f:
            f.write(api_context)
        
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history[-MAX_HISTORY:])
        
        # Friendly prompt replacements for internal UI commands
        display_message = user_message
        if display_message == "PERSONAL_COMPLAINTS_REQ":
            display_message = "Please show me my personal complaints."
        elif display_message == "COMMUNITY_COMPLAINTS_REQ":
            display_message = "Please show me the community complaints."
        elif display_message == "PARKING_RESIDENT_REQ":
            display_message = "Please show me Resident parking categories."
        elif display_message == "PARKING_OTHER_REQ":
            display_message = "Please show me Other parking categories."

        messages.append({"role": "user", "content": display_message})

        # 3. Call LLM
        reply_message = self._call_llm(messages)

        reply_text = (reply_message.content or "").strip()
        
        # Fallback if the LLM completely failed to extract/format response
        if not reply_text:
            if api_context and ("[PERSONAL Complaints]" in api_context or "[COMMUNITY Complaints]" in api_context or "Amenities" in api_context):
                reply_text = "Here is the data I found:\n" + api_context
            else:
                reply_text = "I couldn't find any relevant data or I encountered an error. Please try again."

        # 4. Update history
        self._update_history(session_id, user_message, reply_text)

        return reply_text
        
    def _handle_flat_display(self, session_id: str, user_message: str, chosen_apt: dict, initial_token: str, user_roles: list):
        reqs = chosen_apt.get("requests", [])
        
        if len(reqs) == 1:
            return self._finalize_login(session_id, user_message, chosen_apt, reqs[0], initial_token)
            
        options_json = []
        apt_name = chosen_apt.get("name", "Unknown Apartment")
        
        for req in reqs:
            access_type = req.get("accessType", "")
            group = "User" if access_type in user_roles else "Admin"
            
            flat_obj = req.get("flat") or {}
            flat_num = flat_obj.get("flatNumber", "")
            block_obj = flat_obj.get("block") or {}
            block_name = block_obj.get("blockName", "")
            
            display_name = apt_name
            if flat_num:
                if block_name:
                    display_name = f"{apt_name} - {block_name}-{flat_num}"
                else:
                    display_name = f"{apt_name} - {flat_num}"
            elif apt_name.isdigit():
                display_name = f"Flat {apt_name}"
                
            options_json.append({
                "id": req.get("id"),
                "label": display_name,
                "role": f"{group} - {access_type}"
            })
            
        self.session_states[session_id] = {
            "state": "awaiting_flat_choice",
            "chosen_apt": chosen_apt,
            "initial_token": initial_token
        }
        marker_str = f"__FLAT_SELECTION_MARKER__|{json.dumps(options_json)}"
        self._update_history(session_id, user_message, "Please select your flat.")
        return marker_str
        
    def _finalize_login(self, session_id: str, user_message: str, chosen_apt: dict, chosen_flat: dict, initial_token: str):
        req_id = chosen_flat.get("id")
        access_res = self.api_handler.get_access_token(request_id=req_id, token=initial_token)
        
        final_token = access_res.get("accessToken", {}).get("token")
        print(f"\n========== PERMANENT ACCESS TOKEN ==========\n{final_token}\n============================================\n")
        if not final_token:
            error_data = access_res.get('error', [{}])[0].get('extensions', {})
            backend_msg = error_data.get('error', {}).get('message') or error_data.get('message') or str(access_res)
            
            # Formulate the error explanation
            explanation = f"❌ The backend refused access to this flat. **(Reason: {backend_msg})**\n\nThis generally means the flat's request ID is stale, pending admin approval, or incorrectly mapped on the server.\n\n"
            
            # Reattach the flat selection marker so the user can click again without restarting
            reqs = chosen_apt.get("requests", [])
            options_json = []
            apt_name = chosen_apt.get("name", "Unknown Apartment")
            user_roles = self.session_states.get(session_id, {}).get("user_roles_list", ["OWNER", "OWNER_FAMILY", "TENANT"])
            
            for req in reqs:
                access_type = req.get("accessType", "")
                group = "User" if access_type in user_roles else "Admin"
                flat_obj = req.get("flat") or {}
                flat_num = flat_obj.get("flatNumber", "")
                block_obj = flat_obj.get("block") or {}
                block_name = block_obj.get("blockName", "")
                
                display_name = apt_name
                if flat_num:
                    display_name = f"{apt_name} - {block_name}-{flat_num}" if block_name else f"{apt_name} - {flat_num}"
                elif apt_name.isdigit():
                    display_name = f"Flat {apt_name}"
                    
                options_json.append({
                    "id": req.get("id"),
                    "label": display_name,
                    "role": f"{group} - {access_type}"
                })
                
            marker_str = f"__FLAT_SELECTION_MARKER__|{json.dumps(options_json)}"
            
            # Restore state so they can click again
            self.session_states[session_id] = {
                "state": "awaiting_flat_choice",
                "chosen_apt": chosen_apt,
                "initial_token": initial_token,
                "user_roles_list": user_roles
            }
            
            full_reply = explanation + marker_str
            self._update_history(session_id, user_message, explanation + "Please select another flat.")
            return full_reply
            
        self.auth_tokens[session_id] = final_token
        
        # Store the apartment ID so amenity queries can be filtered by apartment
        apt_id = chosen_apt.get("id", "")
        if not hasattr(self, 'apartment_ids'):
            self.apartment_ids = {}
        self.apartment_ids[session_id] = apt_id
        
        if hasattr(self, 'user_roles'):
            self.user_roles[session_id] = chosen_flat.get("accessType", "RESIDENT")
            
        self.session_states[session_id] = {"state": "normal"}
        
        apt_name = chosen_apt.get("name", "Unknown Apartment")
        reply = f"✅ Awesome, you are now logged in to **{apt_name}**! What would you like to do?"
        self._update_history(session_id, "Selected flat", reply)
        return reply

    def _update_history(self, session_id: str, user_message: str, bot_reply: str):
        history = self._get_history(session_id)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_reply})
        if len(history) > MAX_HISTORY:
            self.sessions[session_id] = history[-MAX_HISTORY:]
