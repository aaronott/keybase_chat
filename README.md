# Keybase CLI Chat Client Using Textual

This project implements a full-screen, Textual-based chat client for Keybase using the Keybase CLI. It allows you to list conversations, send and receive messages in real-time, attach files, and download files directly from the command line.

I will admit that I had a lot of help from ChatGPT, it created most of this but I needed to update some of the things it couldn't figure out. The SUMMARY.md has a full output from ChatGPT so you can see what it things is happening.

## Features

- **Conversation Selection Screen:**  
  Displays your available Keybase conversations in a scrollable list. Conversations are selectable, and you can quit the application from this screen.

- **Chat Screen:**  
  Displays chat messages in a scrollable area with an input box fixed at the bottom. The application polls for new messages using Keybase’s CLI (`--since` option) every 5 seconds and immediately polls after sending a message.

- **Slash Commands:**  
  - `/help`: Show a help message.
  - `/cc [conversation]`: Change the current conversation (returns you to the conversation selection screen).
  - `/af <file_path>`: Attach a file to the current conversation (uses `keybase chat upload`).
  - `/df <file_identifier>`: Download a file from the current conversation (uses `keybase chat download`).
  - `/quit`: Quit the entire application.

- **Debug Logging:**  
  When enabled via the configuration (`"debug": true`), detailed debug logs are written to `debug.log` for troubleshooting (e.g., polling timestamps and message updates).

## Requirements

- Python 3.7+
- [Textual](https://github.com/Textualize/textual) (version 2.1.2 or later)
- Keybase CLI (installed and logged in)

## Installation

1. **Clone the Repository**

   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```



2. **Set Up a Virtual Environment (Recommended)**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**

   ```bash
    pip install -r requirements.txt
   ```

## Configuration

The application reads settings from a config.json file in the project directory. Here’s an example:

```json
{
  "debug": true,
  "max_recent": 0,
  "hide_names": [],
  "read_at_least": 10,
  "download_path": "./downloads"
}
```

* debug: Set to true to enable debug logging (logs written to debug.log).
* max_recent: Limit the number of conversations displayed (0 means no limit).
* hide_names: A list of substrings; if a conversation's display name contains any of these, it is hidden.
* read_at_least: The minimum number of messages to load when entering a conversation.
* download_path: Directory where downloaded files will be saved.

## Usage

Run the application using:

```bash
python3 keybase_chat.py
```

    * Conversation Selection:
    Use the arrow keys to select a conversation from the list. Press Enter to open it or press q to quit the application.

    * Chat Screen:
    The chat screen displays messages in a scrollable area. Type messages or slash commands (e.g., /help, /cc, /af, /df, /quit) in the input box at the bottom and press Enter.
        /quit will exit the application.
        /cc will return you to the conversation selection screen.

    New messages are polled every 5 seconds (or immediately after sending a message) to update the display.

## License

This project is licensed under the MIT License.
Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.


---


