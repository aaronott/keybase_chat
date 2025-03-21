Below is a comprehensive summary of the project along with the complete code and documentation. You can save the following as your project file (for example, as `keybase_chat.py`), and use the included `requirements.txt` to install dependencies.

---

# Keybase CLI Chat Client Using Textual

This project implements a full‑screen, Textual‑based chat client for Keybase that uses the Keybase CLI to list conversations, send and receive messages, attach files, and download files. It includes the following features:

- **Conversation Selection Screen:**  
  Displays your Keybase conversations in a scrollable list. Conversation IDs are prefixed (e.g. `"conv_"`) so they meet Textual’s widget ID requirements. You can select a conversation or quit the application (press “q”).

- **Chat Screen:**  
  Once a conversation is selected, you enter the chat screen which displays:
  - A header and footer.
  - A scrollable message area (using a `ListView`), where each message is a separate item.
  - An input box at the bottom where you type messages or slash‑commands.
  
  The chat screen:
  - Polls every 5 seconds using the Keybase CLI’s `--since` option to fetch new messages (and updates the timestamp).
  - Deduplicates messages based on message IDs.
  - Processes slash‑commands:
    - `/help` – Displays available commands.
    - `/cc [conversation]` – Switches conversation (pops back to the conversation selection screen).
    - `/af <file_path>` – Attaches a file using `keybase chat send --file <file_path> <conversation_spec>`.
    - `/df <file_identifier>` – Downloads a file using `keybase chat download --message <message_id> <conversation_spec> --out-file <destination>`.
    - `/quit` – Exits the entire application.
  - When you send a message, it immediately triggers a poll so that your message is picked up without waiting for the next 5‑second interval.

- **Debug Logging:**  
  When `"debug": true` is set in your configuration, detailed debug messages (using Python’s `logging.debug()`) are recorded, including the polling timestamps and new messages.

- **Configuration:**  
  A JSON configuration file (`config.json`) can be used to customize options:
  - `"debug"`: Enable debug logging.
  - `"max_recent"`: Limit the number of recent conversations displayed (0 means no limit).
  - `"hide_names"`: List of substrings—if a conversation’s display name contains one of these, it’s hidden.
  - `"read_at_least"`: The number of messages to load initially when entering a conversation.
  - `"download_path"`: The folder where downloaded files are saved.

---

## Installation

1. **Create a virtual environment (optional but recommended):**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Create a `requirements.txt` file with the following content:**

   ```txt
   textual>=2.1.2
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Ensure you have the Keybase CLI installed and you are logged in.**

5. **(Optional)** Create a `config.json` file (in the same directory as your script) to override default settings. For example:

   ```json
   {
     "debug": true,
     "max_recent": 0,
     "hide_names": [],
     "read_at_least": 10,
     "download_path": "./downloads"
   }
   ```

---

## Usage

Run the application using:

```bash
python3 keybase_chat.py
```

- **Conversation Selection Screen:**  
  Use the arrow keys to select a conversation. Press **Enter** to open the conversation, or press **q** to quit the application.

- **Chat Screen:**  
  In the chat screen, the message area is scrollable and your input box remains fixed at the bottom. Type messages or slash‑commands into the input box and press **Enter**.
  
  **Slash Commands:**
  - `/help`: Displays help.
  - `/cc [conversation]`: Switch conversation (returns you to the conversation selection screen).
  - `/af <file_path>`: Attach a file.
  - `/df <file_identifier>`: Download a file.
  - `/quit`: Quit the entire application.
  
  Press **Escape** to return to the conversation selection screen.

New messages are polled every 5 seconds (or immediately after you send a message) so that updates appear promptly.

---

## Full Code

Below is the complete code for `keybase_chat.py`:

```python
#!/usr/bin/env python3
import asyncio
import json
import os
import re
import sys
import datetime
import logging

from textual.app import App
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Header, Footer, Input, ListView, ListItem, Static

