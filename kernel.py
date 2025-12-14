import os
import time
import subprocess
import json
import inspect
from typing import Dict, Any, List, Optional, Callable, Union, get_origin, get_args
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


class FunctionRegistry:
    def __init__(self):
        self.functions: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    def _get_type_schema(self, annotation: Any) -> Dict[str, Any]:
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            non_none_args = [arg for arg in args if arg is not type(None)]
            if non_none_args:
                return self._get_type_schema(non_none_args[0])

        if annotation == str:
            return {"type": "string"}
        elif annotation == int:
            return {"type": "integer"}
        elif annotation == float:
            return {"type": "number"}
        elif annotation == bool:
            return {"type": "boolean"}
        else:
            return {"type": "string"}

    def _generate_schema(self, func: Callable, description: str) -> Dict[str, Any]:
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = (
                param.annotation if param.annotation != inspect.Parameter.empty else str
            )
            param_desc = param_name.replace("_", " ").title()

            prop_schema = self._get_type_schema(param_type)
            prop_schema["description"] = param_desc

            if param.default != inspect.Parameter.empty:
                prop_schema["default"] = param.default
            else:
                origin = get_origin(param_type)
                if origin is not Union or type(None) not in get_args(param_type):
                    required.append(param_name)

            properties[param_name] = prop_schema

        params_schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            params_schema["required"] = required

        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": params_schema,
            },
        }

    def register(self, description: str):
        def decorator(func: Callable):
            self.functions[func.__name__] = func
            schema = self._generate_schema(func, description)
            self.schemas.append(schema)
            return func

        return decorator

    def get_functions(self) -> List[Dict[str, Any]]:
        return self.schemas

    def get_function_map(self) -> Dict[str, Callable]:
        return self.functions


registry = FunctionRegistry()


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
@registry.register("Tap on the Android screen at the given coordinates")
def android_tap(x: int, y: int) -> str:
    print(f"Tapping: ({x}, {y})")
    run_adb_command(["shell", "input", "tap", str(x), str(y)])
    time.sleep(0.5)
    return f"Tapped at ({x}, {y})"


@registry.register(
    "Type text into the Android device. Optionally provide coordinates to focus a text field first."
)
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


@registry.register("Navigate to the Android home screen")
def android_home() -> str:
    print("Going Home")
    run_adb_command(["shell", "input", "keyevent", "KEYCODE_HOME"])
    time.sleep(0.5)
    return "Navigated to home screen"


@registry.register("Press the back button on Android")
def android_back() -> str:
    print("Going Back")
    run_adb_command(["shell", "input", "keyevent", "KEYCODE_BACK"])
    time.sleep(0.5)
    return "Went back"


@registry.register("Swipe on the Android screen from start coordinates to end coordinates")
def android_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    print(f"Swiping from ({x1}, {y1}) to ({x2}, {y2})")
    run_adb_command(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
    time.sleep(0.5)
    return f"Swiped from ({x1}, {y1}) to ({x2}, {y2})"


@registry.register("Wait for a specified number of seconds")
def android_wait(seconds: float = 2.0) -> str:
    print(f"Waiting {seconds} seconds...")
    time.sleep(seconds)
    return f"Waited {seconds} seconds"


# Host-side functions
@registry.register("Read a file from the host machine")
def host_read_file(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return f"File content:\n{content}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


@registry.register("Write content to a file on the host machine")
def host_write_file(filepath: str, content: str) -> str:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} characters to {filepath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@registry.register("Run a shell command on the host machine")
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


@registry.register("List contents of a directory on the host machine")
def host_list_directory(directory: str = ".") -> str:
    try:
        items = os.listdir(directory)
        return f"Directory contents:\n" + "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {str(e)}"


@registry.register(
    "Call this when the task is complete. Provide a summary of what was accomplished."
)
def task_complete(summary: str) -> str:
    print(f"\n✓ Task Complete: {summary}")
    return "TASK_COMPLETE"


FUNCTIONS = registry.get_functions()
FUNCTION_MAP = registry.get_function_map()


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
