#!/usr/bin/env python3
import asyncio
import json
import os
import re
import sys
import datetime

from textual.app import App
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Header, Footer, Input, ListView, ListItem, Static

import logging
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
        "keybase", "chat", "upload", spec, file_path,
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
        "keybase", "chat", "download", spec, file_identifier, "--outfile", out_file,
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

        # Set focus to the input box (no await needed)
        self.set_focus(self.input_box)

        # Load previous messages and add as ListItems.
        prev = await read_previous_messages(self.conversation, self.config)
        for line in prev.splitlines():
            m = re.match(r"\[(\d+)\]", line)
            if m:
                self.seen_ids.add(m.group(1))
            await self.message_list.append(ListItem(Static(line, markup=False)))

        # Start background polling for new messages using --since option.
        self.listen_task = asyncio.create_task(self.listen_messages())


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
        self.message_list.scroll_end()  # Removed 'await' here.
        logging.debug("Poll iteration complete.")

    async def listen_messages(self):
        while self.running:
            await asyncio.sleep(5)
            try:
                await self.poll_iteration()
            except Exception as e:
                logging.debug(f"Exception in listen_messages: {e}")

    async def action_pop_chat(self) -> None:
        """Return to the conversation selection screen."""
        self.running = False
        if self.listen_task:
            self.listen_task.cancel()
        await self.app.pop_screen()

    async def action_quit_app(self) -> None:
        """Exit the entire application."""
        self.running = False
        if self.listen_task:
            self.listen_task.cancel()
        self.app.exit()

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
                await self.action_quit_app()
                return
            elif cmd == "/cc":
                if arg:
                    await self.message_list.append(ListItem(Static(f"Switching to conversation: {arg}", markup=False)))
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
            # Immediately poll for new messages after sending a message.
            await self.poll_iteration()

    
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