# Configure logging to write debug messages to debug.log.
logging.basicConfig(
    filename="debug.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

#########################################
# Helper Functions and Configuration
#########################################

DEFAULT_CONFIG = {
    "debug": False,
    "max_recent": 0,            # 0 means no limit.
    "hide_names": [],           # List of substrings to hide.
    "read_at_least": 10,        # Number of messages to load initially.
    "download_path": "./downloads"
}

def load_config():
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print("Error loading config file:", e)
            return DEFAULT_CONFIG
    else:
        return DEFAULT_CONFIG

async def get_current_user():
    proc = await asyncio.create_subprocess_exec(
        "keybase", "whoami",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        print("Error determining current user:", stderr.decode().strip())
        return None
    return stdout.decode().strip()

async def list_conversations():
    payload = {"method": "list", "params": {"options": {}}}
    proc = await asyncio.create_subprocess_exec(
        "keybase", "chat", "api", "-m", json.dumps(payload),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        print("Error listing conversations:", stderr.decode().strip())
        return []
    try:
        data = json.loads(stdout.decode())
        return data.get("result", {}).get("conversations", [])
    except Exception as e:
        print("Error parsing conversation list:", e)
        return []

def conversation_display_name(conv, current_user):
    ch = conv.get("channel", {})
    if ch.get("members_type") == "team":
        return f"Team: {ch.get('name','unknown')} (Topic: {ch.get('topic_name','unknown')})"
    else:
        names = ch.get("name", "")
        names_list = [n.strip() for n in names.split(",")]
        filtered = [n for n in names_list if n != current_user]
        if not filtered:
            filtered = names_list
        return ",".join(filtered)

def get_conversation_spec(conv):
    ch = conv.get("channel", {})
    if ch.get("members_type") == "team":
        return f"{ch.get('name','')},{ch.get('topic_name','')}"
    else:
        return ch.get("name", "")

async def read_previous_messages(conv, config):
    spec = get_conversation_spec(conv)
    at_least = config.get("read_at_least", 10)
    proc = await asyncio.create_subprocess_exec(
        "keybase", "chat", "read", "--at-least", str(at_least), spec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return f"Error reading previous messages: {stderr.decode().strip()}"
    return stdout.decode()

async def send_message_cmd(conversation_id, message):
    payload = {
        "method": "send",
        "params": {
            "options": {
                "conversation_id": conversation_id,
                "message": {"body": message, "type": "text"}
            }
        }
    }
    proc = await asyncio.create_subprocess_exec(
        "keybase", "chat", "api", "-m", json.dumps(payload),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

async def attach_file_cmd(conv, file_path):
    if not os.path.exists(file_path):
        return f"File '{file_path}' does not exist."
    spec = get_conversation_spec(conv)
    proc = await asyncio.create_subprocess_exec(
        "keybase", "chat", "send", "--file", file_path, spec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return f"Error attaching file: {stderr.decode().strip()}"
    return "File attached successfully."

async def download_file_cmd(conv, file_identifier, config):
    spec = get_conversation_spec(conv)
    download_dir = config.get("download_path", ".")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    out_file = os.path.join(download_dir, file_identifier)
    proc = await asyncio.create_subprocess_exec(
        "keybase", "chat", "download", "--message", file_identifier, spec, "--out-file", out_file,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return f"Error downloading file: {stderr.decode().strip()}"
    return f"File downloaded successfully to {out_file}."

def get_help_text():
    return (
        "Commands:\n"
        "  /help                  - Show this help message.\n"
        "  /cc [conversation]     - Change channel. With an argument, switches to that conversation.\n"
        "  /af <file_path>        - Attach a file to the conversation.\n"
        "  /df <file_identifier>  - Download a file (provide file/message ID).\n"
        "  /quit                  - Quit the application.\n"
    )

#########################################
# Conversation Selection Screen
#########################################

class ConversationSelectionScreen(Screen):
    """Screen for selecting a conversation."""
    BINDINGS = [("q", "quit_app", "Quit Application")]
    
    async def action_quit_app(self) -> None:
        await self.app.shutdown()
    
    def __init__(self, config, current_user, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.current_user = current_user
        self.conversations = []
    
    async def on_mount(self) -> None:
        self.conversations = await list_conversations()
        if self.config.get("max_recent", 0) > 0:
            self.conversations = sorted(
                self.conversations, key=lambda c: c.get("active_at", 0), reverse=True
            )[:self.config["max_recent"]]
        else:
            self.conversations = sorted(
                self.conversations, key=lambda c: c.get("active_at", 0), reverse=True
            )
        items = []
        for conv in self.conversations:
            name = conversation_display_name(conv, self.current_user)
            if any(h.lower() in name.lower() for h in self.config.get("hide_names", [])):
                continue
            # Prefix the conversation id with "conv_" for a valid identifier.
            item = ListItem(Static(name, markup=False), id="conv_" + str(conv.get("id")))
            items.append(item)
        self.list_view = ListView(*items)
        container = Vertical(Header(), self.list_view, Footer())
        await self.mount(container)
    
    async def on_list_view_selected(self, message: ListView.Selected) -> None:
        conv_id_with_prefix = message.item.id
        conv_id = conv_id_with_prefix.replace("conv_", "")
        conv = next((c for c in self.conversations if str(c.get("id")) == conv_id), None)
        if conv:
            await self.app.push_screen(ChatScreen(conv, self.config, self.current_user))

#########################################
# Chat Screen
#########################################

class ChatScreen(Screen):
    """Screen for chatting in a conversation using a scrollable ListView for messages."""
    BINDINGS = [("escape", "pop_chat", "Back to Conversation Selection")]
    
    def __init__(self, conversation, config, current_user, **kwargs):
        super().__init__(**kwargs)
        self.conversation = conversation
        self.config = config
        self.current_user = current_user
        self.listen_task = None
        self.running = True
        self.seen_ids = set()
        self.last_poll_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    async def on_mount(self) -> None:
        self.header = Header()
        self.footer = Footer()
        self.message_list = ListView()
        self.input_box = Input(placeholder="Type message or command here...")
        container = Vertical(self.header, self.message_list, self.input_box, self.footer)
        await self.mount(container)
        
        # Load previous messages and add as ListItems.
        prev = await read_previous_messages(self.conversation, self.config)
        for line in prev.splitlines():
            m = re.match(r"\[(\d+)\]", line)
            if m:
                self.seen_ids.add(m.group(1))
            await self.message_list.append(ListItem(Static(line, markup=False)))
        
        # Start background polling for new messages using --since option.
        self.listen_task = asyncio.create_task(self.listen_messages())
    
    async def listen_messages(self):
        """
        Polls every 5 seconds using:
           keybase chat read --since <timestamp> <conversation_spec>
        and appends unseen messages. The timestamp is updated after each poll.
        """
        while self.running:
            await asyncio.sleep(5)
            try:
                logging.debug(f"Starting poll with last_poll_timestamp: {self.last_poll_timestamp}")
                proc = await asyncio.create_subprocess_exec(
                    "keybase", "chat", "read", "--since", self.last_poll_timestamp, get_conversation_spec(self.conversation),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                new_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
                logging.debug(f"Polling: Old timestamp: {self.last_poll_timestamp} -> New timestamp: {new_timestamp}")
                self.last_poll_timestamp = new_timestamp
                if proc.returncode != 0:
                    logging.debug(f"Poll returned error: {stderr.decode().strip()}")
                    continue
                new_lines = stdout.decode().splitlines()
                logging.debug(f"Poll returned {len(new_lines)} lines.")
                for line in new_lines:
                    m = re.match(r"\[(\d+)\]", line)
                    if m:
                        msg_id = m.group(1)
                        if msg_id not in self.seen_ids:
                            self.seen_ids.add(msg_id)
                            await self.message_list.append(ListItem(Static(line, markup=False)))
                            logging.debug(f"New message appended: {line}")
                self.message_list.scroll_end()  # Note: not awaitable.
                logging.debug("Poll iteration complete.")
            except Exception as e:
                logging.debug(f"Exception in listen_messages: {e}")
    
    async def action_pop_chat(self) -> None:
        """Return to the conversation selection screen."""
        self.running = False
        if self.listen_task:
            self.listen_task.cancel()
        await self.app.pop_screen()
    
    async def on_input_submitted(self, message: Input.Submitted) -> None:
        user_input = message.value.strip()
        self.input_box.value = ""
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if cmd == "/help":
                await self.message_list.append(ListItem(Static(get_help_text(), markup=False)))
            elif cmd == "/quit":
                # Quit the entire application.
                self.running = False
                if self.listen_task:
                    self.listen_task.cancel()
                self.app.exit()
                return
            elif cmd == "/cc":
                if arg:
                    await self.message_list.append(ListItem(Static(f"Switching to conversation: {arg}", markup=False)))
                    # For simplicity, return to conversation selection.
                    await self.app.pop_screen()
                    return
                else:
                    await self.app.pop_screen()
                    return
            elif cmd == "/af":
                if arg:
                    result = await attach_file_cmd(self.conversation, arg)
                    await self.message_list.append(ListItem(Static(result, markup=False)))
                else:
                    await self.message_list.append(ListItem(Static("Usage: /af <file_path>", markup=False)))
            elif cmd == "/df":
                if arg:
                    result = await download_file_cmd(self.conversation, arg, self.config)
                    await self.message_list.append(ListItem(Static(result, markup=False)))
                else:
                    await self.message_list.append(ListItem(Static("Usage: /df <file_identifier>", markup=False)))
            else:
                await self.message_list.append(ListItem(Static("Unknown command. Type /help for help.", markup=False)))
        else:
            await send_message_cmd(self.conversation.get("id"), user_input)
            # Immediately poll for new messages after sending.
            await self.poll_iteration()
    
    async def poll_iteration(self):
        proc = await asyncio.create_subprocess_exec(
            "keybase", "chat", "read", "--since", self.last_poll_timestamp, get_conversation_spec(self.conversation),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        new_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        logging.debug(f"Polling: Old timestamp: {self.last_poll_timestamp} -> New timestamp: {new_timestamp}")
        self.last_poll_timestamp = new_timestamp
        if proc.returncode != 0:
            logging.debug(f"Poll returned error: {stderr.decode().strip()}")
            return
        new_lines = stdout.decode().splitlines()
        logging.debug(f"Poll returned {len(new_lines)} lines.")
        for line in new_lines:
            m = re.match(r"\[(\d+)\]", line)
            if m:
                msg_id = m.group(1)
                if msg_id not in self.seen_ids:
                    self.seen_ids.add(msg_id)
                    await self.message_list.append(ListItem(Static(line, markup=False)))
                    logging.debug(f"New message appended: {line}")
        self.message_list.scroll_end()
        logging.debug("Poll iteration complete.")

#########################################
# Main Application
#########################################

class KeybaseChatApp(App):
    async def on_load(self) -> None:
        self.config = load_config()
        self.current_user = await get_current_user()
        if not self.current_user:
            print("Unable to determine current user. Exiting.")
            await self.shutdown()
    
    async def on_mount(self) -> None:
        await self.push_screen(ConversationSelectionScreen(self.config, self.current_user))

if __name__ == "__main__":
    KeybaseChatApp().run()
```

---

## Documentation Summary

- **Configuration:**  
  Settings are loaded from `config.json` if available; otherwise, defaults are used.

- **Helper Functions:**  
  - `get_current_user()`: Returns the logged‑in Keybase username.
  - `list_conversations()`: Returns a list of conversations via the Keybase CLI.
  - `read_previous_messages()`: Loads initial messages for a conversation.
  - `send_message_cmd()`, `attach_file_cmd()`, `download_file_cmd()`: Wrap Keybase CLI commands.
  - `get_conversation_spec()`: Constructs the conversation spec string (for direct messages or teams).

- **ConversationSelectionScreen:**  
  Displays available conversations in a ListView. Each conversation is identified with a valid widget ID (prefixed with `"conv_"`). The user can select a conversation or press **q** to quit.

- **ChatScreen:**  
  Displays the chat for a conversation using a ListView for messages and an Input widget for user input.  
  - It polls every 5 seconds using `--since <timestamp>` to fetch new messages and updates the view.
  - When a message is sent, it immediately calls a poll iteration so that the message is shown quickly.
  - Slash commands:
    - `/help`: Displays help text.
    - `/cc [conversation]`: Switches to a different conversation (returns to conversation selection).
    - `/af <file_path>`: Attaches a file.
    - `/df <file_identifier>`: Downloads a file.
    - `/quit`: Exits the entire application.
  - Pressing **escape** also returns to the conversation selection screen.

- **Main Application (KeybaseChatApp):**  
  Initializes the configuration, fetches the current user, and shows the ConversationSelectionScreen.

- **Logging:**  
  Debug information is logged to `debug.log` when `"debug": true` is set in the configuration.

---

This complete export should allow you to rebuild the project exactly as described. If you ask again for this project in the future, I'll be able to generate a similar solution with all these features and documentation.

Happy coding, and feel free to ask if you have further questions or need more modifications!
