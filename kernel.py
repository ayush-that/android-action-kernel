import os
import time
import subprocess
import json
from typing import Dict, Any, List, Optional
from openai import OpenAI
import sanitizer
from dotenv import load_dotenv

# --- CONFIGURATION ---
ADB_PATH = "adb"
MODEL = "gpt-5.2-2025-12-11"
SCREEN_DUMP_PATH = "/sdcard/window_dump.xml"
LOCAL_DUMP_PATH = "window_dump.xml"

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def escape_text_for_adb(text: str) -> str:
    text = text.replace(" ", "%s")
    text = text.replace("&", "\\&")
    text = text.replace("<", "\\<")
    text = text.replace(">", "\\>")
    text = text.replace("|", "\\|")
    text = text.replace(";", "\\;")
    text = text.replace("$", "\\$")
    text = text.replace("`", "\\`")
    text = text.replace("(", "\\(")
    text = text.replace(")", "\\)")
    text = text.replace("'", "\\'")
    text = text.replace('"', '\\"')
    return text


def run_adb_command(command: List[str]):
    result = subprocess.run([ADB_PATH] + command, capture_output=True, text=True)
    if result.stderr and "error" in result.stderr.lower():
        print(f"ADB Error: {result.stderr.strip()}")
    return result.stdout.strip()


def get_screen_state() -> str:
    run_adb_command(["shell", "uiautomator", "dump", SCREEN_DUMP_PATH])
    run_adb_command(["pull", SCREEN_DUMP_PATH, LOCAL_DUMP_PATH])

    if not os.path.exists(LOCAL_DUMP_PATH):
        return "Error: Could not capture screen."

    with open(LOCAL_DUMP_PATH, "r", encoding="utf-8") as f:
        xml_content = f.read()

    elements = sanitizer.get_interactive_elements(xml_content)
    return json.dumps(elements, indent=2)


# Android action functions
def android_tap(x: int, y: int) -> str:
    print(f"Tapping: ({x}, {y})")
    run_adb_command(["shell", "input", "tap", str(x), str(y)])
    time.sleep(0.5)
    return f"Tapped at ({x}, {y})"


def android_type(text: str, x: Optional[int] = None, y: Optional[int] = None) -> str:
    if x is not None and y is not None:
        print(f"Focusing text field at: ({x}, {y})")
        run_adb_command(["shell", "input", "tap", str(x), str(y)])
        time.sleep(0.5)

    print(f"Typing: {text}")
    escaped_text = escape_text_for_adb(text)
    run_adb_command(["shell", "input", "text", escaped_text])
    time.sleep(0.3)
    return f"Typed: {text}"


def android_home() -> str:
    print("Going Home")
    run_adb_command(["shell", "input", "keyevent", "KEYCODE_HOME"])
    time.sleep(0.5)
    return "Navigated to home screen"


def android_back() -> str:
    print("Going Back")
    run_adb_command(["shell", "input", "keyevent", "KEYCODE_BACK"])
    time.sleep(0.5)
    return "Went back"


def android_wait(seconds: float = 2.0) -> str:
    print(f"Waiting {seconds} seconds...")
    time.sleep(seconds)
    return f"Waited {seconds} seconds"


# Host-side functions
def host_read_file(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return f"File content:\n{content}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


def host_write_file(filepath: str, content: str) -> str:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} characters to {filepath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def host_run_command(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        if result.stderr:
            output += f"\nStderr: {result.stderr.strip()}"
        return output or "Command executed (no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error running command: {str(e)}"


def host_list_directory(directory: str = ".") -> str:
    try:
        items = os.listdir(directory)
        return f"Directory contents:\n" + "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def task_complete(summary: str) -> str:
    print(f"\n✓ Task Complete: {summary}")
    return "TASK_COMPLETE"


FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "android_tap",
            "description": "Tap on the Android screen at the given coordinates",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "android_type",
            "description": "Type text into the Android device. Optionally provide coordinates to focus a text field first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "x": {
                        "type": "integer",
                        "description": "X coordinate of text field (optional)",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate of text field (optional)",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "android_home",
            "description": "Navigate to the Android home screen",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "android_back",
            "description": "Press the back button on Android",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "android_wait",
            "description": "Wait for a specified number of seconds",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": "Seconds to wait",
                        "default": 2.0,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "host_read_file",
            "description": "Read a file from the host machine",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "host_write_file",
            "description": "Write content to a file on the host machine",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "host_run_command",
            "description": "Run a shell command on the host machine",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "host_list_directory",
            "description": "List contents of a directory on the host machine",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path (default: current directory)",
                        "default": ".",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Call this when the task is complete. Provide a summary of what was accomplished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was accomplished",
                    },
                },
                "required": ["summary"],
            },
        },
    },
]

FUNCTION_MAP = {
    "android_tap": android_tap,
    "android_type": android_type,
    "android_home": android_home,
    "android_back": android_back,
    "android_wait": android_wait,
    "host_read_file": host_read_file,
    "host_write_file": host_write_file,
    "host_run_command": host_run_command,
    "host_list_directory": host_list_directory,
    "task_complete": task_complete,
}


def run_agent(goal: str, max_iterations: int = 50):
    print(f"Android Agent Started. Goal: {goal}\n")

    with open("prompts/agent_system_prompt.md", "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"GOAL: {goal}"},
    ]

    for iteration in range(max_iterations):
        print(f"\n--- Iteration {iteration + 1} ---")

        screen_context = get_screen_state()
        messages.append(
            {
                "role": "user",
                "content": f"Current screen state:\n{screen_context}",
            }
        )

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=FUNCTIONS,
            tool_choice="auto",
        )

        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            if message.content:
                print(f"Agent: {message.content}")
            continue

        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            print(f"Calling: {function_name}({json.dumps(function_args, indent=2)})")

            if function_name not in FUNCTION_MAP:
                result = f"Error: Unknown function {function_name}"
            else:
                try:
                    result = FUNCTION_MAP[function_name](**function_args)
                except Exception as e:
                    result = f"Error: {str(e)}"

            if result == "TASK_COMPLETE":
                print("\n✓ Agent completed the task successfully!")
                return

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

            print(f"Result: {result[:200]}...")

        time.sleep(1)

    print(f"\n⚠ Reached maximum iterations ({max_iterations})")


if __name__ == "__main__":
    GOAL = input("Enter your goal: ")
    run_agent(GOAL)
