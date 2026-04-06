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
SYSTEM_PROMPT = """You are Homefy Assistant, a smart and friendly AI chatbot for the Homefy 
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

--- RESPONSE FORMATTING RULES ---
1. NEVER use markdown tables. Always use numbered lists.
2. For complaints, group them by type (Community / Personal) and show each as:
   <number>. <CategoryName> (Status: <STATUS>, Urgent: <true/false>) - <ComplaintID>
   Example:
   **Community Complaints:**
   1. Water (Status: PENDING, Urgent: true) - COM-IHA-0169
   2. Plumbing (Status: WORK_IN_PROGRESS, Urgent: false) - COM-IHA-0167
3. After listing complaints, always suggest: "Would you like to: 1. Create a new complaint  2. View complaint details"
4. For amenity bookings, show each as a numbered list with amenity name, date, time, and status.
5. Keep all responses concise. No walls of text.

--- COMPLAINT CREATION FLOW ---
If the user wants to raise/create/add a complaint, you MUST reply with exactly this special marker:
__COMPLAINT_FORM_MARKER__
Do NOT ask for description, category, or any other details. Just reply precisely with that marker so the system can show the interactive form.

--- FUNCTION CALLING RULES (MUST FOLLOW STRICTLY) ---
1. NEVER call a function inside another function. Functions cannot be nested.
2. Call only ONE function at a time. Wait for the system to return the result before proceeding.
3. For amenity booking, you MUST follow this exact two-step sequence:
   - Step 1: Call get_amenity_slots with the amenity_id and date range to retrieve available slot IDs.
   - Step 2: Only AFTER receiving real slot IDs from the system response, call create_amenity_booking with those IDs.
4. The slot_ids parameter in create_amenity_booking MUST contain actual ID strings returned by get_amenity_slots. NEVER pass function calls, placeholders, or made-up text as slot_ids.
5. If get_amenity_slots returns an error or empty slots, inform the user — do NOT proceed to create_amenity_booking.
6. NEVER invent or guess function names. Only call: get_amenity_slots, create_amenity_booking.
"""

# ── Model config ───────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")

MAX_HISTORY = 20   # keep last 20 messages per session

LLM_TOOLS = [
    {

        "type": "function",
        "function": {
            "name": "create_amenity_booking",
            "description": "Book an amenity such as a swimming pool or clubhouse slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amenity_id": {"type": "string", "description": "The GUID of the amenity to book, found in the Available Amenities context."},
                    "slot_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of slot GUIDs the user wants to book. MUST be valid IDs."
                    }
                },
                "required": ["amenity_id", "slot_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_amenity_slots",
            "description": "Fetch available slots for an amenity for a specific date range. Always call this FIRST before calling create_amenity_booking, to find valid slot_ids.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amenity_id": {"type": "string", "description": "The GUID of the amenity, found in the Available Amenities context."},
                    "start_date": {"type": "string", "description": "The ISO string for the start date (e.g. '2026-04-03T00:00:00Z')."},
                    "end_date": {"type": "string", "description": "The ISO string for the end date (e.g. '2026-04-03T23:59:59Z')."}
                },
                "required": ["amenity_id", "start_date", "end_date"]
            }
        }
    }
]

