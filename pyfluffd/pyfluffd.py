import http.server
import json
import asyncio
import logging
from urllib.parse import urlparse, parse_qs # parse_qs might not be needed if strictly POST
from pyfluffd.pyfluff_con import PyFluffConnect
import pyfluffd.pyfluff_action as pyfluff_action

# Initialize logging
# Ensure this is only done once, typically at the application entry point.
# If other modules also call basicConfig, it might lead to unexpected behavior.
# For a simple application like this, having it here is okay.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Global state
connected_furbys = {}  # Stores PyFluffConnect instances, keyed by Furby address/UUID string
server_event_loop = None  # Will store the asyncio event loop

class FluffRequestHandler(http.server.BaseHTTPRequestHandler):
    def _send_response(self, status_code, content_type, data_bytes, extra_headers=None):
        self.send_response(status_code)
        self.send_header('Content-type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if data_bytes is not None:
            self.wfile.write(data_bytes)
        logger.debug(f"Response sent: {status_code}, Content-Type: {content_type}, Size: {len(data_bytes) if data_bytes else 0} bytes")

    def do_OPTIONS(self):
        logger.info(f"OPTIONS request received for path: {self.path}")
        self.send_response(204) # No Content
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        logger.info(f"GET request received for path: {parsed_path.path}")

        if parsed_path.path == '/list':
            logger.info("Handling /list endpoint.")
            try:
                actions_list = pyfluff_action.list_actions()
                response_data = json.dumps(actions_list).encode('utf-8')
                self._send_response(200, 'application/json', response_data)
            except Exception as e:
                logger.error(f"Error handling /list: {e}", exc_info=True)
                self._send_response(500, 'text/plain', b"Error listing actions.")
        
        elif parsed_path.path == '/scan':
            logger.info("Handling /scan endpoint.")
            if server_event_loop:
                async def _discover_devices_async():
                    logger.info("Starting Furby discovery in _discover_devices_async...")
                    try:
                        found_devices = await PyFluffConnect.discover_furbys()
                        # PyFluffConnect.discover_furbys already logs found devices
                        return found_devices 
                    except Exception as e_discover:
                        logger.error(f"Error during Furby discovery in _discover_devices_async: {e_discover}", exc_info=True)
                        return e_discover # Propagate exception to be handled by future.result()
                
                future = asyncio.run_coroutine_threadsafe(_discover_devices_async(), server_event_loop)
                try:
                    result = future.result(timeout=10.0) # Changed from future.get
                    if isinstance(result, Exception):
                        # If _discover_devices_async returned an exception
                        raise result 
                    # Assuming result is a list of BLEDevice objects
                    discovered_addresses = [d.address for d in result if hasattr(d, 'address')]
                    logger.info(f"Scan completed. Discovered addresses: {discovered_addresses}")
                    self._send_response(200, 'application/json', json.dumps({"status": "ok", "message": "Scanning completed.", "devices": discovered_addresses}).encode('utf-8'))
                except Exception as e:
                    logger.error(f"Error during scan future.result() or processing: {e}", exc_info=True)
                    self._send_response(500, 'application/json', json.dumps({"status": "error", "message": f"Scan failed or timed out: {str(e)}"}).encode('utf-8'))
            else:
                logger.error("Server event loop not available for /scan.")
                self._send_response(500, 'text/plain', b"Server error: cannot initiate scan.")

        elif parsed_path.path.startswith('/connect/'):
            logger.info(f"Handling /connect endpoint for path: {parsed_path.path}")
            if not server_event_loop:
                logger.error("Server event loop not available for /connect.")
                self._send_response(500, 'application/json', json.dumps({"status": "error", "message": "Server event loop not available"}).encode('utf-8'))
                return
            
            parts = parsed_path.path.split('/')
            if len(parts) < 3 or not parts[2]:
                logger.warning(f"Device address missing in /connect request: {parsed_path.path}")
                self._send_response(400, 'application/json', json.dumps({"status": "error", "message": "Device address missing"}).encode('utf-8'))
                return
            device_address = parts[2]
            logger.info(f"Attempting to connect to device: {device_address}")

            async def _connect_async(address):
                if address in connected_furbys and connected_furbys[address].is_connected:
                    logger.info(f"Already connected to {address}.")
                    return True, f"Already connected to {address}"
                
                logger.debug(f"Creating PyFluffConnect instance for {address}")
                fluff_conn = PyFluffConnect(address)
                is_connected_flag = await fluff_conn.connect() # connect() itself logs success/failure
                if is_connected_flag:
                    connected_furbys[address] = fluff_conn
                    # Start idle mode in the background
                    asyncio.create_task(fluff_conn.start_idle(), name=f"idle_task_{address}")
                    return True, f"Successfully connected to {address}"
                else:
                    # fluff_conn.connect() already logs error
                    return False, f"Failed to connect to {address}"

            future = asyncio.run_coroutine_threadsafe(_connect_async(device_address), server_event_loop)
            try:
                success, message = future.result(timeout=15.0) # Changed from future.get
                if success:
                    logger.info(f"Connection to {device_address} successful: {message}")
                    self._send_response(200, 'application/json', json.dumps({"status": "ok", "message": message}).encode('utf-8'))
                else:
                    logger.warning(f"Connection to {device_address} failed: {message}")
                    self._send_response(500, 'application/json', json.dumps({"status": "error", "message": message}).encode('utf-8'))
            except Exception as e:
                logger.error(f"Error during /connect for {device_address}: {e}", exc_info=True)
                self._send_response(500, 'application/json', json.dumps({"status": "error", "message": f"Connection failed: {str(e)}"}).encode('utf-8'))
        
        elif parsed_path.path.startswith('/disconnect/'):
            logger.info(f"Handling /disconnect endpoint for path: {parsed_path.path}")
            if not server_event_loop:
                logger.error("Server event loop not available for /disconnect.")
                self._send_response(500, 'application/json', json.dumps({"status": "error", "message": "Server event loop not available"}).encode('utf-8'))
                return

            parts = parsed_path.path.split('/')
            if len(parts) < 3 or not parts[2]:
                logger.warning(f"Device address missing in /disconnect request: {parsed_path.path}")
                self._send_response(400, 'application/json', json.dumps({"status": "error", "message": "Device address missing"}).encode('utf-8'))
                return
            device_address = parts[2]
            logger.info(f"Attempting to disconnect from device: {device_address}")

            async def _disconnect_async(address):
                if address in connected_furbys:
                    logger.debug(f"Found connected Furby {address} for disconnection.")
                    fluff_conn = connected_furbys[address]
                    await fluff_conn.disconnect() # disconnect() logs its actions
                    del connected_furbys[address]
                    return True, f"Disconnected from {address}"
                else:
                    logger.warning(f"Furby {address} not found in connected_furbys for disconnection.")
                    return False, f"Furby not found for disconnection: {address}"

            future = asyncio.run_coroutine_threadsafe(_disconnect_async(device_address), server_event_loop)
            try:
                success, message = future.result(timeout=10.0) # Changed from future.get
                if success:
                    logger.info(f"Disconnection from {device_address} successful: {message}")
                    self._send_response(200, 'application/json', json.dumps({"status": "ok", "message": message}).encode('utf-8'))
                else:
                    logger.warning(f"Disconnection from {device_address} indicated failure (not found): {message}")
                    self._send_response(404, 'application/json', json.dumps({"status": "error", "message": message}).encode('utf-8'))
            except Exception as e:
                logger.error(f"Error during /disconnect for {device_address}: {e}", exc_info=True)
                self._send_response(500, 'application/json', json.dumps({"status": "error", "message": f"Disconnection failed: {str(e)}"}).encode('utf-8'))
        else:
            logger.warning(f"GET request for unknown path: {parsed_path.path}")
            self._send_response(404, 'text/plain', b'Not Found')

    def do_POST(self):
        parsed_path = urlparse(self.path)
        logger.info(f"POST request received for path: {parsed_path.path}")

        if parsed_path.path.startswith('/cmd/'):
            command_name = parsed_path.path[len('/cmd/'):]
            logger.info(f"Handling /cmd endpoint for command: {command_name}")
            
            if not server_event_loop:
                logger.error("Server event loop not available for /cmd.")
                return

            try:
                content_length = int(self.headers['Content-Length'])
                post_data_raw = self.rfile.read(content_length)
                post_data = json.loads(post_data_raw.decode('utf-8'))

                params = post_data.get('params', {})
                target_uuid = post_data.get('target', None) # Can be None for broadcast

                logger.info(f"POST /cmd: Command='{command_name}', Target='{target_uuid or 'broadcast'}', Params={params}")

                async def _execute_command_async():
                    if target_uuid: # Targeted command
                        logger.info(f"Executing targeted command '{command_name}' for {target_uuid}.")
                        if target_uuid in connected_furbys and connected_furbys[target_uuid].is_connected:
                            fluff_conn = connected_furbys[target_uuid]
                            try:
                                result = await pyfluff_action.execute_action(fluff_conn, command_name, params)
                                if result: 
                                    logger.info(f"Command '{command_name}' for {target_uuid} executed successfully, result: {result}")
                                    return True, result 
                                else:
                                    logger.warning(f"Command '{command_name}' for {target_uuid} execution failed or returned False, result: {result}")
                                    return False, f"Command '{command_name}' execution failed or returned False."
                            except Exception as e_action:
                                logger.error(f"Exception during action '{command_name}' for {target_uuid}: {e_action}", exc_info=True)
                                return False, f"Error executing command '{command_name}': {str(e_action)}"
                        else:
                            logger.warning(f"Target Furby {target_uuid} for command '{command_name}' not found or not connected.")
                            return False, f"Error: Target Furby {target_uuid} not found or not connected."
                    else: # Broadcast command
                        logger.info(f"Executing broadcast command '{command_name}'.")
                        if not connected_furbys:
                            logger.warning("Broadcast command received, but no Furbys connected.")
                            return False, "Error: No Furbys connected for broadcast."
                        
                        tasks = []
                        active_targets = []
                        for uuid, fluff_conn in connected_furbys.items():
                            if fluff_conn.is_connected:
                                tasks.append(pyfluff_action.execute_action(fluff_conn, command_name, params))
                                active_targets.append(uuid)
                        
                        if not tasks:
                            logger.warning("Broadcast command received, but no Furbys actively connected.")
                            return False, "Error: No Furbys actively connected for broadcast."
                        
                        logger.info(f"Broadcasting '{command_name}' to {len(tasks)} Furbys: {active_targets}")
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        success_count = 0
                        failures = []
                        for i, res_or_exc in enumerate(results):
                            target_dev_id = active_targets[i]
                            if isinstance(res_or_exc, Exception):
                                failures.append(f"{target_dev_id}: {str(res_or_exc)}")
                                logger.error(f"Broadcast action '{command_name}' on {target_dev_id} failed: {res_or_exc}", exc_info=True)
                            elif res_or_exc:
                                success_count +=1
                                logger.debug(f"Broadcast action '{command_name}' on {target_dev_id} successful, result: {res_or_exc}")
                            else: 
                                failures.append(f"{target_dev_id}: Action returned False")
                                logger.warning(f"Broadcast action '{command_name}' on {target_dev_id} returned False, result: {res_or_exc}")

                        summary_message = f"Broadcast '{command_name}': {success_count} successful, {len(failures)} failed."
                        logger.info(summary_message)
                        if failures:
                            summary_message += " Failures: [" + "; ".join(failures) + "]"
                        
                        overall_success = success_count > 0 or (not failures and len(tasks) > 0)
                        return overall_success, summary_message
                
                logger.debug(f"Scheduling command '{command_name}' for execution.")
                future = asyncio.run_coroutine_threadsafe(_execute_command_async(), server_event_loop)
                try:
                    success, response_data = future.result(timeout=45.0) # Changed from future.get
                    if success:
                        logger.info(f"Command '{command_name}' (target: {target_uuid or 'broadcast'}) processed successfully. Response details: {response_data}")
                        self._send_response(200, 'application/json', json.dumps({"status": "ok", "details": response_data}).encode('utf-8'))
                    else:
                        logger.warning(f"Command '{command_name}' (target: {target_uuid or 'broadcast'}) failed. Response details: {response_data}")
                        status_code = 400 if "Target Furby not found" in str(response_data) or "No Furbys connected" in str(response_data) else 500
                        self._send_response(status_code, 'application/json', json.dumps({"status": "error", "message": response_data}).encode('utf-8'))
                except Exception as e_future: 
                    logger.error(f"Command '{command_name}' (target: {target_uuid or 'broadcast'}) execution future error: {e_future}", exc_info=True)
                    self._send_response(500, 'application/json', json.dumps({"status": "error", "message": f"Command timed out or failed: {str(e_future)}"}).encode('utf-8'))

            except json.JSONDecodeError:
                logger.error("Error decoding JSON from POST data.", exc_info=True)
                self._send_response(400, 'application/json', json.dumps({"status": "error", "message": "Bad Request: Invalid JSON."}).encode('utf-8'))
            except Exception as e:
                logger.error(f"Generic error processing POST request for '{command_name}': {e}", exc_info=True)
                self._send_response(500, 'application/json', json.dumps({"status": "error", "message": "Internal Server Error."}).encode('utf-8'))
        else:
            logger.warning(f"POST request for unknown path: {parsed_path.path}")
            self._send_response(404, 'text/plain', b'Not Found')

def run_server(port=3872):
    global server_event_loop
    # Create and set a new event loop for the server thread
    server_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(server_event_loop)

    httpd = None
    try:
        httpd = http.server.HTTPServer(('', port), FluffRequestHandler)
        logger.info(f"Starting Fluffd HTTP server on port {port}...")
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("HTTP server shutting down...")
    finally:
        if httpd:
            httpd.server_close()
        if server_event_loop:
            # Wait for all tasks to complete before closing loop (optional, good practice)
            # loop_tasks = asyncio.all_tasks(server_event_loop)
            # if loop_tasks:
            #    server_event_loop.run_until_complete(asyncio.gather(*loop_tasks, return_exceptions=True))
            server_event_loop.close()
            logger.info("Asyncio event loop closed.")

if __name__ == '__main__':
    run_server()
    # Conceptual:
    # For testing, one might want to auto-connect to a known Furby if server_event_loop is available
    # and add it to connected_furbys.
    # e.g.
    # async def auto_connect_test():
    #     # ... discovery ...
    #     # my_furby_addr = "XX:XX:XX:XX:XX:XX"
    #     # conn = PyFluffConnect(my_furby_addr)
    #     # if await conn.connect():
    #     #    connected_furbys[my_furby_addr] = conn
    #     #    logger.info(f"Auto-connected to test Furby: {my_furby_addr}")
    #     # else:
    #     #    logger.warning(f"Failed to auto-connect to test Furby: {my_furby_addr}")

    # if server_event_loop: # This check wouldn't work as run_server() blocks
    #    # This auto-connect logic would need to be run in a separate thread
    #    # or integrated into the server_event_loop startup if run_server was async
    #    pass
    pass
