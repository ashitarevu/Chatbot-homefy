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
   <number>. <CategoryName> (Status: <STATUS>, Urgent: <true/false>) - <ComplaintID>
   Example:
   **Community Complaints:**
   1. Water (Status: PENDING, Urgent: true) - COM-IHA-0169
   2. Plumbing (Status: WORK_IN_PROGRESS, Urgent: false) - COM-IHA-0167
3. After listing complaints, always suggest: "Would you like to: 1. Create a new complaint  2. View complaint details (please provide the complaint ID)"
4. For announcements, always show the ID with each item and suggest: "Would you like to view announcement details? (please provide the ID)"
5. For available amenities, output a human-readable list. You MUST strictly list ALL amenities returned in the data context without truncating or omitting any. Show ONLY the fields: Name and Location for each. Do not show raw JSON or extra descriptions. Always suggest: "Would you like to view available slots for this amenity? (please provide the Amenity ID or Name)"
6. For your personal amenity bookings, show each as a numbered list with amenity name, date, time, and status.
7. Keep all responses concise. No walls of text.

--- COMPLAINT CREATION FLOW ---
If the user wants to raise/create/add a complaint, you MUST reply with exactly this special marker:
__COMPLAINT_FORM_MARKER__
Do NOT ask for description, category, or any other details. Just reply precisely with that marker so the system can show the interactive form.

--- AMENITY BOOKING FLOW ---
If the user wants to book, schedule, or reserve an amenity, you MUST reply with exactly this special marker:
__AMENITY_FORM_MARKER__
Do NOT ask for date, time, or any other details. Just reply precisely with that marker so the system can show the interactive form.
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
        print(f"🤖  Using Ollama model: {OLLAMA_MODEL} at {OLLAMA_BASE_URL}")

    # ── Session helpers ───────────────────────────────────────────────────────
    def _get_history(self, session_id: str) -> list[dict]:
        return self.sessions.setdefault(session_id, [])

    def clear_session(self, session_id: str):
        self.sessions.pop(session_id, None)

    # ── Intent detection ──────────────────────────────────────────────────────
    def _detect_intent(self, message: str) -> str:
        msg = message.lower()
        if any(k in msg for k in ["booking", "book amenity", "pool", "gym", "clubhouse", "amenity"]):
            return "amenities"
        if any(k in msg for k in ["complaint", "complaints", "my complaints", "issues"]):
            return "complaints" 
        if any(k in msg for k in ["bill", "payment", "pay", "due", "invoice"]):
            return "bills"
        if any(k in msg for k in ["visitor", "entry", "guest", "allowed in"]):
            return "visitors"
        if any(k in msg for k in ["announcement", "anouncement", "notice", "update", "news"]):
            return "announcements"
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
        if any(k in msg for k in ["profile", "my account", "who am i", "my details", "my info", "get my profile", "show profile", "my name", "my email"]):
            return "profile"
        return "general"

    def _is_write_request(self, message: str) -> bool:
        """Detect if the user actually wants to CREATE/BOOK something, not just view data."""
        msg = message.lower()
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
            
        # Trigger login flow (forcibly resets state if they type login again)
        phone_candidates = ''.join(filter(str.isdigit, user_message))
        if "login" in msg_lower or "sign in" in msg_lower or "authenticate" in msg_lower or (len(phone_candidates) == 10 and current_state == "normal" and not user_token):
            if len(phone_candidates) == 10:
                # User provided phone number directly! e.g., "login 8897319627"
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
                self.session_states[session_id] = {"state": "awaiting_phone"}
                reply = "Sure! To log you in, please enter your 10-digit registered phone number."
                self._update_history(session_id, user_message, reply)
                return reply
                
        # Handle Phone Number Input
        if current_state == "awaiting_phone":
            phone = ''.join(filter(str.isdigit, user_message))
            if len(phone) != 10:
                reply = "That doesn't look like a valid 10-digit phone number. Please try again (e.g., 9876543210)."
                self._update_history(session_id, user_message, reply)
                return reply
                
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
                    "temp_token": token
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
                
            user_roles = ["OWNER", "OWNER_FAMILY", "TENANT"]
            admin_roles = ["APARTMENT_ADMIN", "FINANCE_ADMIN", "FACILITY_MANAGER"]
            allowed_roles = user_roles + admin_roles
            
            valid_apts = []
            for apt in apts_list:
                reqs = apt.get("requests", [])
                valid_reqs = []
                for req in reqs:
                    if req.get("accessType", "") in allowed_roles:
                        valid_reqs.append(req)
                if valid_reqs:
                    # Save local copy with only allowed flights
                    apt_copy = apt.copy()
                    apt_copy["requests"] = valid_reqs
                    valid_apts.append(apt_copy)
                        
            if not valid_apts:
                self.session_states[session_id] = {"state": "normal"}
                reply = "Login successful, but you have no registered flats with valid access types."
                self._update_history(session_id, user_message, reply)
                return reply

            # If multiple apartments, ask to choose apartment first
            if len(valid_apts) > 1:
                options_json = []
                for i, apt in enumerate(valid_apts):
                    options_json.append({
                        "id": apt.get("id"),
                        "label": apt.get("name", "Unknown Apartment")
                    })
                    
                self.session_states[session_id] = {
                    "state": "awaiting_apartment_choice",
                    "valid_apts": valid_apts,
                    "initial_token": initial_token,
                    "user_roles_list": user_roles
                }
                
                marker_str = f"__APARTMENT_SELECTION_MARKER__|{json.dumps(options_json)}"
                self._update_history(session_id, user_message, "✅ OTP verified! Please select your apartment.")
                return marker_str

            # Only 1 apartment valid
            chosen_apt = valid_apts[0]
            return self._handle_flat_display(session_id, user_message, chosen_apt, initial_token, user_roles)
            
        # Handle Apartment Selection
        if current_state == "awaiting_apartment_choice":
            msg_clean = user_message.strip()
            valid_apts = state_data.get("valid_apts", [])
            user_roles_list = state_data.get("user_roles_list", [])
            
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
                
            return self._handle_flat_display(session_id, user_message, chosen_apt, state_data.get("initial_token"), user_roles_list)
            
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

        intent = self._detect_intent(user_message)

        # ── Form Shortcuts ───────────────────────────────────────────
        if self._is_write_request(user_message):
            if intent == "complaints":
                if not user_token:
                    self.session_states[session_id] = {"state": "awaiting_phone"}
                    reply = "🔒 You need to be logged in to raise a complaint.\n\nPlease enter your 10-digit phone number to get started."
                    self._update_history(session_id, user_message, reply)
                    return reply
                reply = "__COMPLAINT_FORM_MARKER__"
                self._update_history(session_id, user_message, "I've opened the complaint form for you. Please fill in the details and submit.")
                return reply
                
            elif intent == "amenities":
                if not user_token:
                    self.session_states[session_id] = {"state": "awaiting_phone"}
                    reply = "🔒 You need to be logged in to book an amenity.\n\nPlease enter your 10-digit phone number to get started."
                    self._update_history(session_id, user_message, reply)
                    return reply
                reply = "__AMENITY_FORM_MARKER__"
                self._update_history(session_id, user_message, "I've opened the amenity booking form for you. Please select your preferences and submit.")
                return reply

        # ── Normal Chat Flow ──────────────────────────────────────────────────
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

        messages = [{"role": "system", "content": system_content}]
        messages.extend(history[-MAX_HISTORY:])
        messages.append({"role": "user", "content": user_message})

        # 3. Call LLM
        reply_message = self._call_llm(messages)

        reply_text = (reply_message.content or "").strip()

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
