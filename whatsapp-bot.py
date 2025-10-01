from pywa import WhatsApp, types, filters
from fastapi import FastAPI, Request
import openai
import json

# In-memory store for chat history; use Redis/DB for production
history = {}

def get_chat_history(user_id):
    # Returns last 5 messages as list of dicts
    return history.get(user_id, [])[-5:]

def add_message(user_id, role, content):
    if user_id not in history:
        history[user_id] = []
    history[user_id].append({"role": role, "content": content})

# Rule-based responses; load from file and hot-reloadable
def load_rules():
    with open("responses.json") as f:
        return json.load(f)
rules = load_rules()

openai.api_key = "YOUR_OPENAI_API_KEY"

app = FastAPI()
wa = WhatsApp(
    phone_id="YOUR_PHONE_ID",
    token="YOUR_ACCESS_TOKEN",
    server=app,
    callback_url="https://YOUR_DOMAIN/webhook",
    verify_token="VERIFY_TOKEN"
)

def needs_human(text):
    sensitive = ["human", "agent", "escalate", "refund", "complaint"]
    return any(w in text for w in sensitive)

def notify_human(user_id, msg):
    print(f"ROUTE TO HUMAN: {user_id}: {msg}")

@wa.on_message(filters.text)
def respond(client: WhatsApp, msg: types.Message):
    user_id = msg.from_user.wa_id
    text = msg.text.lower()
    add_message(user_id, "user", text)

    if needs_human(text):
        notify_human(user_id, text)
        msg.reply_text("Connecting you to a human agent. Please wait.")
        return

    if text in rules:
        reply = rules[text]
    else:
        # Use chat history as LLM context
        messages = [{"role": h["role"], "content": h["content"]}
                    for h in get_chat_history(user_id)]
        messages.append({"role": "user", "content": text})
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            max_tokens=250
        )
        reply = completion.choices[0].message.content

    add_message(user_id, "assistant", reply)
    msg.reply_text(reply)

@app.post("/update_rules")
async def update_rules(request: Request):
    data = await request.json()
    global rules
    rules = data
    with open("responses.json", "w") as f:
        json.dump(rules, f)
    return {"ok": True}

# To run: uvicorn script_filename:app --reload