class HomefyChatbot:
    """Stateful chatbot with per-session conversation memory."""

    def __init__(self):
        self.sessions: dict[str, list[dict]] = {}  # session_id → message history
        self.api_handler = HomefyAPIHandler()
        self.auth_tokens = {}
        self.user_roles = {}
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
        if any(k in msg for k in ["announcement", "notice", "update", "news"]):
            return "announcements"
        if any(k in msg for k in ["vehicle", "car", "bike", "parking"]):
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
    def _call_llm(self, messages: list[dict], use_tools: bool = False):
        kwargs = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        if use_tools:
            kwargs["tools"] = LLM_TOOLS
            kwargs["tool_choice"] = "auto"
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
                
            # Multiple apartments (or even 1, still need to get the permanent token!) -> ask user to choose or auto-select
            if len(apts_list) == 1:
                # Auto select the only flat
                req_list = apts_list[0].get("requests", [])
                req_id = req_list[0].get("id") if req_list else apts_list[0].get("id")
                
                
                access_res = self.api_handler.get_access_token(request_id=req_id, token=initial_token)
                final_token = access_res.get("accessToken", {}).get("token")
                print(f"\n========== PERMANENT ACCESS TOKEN ==========\n{final_token}\n============================================\n")
                
                if not final_token:
                    self.session_states[session_id] = {"state": "normal"}
                    reply = "Failed to get the final access token for your flat. Please try again later."
                    self._update_history(session_id, user_message, reply)
                    return reply
                self.auth_tokens[session_id] = final_token
                self.session_states[session_id]["apartment_id"] = req_id
                
                if hasattr(self, 'user_roles'):
                    self.user_roles[session_id] = req_list[0].get("accessType", "RESIDENT") if req_list else "RESIDENT"
                    
                self.session_states[session_id] = {"state": "normal"}

                
                apt_name = apts_list[0].get("name", "your flat")
                reply = f"✅ Login successful! You are now logged in to **{apt_name}**. How can I help you today?"
                self._update_history(session_id, user_message, reply)
                return reply
                
            # Multiple apartments -> ask user to choose
            options = []
            for i, apt in enumerate(apts_list):
                apt_name = apt.get("name", "")
                role = "Resident"
                display_name = apt_name
                
                reqs = apt.get("requests", [])
                if reqs and isinstance(reqs, list) and len(reqs) > 0:
                    role = reqs[0].get("accessType", "Resident")
                    
                    # Fetch block and flat number from the nested 'flat' object inside 'requests'
                    flat_obj = reqs[0].get("flat") or {}
                    flat_num = flat_obj.get("flatNumber", "")
                    block_obj = flat_obj.get("block") or {}
                    block_name = block_obj.get("blockName", "")
                    
                    if flat_num:
                        if block_name:
                            display_name = f"{apt_name} - {block_name}-{flat_num}"
                        else:
                            display_name = f"{apt_name} - {flat_num}"
                        
                # Fallback for purely numeric apartment names lacking nested flat data 
                if display_name == apt_name and apt_name.isdigit():
                    display_name = f"Flat {apt_name}"
                    
                options.append(f"{i+1}. {display_name} (Role: {role})")
                
            options_str = "\n".join(options)
            self.session_states[session_id] = {
                "state": "awaiting_apartment",
                "apartments": apts_list,
                "initial_token": initial_token
            }
            
            reply = f"✅ OTP verified! You are associated with multiple flats. Please reply with the number of the flat you want to select:\n\n{options_str}"
            self._update_history(session_id, user_message, reply)
            return reply
            
        # Handle Apartment Selection
        if current_state == "awaiting_apartment":
            try:
                choice = int(''.join(filter(str.isdigit, user_message))) - 1
                apts_list = state_data.get("apartments", [])
                
                if choice < 0 or choice >= len(apts_list):
                    raise ValueError()
            except ValueError:
                reply = "Please reply with a valid number from the list above."
                self._update_history(session_id, user_message, reply)
                return reply
                
            # Final token exchange
            req_list = apts_list[choice].get("requests", [])
            req_id = req_list[0].get("id") if req_list else apts_list[choice].get("id")
            
            initial_token = state_data.get("initial_token")
            access_res = self.api_handler.get_access_token(request_id=req_id, token=initial_token)
            
            final_token = access_res.get("accessToken", {}).get("token")
            print(f"\n========== PERMANENT ACCESS TOKEN ==========\n{final_token}\n============================================\n")
            if not final_token:
                self.session_states[session_id] = {"state": "normal"}
                reply = f"Failed to get the final access token for your selected flat. Please login again. Debug: {access_res}"
                self._update_history(session_id, user_message, reply)
                return reply
                
            self.auth_tokens[session_id] = final_token
            self.session_states[session_id]["apartment_id"] = req_id
            
            if hasattr(self, 'user_roles'):
                self.user_roles[session_id] = req_list[0].get("accessType", "RESIDENT") if req_list else "RESIDENT"
                
            self.session_states[session_id] = {"state": "normal"}
            
            apt_name = apts_list[choice].get("name", "your flat")
            reply = f"✅ Awesome, you are now logged in to **{apt_name}**! What would you like to do?"
            self._update_history(session_id, user_message, reply)
            return reply

        intent = self._detect_intent(user_message)

        # ── Complaint Form Shortcut ───────────────────────────────────────────
        if intent == "complaints" and self._is_write_request(user_message):
            if not user_token:
                self.session_states[session_id] = {"state": "awaiting_phone"}
                reply = "🔒 You need to be logged in to raise a complaint.\n\nPlease enter your 10-digit phone number to get started."
                self._update_history(session_id, user_message, reply)
                return reply
            reply = "__COMPLAINT_FORM_MARKER__"
            self._update_history(session_id, user_message, "I've opened the complaint form for you. Please fill in the details and submit.")
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
                api_context = self.api_handler.call_apis_in_sequence(
                    intent, user_token, role=user_role
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

        # 3. Call LLM — only enable tools when we have enough context
        use_tools = False
        if self._is_write_request(user_message):
            if intent == "amenities":
                use_tools = True
            elif intent == "complaints":
                # Only enable tools if the conversation already has complaint context
                # (i.e., user has been through the ask flow and provided details)
                recent_history = history[-6:]  # last 3 exchanges
                history_text = " ".join(m.get("content", "") for m in recent_history).lower()
                # Check if categories were already discussed AND user has provided description
                category_names = [c["name"].lower() for c in self.api_handler.FALLBACK_CATEGORIES]
                has_category = any(cat in history_text for cat in category_names)
                has_description = len(user_message.split()) > 5  # user gave some detail
                use_tools = has_category and has_description
        reply_message = self._call_llm(messages, use_tools=use_tools)

        # Handle tool calls from LLM
        if getattr(reply_message, "tool_calls", None):

            # Only process the FIRST tool call — no chaining allowed
            tool_call = reply_message.tool_calls[0]
            function_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            # ── Validate create_amenity_booking before executing ───────────
            if function_name == "create_amenity_booking":
                slot_ids = args.get("slot_ids", [])
                invalid = (
                    not slot_ids or
                    any(isinstance(s, str) and "<function=" in s for s in slot_ids)
                )
                if invalid:
                    amenity_id = args.get("amenity_id", "")
                    import datetime
                    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
                    res = self.api_handler.get_amenity_slots(
                        token=user_token,
                        amenity_id=amenity_id,
                        start_date=f"{tomorrow}T00:00:00Z",
                        end_date=f"{tomorrow}T23:59:59Z"
                    )
                    reply_text = (
                        f"I need to check available slots first before booking.\n\n"
                        f"Available slots: {json.dumps(res, indent=2)}\n\n"
                        f"Please choose a slot and I'll confirm the booking."
                    )
                    self._update_history(session_id, user_message, reply_text)
                    return reply_text

            # ── Execute the single valid tool call ─────────────────────
            if function_name == "create_amenity_booking":
                res = self.api_handler.create_amenity_booking(
                    token=user_token,
                    amenity_id=args.get("amenity_id"),
                    slot_ids=args.get("slot_ids", [])
                )
            elif function_name == "get_amenity_slots":
                res = self.api_handler.get_amenity_slots(
                    token=user_token,
                    amenity_id=args.get("amenity_id"),
                    start_date=args.get("start_date"),
                    end_date=args.get("end_date")
                )
            else:
                res = {"error": f"Unknown function: {function_name}"}

            # ── Append assistant + tool result messages ──────────────────
            assistant_message = reply_message.model_dump(exclude_unset=True)
            if assistant_message.get("content") is None:
                assistant_message["content"] = ""
            if "function_call" in assistant_message and assistant_message["function_call"] is None:
                del assistant_message["function_call"]
            messages.append(assistant_message)
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(res)
            })

            # ── Final LLM call — NO tools, just generate text reply ──────
            final_response = self.client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
            reply_text = (final_response.choices[0].message.content or "").strip()

        else:
            reply_text = (reply_message.content or "").strip()

        # 4. Update history
        self._update_history(session_id, user_message, reply_text)

        return reply_text
        
    def _update_history(self, session_id: str, user_message: str, bot_reply: str):
        history = self._get_history(session_id)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_reply})
        if len(history) > MAX_HISTORY:
            self.sessions[session_id] = history[-MAX_HISTORY:]
