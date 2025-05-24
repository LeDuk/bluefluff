import logging
import asyncio # For sleep, TimeoutError
import os # For path operations in flash_dlc
from pyfluffd.pyfluff_con import PyFluffConnect, BleakError, TimeoutError as FluffTimeoutError

# Ensure logger is defined (it should be, as per instructions)
# This check is more for robustness if this file were used in isolation without pyfluffd.py setting up basicConfig
if not logging.getLogger(__name__).hasHandlers():
    logging.basicConfig(level=logging.DEBUG) # Default to DEBUG if no handlers for this logger's lineage
logger = logging.getLogger(__name__)


# Action functions
async def antenna(fluff_conn: PyFluffConnect, params: dict):
    """Sets the color of the Furby's antenna."""
    logger.info(f"Action 'antenna' called with params: {params}")
    try:
        red = int(params.get("red", 0))
        green = int(params.get("green", 0))
        blue = int(params.get("blue", 0))
        command_bytes = bytes([0x14, red, green, blue])
        logger.debug(f"Antenna action: Sending command {command_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info("Antenna action successful.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Antenna action: Invalid parameters {params}. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in antenna action: {e}", exc_info=True)
        return False

async def debug_screen(fluff_conn: PyFluffConnect, params: dict):
    """Cycles through the LCD eye debug menus."""
    logger.info(f"Action 'debug_screen' called with params: {params}")
    try:
        command_bytes = bytes([0xdb])
        logger.debug(f"Debug screen action: Sending command {command_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info("Debug screen action successful.")
        return True
    except Exception as e:
        logger.error(f"Error in debug_screen action: {e}", exc_info=True)
        return False

async def lcd_light(fluff_conn: PyFluffConnect, params: dict):
    """Sets the LCD Eyes Background Light."""
    logger.info(f"Action 'lcd_light' called with params: {params}")
    try:
        state = int(params.get("state", 0))
        command_bytes = bytes([0xcd, state])
        logger.debug(f"LCD light action: Sending command {command_bytes.hex()} with state {state} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info(f"LCD light action successful (state: {state}).")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"LCD light action: Invalid parameters {params}. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in lcd_light action: {e}", exc_info=True)
        return False

async def action(fluff_conn: PyFluffConnect, params: dict):
    """Furby move / talk action."""
    logger.info(f"Action 'action' called with params: {params}")
    try:
        input_val = int(params.get("input", 0))
        index_val = int(params.get("index", 0))
        subindex_val = int(params.get("subindex", 0))
        specific_val = int(params.get("specific", 0))
        command_bytes = bytes([0x13, 0x00, input_val, index_val, subindex_val, specific_val])
        logger.debug(f"Action 'action': Sending command {command_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info("Action 'action' successful.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Action 'action': Invalid parameters {params}. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in 'action': {e}", exc_info=True)
        return False

async def set_name(fluff_conn: PyFluffConnect, params: dict):
    """Set new Name and announce it."""
    logger.info(f"Action 'set_name' called with params: {params}")
    try:
        name_val = int(params.get("name", 0))
        if not (0 <= name_val <= 128):
            logger.warning(f"Set_name action: Invalid name value: {name_val}. Must be 0-128.")
            return False

        command1_bytes = bytes([0x21, name_val])
        command2_bytes = bytes([0x13, 0x00, 0x21, 0x00, 0x00, name_val])

        logger.debug(f"Set_name action: Sending command1 {command1_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command1_bytes)
        # await asyncio.sleep(0.1) # Consider if delay is needed; if so, log it.
        logger.debug(f"Set_name action: Sending command2 {command2_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command2_bytes)
        logger.info(f"Set_name action successful for name_val: {name_val}.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Set_name action: Invalid parameters {params}. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in set_name action: {e}", exc_info=True)
        return False

async def custom_command(fluff_conn: PyFluffConnect, params: dict):
    """Send arbitrary command to GeneralPlus."""
    logger.info(f"Action 'custom_command' called with params: {params}")
    try:
        cmd_hex = params.get("cmd")
        if not cmd_hex:
            logger.warning("Custom_command action: Missing 'cmd' parameter.")
            return False
        command_bytes = bytes.fromhex(cmd_hex)
        logger.debug(f"Custom_command action: Sending command {command_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info(f"Custom_command action successful for cmd: {cmd_hex}.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Custom_command action: Invalid 'cmd' parameter '{params.get('cmd')}'. Must be valid hex. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in custom_command: {e}", exc_info=True)
        return False

async def set_idle(fluff_conn: PyFluffConnect, params: dict):
    """Enable or disable keeping Furby quiet."""
    logger.info(f"Action 'set_idle' called with params: {params}")
    try:
        idle_flag = int(params.get("idle", -1)) # Default to invalid if not provided
        if idle_flag == 1:
            logger.info("Set_idle action: Enabling idle mode.")
            fluff_conn.start_idle() # start_idle has its own logging
        elif idle_flag == 0:
            logger.info("Set_idle action: Disabling idle mode.")
            await fluff_conn.stop_idle() # stop_idle has its own logging
        else:
            logger.warning(f"Set_idle action: Invalid 'idle' parameter value: {params.get('idle')}. Must be 0 or 1.")
            return False
        logger.info(f"Set_idle action successful (idle_flag: {idle_flag}).")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Set_idle action: Invalid 'idle' parameter type. Must be an integer 0 or 1. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in set_idle action: {e}", exc_info=True)
        return False

async def mood_meter(fluff_conn: PyFluffConnect, params: dict):
    """Set Moodmeter value."""
    logger.info(f"Action 'mood_meter' called with params: {params}")
    try:
        action_val = int(params.get("action", 0))
        type_val = int(params.get("type", 0))
        value_val = int(params.get("value", 0))
        command_bytes = bytes([0x23, action_val, type_val, value_val])
        logger.debug(f"Mood_meter action: Sending command {command_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info("Mood_meter action successful.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Mood_meter action: Invalid parameters {params}. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in mood_meter action: {e}", exc_info=True)
        return False

# Nordic Actions
async def nordic_custom(fluff_conn: PyFluffConnect, params: dict):
    """Send arbitrary command to Nordic."""
    logger.info(f"Action 'nordic_custom' called with params: {params}")
    try:
        cmd_hex = params.get("cmd")
        if not cmd_hex:
            logger.warning("Nordic_custom action: Missing 'cmd' parameter.")
            return False
        command_bytes = bytes.fromhex(cmd_hex)
        logger.debug(f"Nordic_custom action: Sending command {command_bytes.hex()} to nordic_write.")
        await fluff_conn.nordic_write(command_bytes)
        logger.info(f"Nordic_custom action successful for cmd: {cmd_hex}.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Nordic_custom action: Invalid 'cmd' parameter '{params.get('cmd')}'. Must be valid hex. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in nordic_custom: {e}", exc_info=True)
        return False

async def nordic_packet_ack(fluff_conn: PyFluffConnect, params: dict):
    """Enable / disable nordic packet ACK messages for file writing."""
    logger.info(f"Action 'nordic_packet_ack' called with params: {params}")
    try:
        state = int(params.get("state", -1)) 
        if state not in [0, 1]:
            logger.warning(f"Nordic_packet_ack action: Invalid 'state' parameter: {state}. Must be 0 or 1.")
            return False
        command_bytes = bytes([0x09, state, 0x00])
        logger.debug(f"Nordic_packet_ack action: Sending command {command_bytes.hex()} with state {state} to nordic_write.")
        await fluff_conn.nordic_write(command_bytes)
        logger.info(f"Nordic_packet_ack action successful (state: {state}).")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Nordic_packet_ack action: Invalid 'state' parameter type. Must be an integer 0 or 1. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in nordic_packet_ack: {e}", exc_info=True)
        return False

# DLC-related Actions
async def dlc_delete(fluff_conn: PyFluffConnect, params: dict):
    """Delete DLC from slot with ID."""
    logger.info(f"Action 'dlc_delete' called with params: {params}")
    try:
        slot = int(params.get("slot", -1)) 
        if not (0 <= slot <= 255) : 
             logger.warning(f"Dlc_delete action: Invalid 'slot' parameter: {slot}. Must be 0-255.")
             return False
        command_bytes = bytes([0x74, slot])
        logger.debug(f"Dlc_delete action: Sending command {command_bytes.hex()} for slot {slot} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info(f"Dlc_delete action successful for slot: {slot}.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Dlc_delete action: Invalid 'slot' parameter type. Must be an integer. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in dlc_delete: {e}", exc_info=True)
        return False

async def flash_dlc(fluff_conn: PyFluffConnect, params: dict):
    """Flash DLC file to slot on Furby."""
    filename = params.get("filename")
    dlcfile_path = params.get("dlcfile_path")
    logger.info(f"Action 'flash_dlc' called with filename: '{filename}', dlcfile_path: '{dlcfile_path}'")

    if not filename or not dlcfile_path:
        logger.warning("Flash_dlc action: Missing 'filename' or 'dlcfile_path'.")
        return False

    try:
        logger.info(f"Flash_dlc: Attempting to read DLC file from path: {dlcfile_path}")
        with open(dlcfile_path, 'rb') as f:
            dlc_content = f.read()
        dlc_size = len(dlc_content)
        logger.info(f"Flash_dlc: Successfully read DLC file '{dlcfile_path}', size: {dlc_size} bytes")

        buf_cmd = bytes([0x50, 0x00])
        buf_size = bytes([dlc_size >> 16 & 0xff, dlc_size >> 8 & 0xff, dlc_size & 0xff])
        buf_slot = bytes([0x02]) 
        encoded_filename = filename.encode('ascii', 'ignore')[:32] 
        buf_filename = encoded_filename
        buf_end = bytes([0x00, 0x00]) 
        cmd_prepare = buf_cmd + buf_size + buf_slot + buf_filename + buf_end
        
        logger.debug(f"Flash_dlc: Sending DLC prepare command {cmd_prepare.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(cmd_prepare)

        logger.info("Flash_dlc: Waiting for 'ready to receive' notification (0x2402)...")
        notification_received = await fluff_conn.wait_for_gp_notification(
            lambda data: data and len(data) >= 2 and data[0] == 0x24 and data[1] == 0x02,
            timeout=15.0 
        ) # wait_for_gp_notification logs success/timeout

        if notification_received: # This check is somewhat redundant due to wait_for_gp_notification raising on timeout
            logger.info(f"Flash_dlc: Received 'ready to receive' signal. Sending DLC content for '{filename}'...")
            chunk_size = 20
            for i in range(0, dlc_size, chunk_size):
                piece = dlc_content[i:i + chunk_size]
                logger.debug(f"Flash_dlc: Writing DLC chunk {i // chunk_size + 1}/{(dlc_size + chunk_size -1) // chunk_size} ({len(piece)} bytes) for '{filename}'.")
                await fluff_conn.file_write(piece) # file_write has its own logging
                await asyncio.sleep(0.005) 
            logger.info(f"Flash_dlc: DLC content for '{filename}' successfully sent.")
            return True
        else:
            # Should not be reached if wait_for_gp_notification raises TimeoutError as expected
            logger.error(f"Flash_dlc: Did not receive 'ready to receive' signal for '{filename}' (this path should ideally not be reached).")
            return False

    except FileNotFoundError:
        logger.error(f"Flash_dlc action: DLC file not found at path: {dlcfile_path}", exc_info=True)
        return False
    except FluffTimeoutError: 
        logger.error(f"Flash_dlc action: Timeout waiting for 'ready to receive' (0x2402) notification for '{filename}'.", exc_info=True)
        return False
    except BleakError as e: 
        logger.error(f"Flash_dlc action: BleakError during DLC flash for '{filename}': {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Flash_dlc action: Error during flash_dlc for '{filename}': {e}", exc_info=True)
        return False


async def dlc_load(fluff_conn: PyFluffConnect, params: dict):
    """Load DLC for activation."""
    logger.info(f"Action 'dlc_load' called with params: {params}")
    try:
        slot = int(params.get("slot", -1))
        if not (0 <= slot <= 255):
            logger.warning(f"Dlc_load action: Invalid 'slot' parameter: {slot}. Must be 0-255.")
            return False
        command_bytes = bytes([0x60, slot])
        logger.debug(f"Dlc_load action: Sending command {command_bytes.hex()} for slot {slot} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info(f"Dlc_load action successful for slot: {slot}.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Dlc_load action: Invalid 'slot' parameter type. Must be an integer. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in dlc_load action: {e}", exc_info=True)
        return False

async def dlc_activate(fluff_conn: PyFluffConnect, params: dict):
    """Activate loaded DLC - use after 'Load DLC'."""
    logger.info(f"Action 'dlc_activate' called with params: {params}")
    try:
        command_bytes = bytes([0x61])
        logger.debug(f"Dlc_activate action: Sending command {command_bytes.hex()} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info("Dlc_activate action successful.")
        return True
    except Exception as e:
        logger.error(f"Error in dlc_activate action: {e}", exc_info=True)
        return False

async def dlc_deactivate(fluff_conn: PyFluffConnect, params: dict):
    """Deactivate DLC slot without deleting it."""
    logger.info(f"Action 'dlc_deactivate' called with params: {params}")
    try:
        slot = int(params.get("slot", -1))
        if not (0 <= slot <= 255):
            logger.warning(f"Dlc_deactivate action: Invalid 'slot' parameter: {slot}. Must be 0-255.")
            return False
        command_bytes = bytes([0x62, slot])
        logger.debug(f"Dlc_deactivate action: Sending command {command_bytes.hex()} for slot {slot} to general_plus_write.")
        await fluff_conn.general_plus_write(command_bytes)
        logger.info(f"Dlc_deactivate action successful for slot: {slot}.")
        return True
    except (ValueError, TypeError) as e:
        logger.warning(f"Dlc_deactivate action: Invalid 'slot' parameter type. Must be an integer. Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Error in dlc_deactivate action: {e}", exc_info=True)
        return False

# COMMANDS dictionary
COMMANDS = {
    "antenna": {
        "function": antenna,
        "readable": "Antenna Color",
        "description": "Set Antenna Color",
        "params": {
            "red": "Brightness of red antenna LED (0-255)",
            "green": "Brightness of green antenna LED (0-255)",
            "blue": "Brightness of blue antenna LED (0-255)",
        }
    },
    "debug": {
        "function": debug_screen,
        "readable": "Debug Screen",
        "description": "Cycle through LCD eye debug menus",
        "params": {}
    },
    "lcd": {
        "function": lcd_light,
        "readable": "LCD Light",
        "description": "Set LCD Eyes Background Light",
        "params": {
            "state": "0 for off, 1 for on"
        }
    },
    "action": {
        "function": action,
        "readable": "Furby Action",
        "description": "Furby move / talk action",
        "params": {
            "input": "Where to find the action (integer)",
            "index": "Index of actions (integer)",
            "subindex": "Subindex of action (integer)",
            "specific": "Specific action (integer)"
        }
    },
    "set_name": {
        "function": set_name,
        "readable": "Set Name",
        "description": "Set new Name and announce it",
        "params": {
            "name": "New name, value from 0-128 (integer)"
        }
    },
    "custom_command": {
        "function": custom_command,
        "readable": "Custom Command",
        "description": "Send arbitrary command to GeneralPlus",
        "params": {
            "cmd": "Command in hexadecimal format (string)"
        }
    },
    "set_idle": {
        "function": set_idle,
        "readable": "Set Idle Mode",
        "description": "Enable or disable keeping Furby quiet",
        "params": {
            "idle": "1 = keep quiet (idle), 0 = don't idle (integer)"
        }
    },
    "mood_meter": {
        "function": mood_meter,
        "readable": "Set Mood Meter",
        "description": "Set Moodmeter value",
        "params": {
            "action": "1 = set value, 0 = increase value (integer)",
            "type": "0 = Excited, 1 = Displeased, 2 = Tired, 3 = Fullness, 4 = Wellness (integer)",
            "value": "New value (action 1) or delta (action 0) (integer)"
        }
    },
    # Nordic Actions
    "nordic_custom": {
        "function": nordic_custom,
        "readable": "Nordic Custom Command",
        "description": "Send arbitrary command to Nordic",
        "params": {"cmd": "Command in hexadecimal format (string)"}
    },
    "nordic_packet_ack": {
        "function": nordic_packet_ack,
        "readable": "Nordic Packet ACK",
        "description": "Enable / disable nordic packet ACK messages for file writing",
        "params": {"state": "0 for off, 1 for on (integer)"}
    },
    # DLC-related Actions
    "dlc_delete": {
        "function": dlc_delete,
        "readable": "Delete DLC",
        "description": "Delete DLC from slot with ID",
        "params": {"slot": "Slot to be deleted (integer, 0-255)"}
    },
    "flash_dlc": {
        "function": flash_dlc,
        "readable": "Flash DLC",
        "description": "Flash DLC file to slot on Furby",
        "params": {
            "filename": "DLC filename (e.g., TU003410.DLC) (string)",
            "dlcfile_path": "Path to DLC file on server (string)"
        }
    },
    "dlc_load": {
        "function": dlc_load,
        "readable": "Load DLC",
        "description": "Load DLC for activation",
        "params": {"slot": "DLC slot to be loaded (integer, 0-255)"}
    },
    "dlc_activate": {
        "function": dlc_activate,
        "readable": "Activate DLC",
        "description": "Activate loaded DLC - use after 'Load DLC'",
        "params": {}
    },
    "dlc_deactivate": {
        "function": dlc_deactivate,
        "readable": "Deactivate DLC",
        "description": "Deactivate DLC slot without deleting it",
        "params": {"slot": "DLC slot to be deactivated (integer, 0-255)"}
    },
    # Other category for preprogrammed buttons
    "other": {
        "function": None, # Not directly callable, acts as a category
        "readable": "Preprogrammed Actions",
        "description": "Furby move / talk buttons",
        "buttons": {
            "giggle": {
                "readable": "Giggle",
                "cmd": "action", # Target command name
                "params": {"input": 55, "index": 2, "subindex": 14, "specific": 0}
            },
            "puke": {
                "readable": "Puke",
                "cmd": "action",
                "params": {"input": 56, "index": 3, "subindex": 15, "specific": 1}
            },
            "say_example_name": { # Renamed from "name" to avoid conflict
                "readable": "Say a Name (Example)",
                "cmd": "set_name",
                "params": {"name": 3} # Example name index
            },
            "antennaoff": {
                "readable": "Turn Antenna LED Off",
                "cmd": "antenna",
                "params": {"red": 0, "blue": 0, "green": 0}
            },
            "antennared": {
                "readable": "Antenna LED Red",
                "cmd": "antenna",
                "params": {"red": 255, "blue": 0, "green": 0}
            },
            "antennablue": {
                "readable": "Antenna LED Blue",
                "cmd": "antenna",
                "params": {"red": 0, "blue": 255, "green": 0}
            },
            "antennagreen": {
                "readable": "Antenna LED Green",
                "cmd": "antenna",
                "params": {"red": 0, "blue": 0, "green": 255}
            },
        }
    }
}

async def execute_action(fluff_conn: PyFluffConnect, command_name: str, params: dict):
    """Executes a given command by name, potentially handling 'category/button' paths."""
    logger.debug(f"Attempting to execute action: {command_name} with params: {params}")

    # Check for direct command_name match
    if command_name in COMMANDS:
        action_details = COMMANDS[command_name]
        action_function = action_details.get("function")

        if action_function is not None:
            logger.info(f"Executing direct action: {command_name} with params: {params}")
            try:
                result = await action_function(fluff_conn, params)
                return result
            except Exception as e:
                logger.error(f"Exception during execution of direct action {command_name}: {e}", exc_info=True)
                return False
        elif action_details.get("buttons") is not None:
            # User tried to execute a category directly
            logger.error(f"Cannot execute category '{command_name}' directly. Specify a button (e.g., '{command_name}/button_name').")
            return False
        else:
            # Command is in COMMANDS but has no function and no buttons (should not happen with current structure)
            logger.error(f"Command '{command_name}' is defined but has no executable function or buttons.")
            return False

    # Check for "category/button" path
    parts = command_name.split('/', 1)
    if len(parts) == 2:
        category_name, button_name = parts
        logger.debug(f"Interpreting as category/button: {category_name}/{button_name}")
        if category_name in COMMANDS and "buttons" in COMMANDS[category_name]:
            category_buttons = COMMANDS[category_name]["buttons"]
            if button_name in category_buttons:
                target_cmd_details = category_buttons[button_name]
                target_cmd_name = target_cmd_details["cmd"]
                target_cmd_params = target_cmd_details["params"]
                logger.info(f"Executing button '{button_name}' from category '{category_name}' "
                            f"as target command '{target_cmd_name}' with params {target_cmd_params}")
                # Recursive call to execute the target command
                return await execute_action(fluff_conn, target_cmd_name, target_cmd_params)
            else:
                logger.error(f"Button '{button_name}' not found in category '{category_name}'.")
                return False
        else:
            # Category itself not found, or it doesn't define buttons
            logger.debug(f"Category '{category_name}' not found or does not contain buttons.")
            # Fall through to general "Command not found"
    
    logger.warning(f"Command '{command_name}' not found (or category/button path invalid).")
    return False

def list_actions():
    """Returns a list of available actions, suitable for JSON serialization."""
    actions_copy = {}
    for cmd_name, details in COMMANDS.items():
        actions_copy[cmd_name] = {
            key: value for key, value in details.items() if key != "function"
        }
    return actions_copy

if __name__ == '__main__':
    # Basic test for list_actions
    logging.basicConfig(level=logging.INFO)
    logger.info("Available actions:")
    import json
    print(json.dumps(list_actions(), indent=2))

    # To test execute_action, you would need a mock or real PyFluffConnect instance
    # and an event loop.
    # Example (conceptual, requires more setup to run):
    # async def test_execution():
    #     class MockFluffConnect:
    #         async def general_plus_write(self, data: bytes):
    #             logger.info(f"MockFluffConnect: general_plus_write called with {data.hex()}")
    #             # Simulate success, or raise an exception to test error handling
    #             return True # Or False, or raise an error
    #
    #     mock_conn = MockFluffConnect()
    #     logger.info("Testing 'antenna' action...")
    #     result = await execute_action(mock_conn, "antenna", {"red": 255, "green": 100, "blue": 50})
    #     logger.info(f"'antenna' action result: {result}")
    #
    #     logger.info("Testing 'debug' action...")
    #     result = await execute_action(mock_conn, "debug", {})
    #     logger.info(f"'debug' action result: {result}")
    #
    #     logger.info("Testing 'lcd' action with state 1...")
    #     result = await execute_action(mock_conn, "lcd", {"state": 1})
    #     logger.info(f"'lcd' action result: {result}")
    #
    #     logger.info("Testing non-existent action...")
    #     result = await execute_action(mock_conn, "non_existent_action", {})
    #     logger.info(f"'non_existent_action' action result: {result}")

    # if __name__ == '__main__':
    #    asyncio.run(test_execution()) # Needs asyncio import for this part
    pass
