import asyncio
import logging
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from asyncio import Future, TimeoutError

# Configure basic logging - This should ideally be done at the application entry point (e.g., in pyfluffd.py)
# For a library module, it's better not to configure global logging here.
# However, to ensure logger works if this module is used standalone for testing,
# we might add a handler if no handlers are configured.
logger = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers(): # Check if root logger has handlers
    logging.basicConfig(level=logging.DEBUG) # Default to DEBUG for standalone testing

bleak_logger = logging.getLogger('bleak')
bleak_logger.setLevel(logging.WARNING)

# GATT Service and Characteristic UUIDs
SERVICE_FLUFF = "dab91435b5a1e29cb041bcd562613bde"
_CHAR_GENERALPLUS_WRITE = "dab91383b5a1e29cb041bcd562613bde"
_CHAR_GENERALPLUS_LISTEN = "dab91382b5a1e29cb041bcd562613bde"
_CHAR_NORDIC_WRITE = "dab90757b5a1e29cb041bcd562613bde"
_CHAR_NORDIC_LISTEN = "dab90756b5a1e29cb041bcd562613bde"
_CHAR_RSSI_LISTEN = "dab90755b5a1e29cb041bcd562613bde" # This will be removed based on instructions
_CHAR_FILEWRITE = "dab90758b5a1e29cb041bcd562613bde"

FURBY_CHARACTERISTICS = {
    "SERVICE_FLUFF": SERVICE_FLUFF,
    "CHAR_GENERALPLUS_WRITE": _CHAR_GENERALPLUS_WRITE,
    "CHAR_GENERALPLUS_LISTEN": _CHAR_GENERALPLUS_LISTEN,
    "CHAR_NORDIC_WRITE": _CHAR_NORDIC_WRITE,
    "CHAR_NORDIC_LISTEN": _CHAR_NORDIC_LISTEN,
    "CHAR_FILEWRITE": _CHAR_FILEWRITE,
    # CHAR_RSSI_LISTEN is intentionally omitted as it's being removed
}

class PyFluffConnect:
    @staticmethod
    async def discover_furbys(timeout=5.0):
        """Scans for BLE devices and returns a list of found Furbys."""
        found_furbys = []
        logger.info(f"Starting BLE scan for Furbys (timeout: {timeout}s)...")
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            for device in devices:
                if device.name and "Furby" in device.name:
                    logger.info(f"Found Furby: Name='{device.name}', Address='{device.address}'")
                    found_furbys.append(device)
                else:
                    logger.debug(f"Found other BLE device: Name='{device.name}', Address='{device.address}'")
        except BleakError as e:
            logger.error(f"BleakError during BLE scan: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred during BLE scan: {e}", exc_info=True)
        
        if not found_furbys:
            logger.info("BLE scan finished: No Furbys found.")
        else:
            logger.info(f"BLE scan finished: Found {len(found_furbys)} Furby(s).")
        return found_furbys

    def __init__(self, address_or_bledevice=None):
        if isinstance(address_or_bledevice, str):
            self.address = address_or_bledevice
            logger.debug(f"PyFluffConnect initialized with address: {self.address}")
        elif hasattr(address_or_bledevice, 'address'): # Assuming it's a BLEDevice
            self.address = address_or_bledevice.address
            logger.debug(f"PyFluffConnect initialized with BLEDevice: {self.address} (Name: {address_or_bledevice.name})")
        else:
            self.address = None # Or raise error
            logger.debug(f"PyFluffConnect initialized without specific address/device.")

        self.client = None
        self.gp_listen_callback = None
        self.nordic_listen_callback = None
        self.idle_interval = None
        self.one_time_gp_callbacks = {} # For wait_for_gp_notification

    @property
    def is_connected(self):
        """Returns True if the client is connected, False otherwise."""
        return self.client is not None and self.client.is_connected

    async def connect(self):
        """Connects to the Furby device."""
        if self.is_connected:
            logger.info(f"Already connected to {self.address}.")
            return True
        if not self.address:
            logger.error("No address or BLEDevice provided to connect.")
            raise ValueError("Address or BLEDevice must be set before connecting.")

        logger.info(f"Attempting to connect to {self.address}...")
        try:
            # If self.address is already a BLEDevice, use it directly. BleakClient handles this.
            logger.debug(f"Creating BleakClient for {self.address}")
            self.client = BleakClient(self.address) # BleakClient can take address string or BLEDevice
            await self.client.connect()
            logger.info(f"Successfully connected to Furby at {self.address}.")
            # Do not start idle task by default here. Let user/application logic decide.
            return True
        except BleakError as e:
            logger.error(f"BleakError while connecting to {self.address}: {e}", exc_info=True)
            self.client = None # Ensure client is reset on failure
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while connecting to {self.address}: {e}", exc_info=True)
            self.client = None # Ensure client is reset on failure
            return False

    async def disconnect(self):
        """Disconnects from the Furby device."""
        if self.client and self.client.is_connected:
            logger.info(f"Disconnecting from {self.address}...")
            try:
                logger.debug(f"Stopping idle task for {self.address} before disconnecting.")
                await self.stop_idle() # Ensure idle task is stopped before disconnecting
                logger.debug(f"Calling BleakClient.disconnect() for {self.address}.")
                await self.client.disconnect()
                logger.info(f"Successfully disconnected from {self.address}.")
            except BleakError as e:
                logger.error(f"BleakError during disconnection from {self.address}: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"An unexpected error occurred during disconnection from {self.address}: {e}", exc_info=True)
        else:
            logger.info(f"Client for {self.address} not connected or already disconnected.")
        # self.client = None # Option: Reset client instance after disconnect

    async def _keep_alive_idle(self):
        """Periodically sends an idle command to keep the connection alive and Furby quiet."""
        try:
            while True:
                if self.is_connected:
                    logger.debug(f"Idle task for {self.address}: Sending keep-alive idle command (0x00) to GeneralPlus.")
                    await self.general_plus_write(b'\x00') # general_plus_write has its own logging
                else:
                    logger.warning(f"Idle task for {self.address}: Client not connected, cannot send idle command. Stopping task.")
                    break # Stop if not connected
                await asyncio.sleep(3)  # Send every 3 seconds
        except asyncio.CancelledError:
            logger.info(f"Idle keep-alive task for {self.address} was cancelled.")
        except Exception as e:
            logger.error(f"Error in idle keep-alive task for {self.address}: {e}", exc_info=True)

    def start_idle(self):
        """Starts the idle task if not already running."""
        if not self.is_connected:
            logger.warning(f"Cannot start idle task for {self.address}: Not connected.")
            return
        if self.idle_interval is None or self.idle_interval.done():
            logger.info(f"Starting idle keep-alive task for {self.address}.")
            self.idle_interval = asyncio.create_task(self._keep_alive_idle())
        else:
            logger.info(f"Idle task for {self.address} already running.")

    async def stop_idle(self):
        """Stops the idle task if it is running."""
        if self.idle_interval and not self.idle_interval.done():
            logger.info(f"Stopping idle keep-alive task for {self.address}.")
            self.idle_interval.cancel()
            try:
                await self.idle_interval  # Wait for the task to acknowledge cancellation
            except asyncio.CancelledError:
                logger.info(f"Idle task for {self.address} successfully cancelled and awaited.")
            self.idle_interval = None
        else:
            logger.info(f"Idle task for {self.address} not running or already stopped.")

    async def general_plus_write(self, data: bytes):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_GENERALPLUS_WRITE']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot write to GeneralPlus char {char_uuid}.")
            return
        try:
            logger.debug(f"Writing to GeneralPlus char {char_uuid} on {self.address}: Data={data.hex()}")
            await self.client.write_gatt_char(char_uuid, data, response=True)
        except BleakError as e:
            logger.error(f"BleakError during GeneralPlus write to {char_uuid} on {self.address}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error during GeneralPlus write to {char_uuid} on {self.address}: {e}", exc_info=True)

    async def nordic_write(self, data: bytes):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_NORDIC_WRITE']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot write to Nordic char {char_uuid}.")
            return
        try:
            logger.debug(f"Writing to Nordic char {char_uuid} on {self.address}: Data={data.hex()}")
            await self.client.write_gatt_char(char_uuid, data, response=True)
        except BleakError as e:
            logger.error(f"BleakError during Nordic write to {char_uuid} on {self.address}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error during Nordic write to {char_uuid} on {self.address}: {e}", exc_info=True)

    async def file_write(self, data: bytes):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_FILEWRITE']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot write to File char {char_uuid}.")
            return
        try:
            logger.debug(f"Writing to File char {char_uuid} on {self.address}: Data={data.hex()} (Size: {len(data)} bytes)")
            await self.client.write_gatt_char(char_uuid, data, response=True)
        except BleakError as e:
            logger.error(f"BleakError during File write to {char_uuid} on {self.address}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error during File write to {char_uuid} on {self.address}: {e}", exc_info=True)

    async def _notification_handler(self, sender: int, data: bytearray, callback: callable):
        # Sender is often the characteristic handle, data is the bytearray
        logger.debug(f"Notification received on {self.address}: From sender handle {sender}, Data: {data.hex()}")
        
        # Determine characteristic from sender handle if possible/needed for logging
        char_name = "Unknown Characteristic"
        if sender == self.client.services.get_characteristic(FURBY_CHARACTERISTICS['CHAR_GENERALPLUS_LISTEN']).handle: # Optional chaining if available
             char_name = "GeneralPlus Listen"
        elif sender == self.client.services.get_characteristic(FURBY_CHARACTERISTICS['CHAR_NORDIC_LISTEN']).handle:
             char_name = "Nordic Listen"
        logger.debug(f"Notification on {self.address} from {char_name} (Handle: {sender}): Data: {data.hex()}")

        # If callback is specific to a characteristic, it should know how to handle it.
        if callback:
            # Ensure callback is called in a way that doesn't block
            # asyncio.create_task is good if the callback itself is async
            # If callback is synchronous, it will run in the event loop's thread.
            # For truly long-running sync callbacks, loop.run_in_executor would be better.
            # Assuming callbacks here are relatively quick.

            # Check one-time callbacks first
            # Iterate over a copy of items if callbacks can modify the dict
            for future_id, (condition, future) in list(self.one_time_gp_callbacks.items()):
                if not future.done() and condition(data):
                    logger.debug(f"One-time GP callback condition met for future {future_id}")
                    future.set_result(data)
                    del self.one_time_gp_callbacks[future_id] # Remove the callback once triggered
                    logger.debug(f"One-time GP callback for future {future_id} on {self.address} was fulfilled.")
                    return # One-time callback handled, no further processing by persistent callback
            
            if callback: # Call persistent callback if it exists and wasn't handled by a one-time
                logger.debug(f"Calling persistent notification callback for {self.address}, sender handle {sender}.")
                callback(data)


    async def wait_for_gp_notification(self, condition_check: callable, timeout: float = 10.0) -> bytes:
        """
        Waits for a specific GeneralPlus notification that meets condition_check.
        Returns the notification data if received within timeout, otherwise raises asyncio.TimeoutError.
        """
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot wait for GP notifications.")
            raise BleakError(f"Not connected to {self.address}. Cannot wait for GP notifications.")

        future_id = id(condition_check) 
        future = asyncio.Future()
        self.one_time_gp_callbacks[future_id] = (condition_check, future)
        
        logger.debug(f"Waiting for specific GP notification on {self.address} (ID: {future_id}, Timeout: {timeout}s)")
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.debug(f"Specific GP notification received on {self.address} (ID: {future_id}): {result.hex()}")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for specific GP notification on {self.address} (ID: {future_id}) after {timeout}s.")
            if future_id in self.one_time_gp_callbacks: # Should always be true unless task cancelled differently
                del self.one_time_gp_callbacks[future_id]
            raise # Re-raise TimeoutError for the caller to handle
        except Exception as e:
            logger.error(f"Error while waiting for specific GP notification on {self.address} (ID: {future_id}): {e}", exc_info=True)
            if future_id in self.one_time_gp_callbacks:
                del self.one_time_gp_callbacks[future_id]
            raise


    async def start_gp_notifications(self, callback):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_GENERALPLUS_LISTEN']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot start GeneralPlus notifications on {char_uuid}.")
            return
        try:
            self.gp_listen_callback = callback
            # The lambda now passes the persistent callback (self.gp_listen_callback) to _notification_handler
            await self.client.start_notify(
                char_uuid,
                lambda sender, data: asyncio.create_task(self._notification_handler(sender, data, self.gp_listen_callback))
            )
            logger.info(f"Started GeneralPlus notifications on {self.address} for char {char_uuid}.")
        except BleakError as e:
            logger.error(f"BleakError starting GeneralPlus notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error starting GeneralPlus notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)

    async def stop_gp_notifications(self):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_GENERALPLUS_LISTEN']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot stop GeneralPlus notifications on {char_uuid}.")
            return
        try:
            await self.client.stop_notify(char_uuid)
            logger.info(f"Stopped GeneralPlus notifications on {self.address} for char {char_uuid}.")
        except BleakError as e:
            logger.error(f"BleakError stopping GeneralPlus notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error stopping GeneralPlus notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)
        finally:
            self.gp_listen_callback = None
            logger.debug(f"GP listen callback cleared for {self.address} on char {char_uuid}.")


    async def start_nordic_notifications(self, callback):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_NORDIC_LISTEN']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot start Nordic notifications on {char_uuid}.")
            return
        try:
            self.nordic_listen_callback = callback
            await self.client.start_notify(
                char_uuid,
                lambda sender, data: asyncio.create_task(self._notification_handler(sender, data, self.nordic_listen_callback))
            )
            logger.info(f"Started Nordic notifications on {self.address} for char {char_uuid}.")
        except BleakError as e:
            logger.error(f"BleakError starting Nordic notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error starting Nordic notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)

    async def stop_nordic_notifications(self):
        char_uuid = FURBY_CHARACTERISTICS['CHAR_NORDIC_LISTEN']
        if not self.is_connected:
            logger.error(f"Not connected to {self.address}. Cannot stop Nordic notifications on {char_uuid}.")
            return
        try:
            await self.client.stop_notify(char_uuid)
            logger.info(f"Stopped Nordic notifications on {self.address} for char {char_uuid}.")
        except BleakError as e:
            logger.error(f"BleakError stopping Nordic notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error stopping Nordic notifications on {self.address} for char {char_uuid}: {e}", exc_info=True)
        finally:
            self.nordic_listen_callback = None
            logger.debug(f"Nordic listen callback cleared for {self.address} on char {char_uuid}.")


async def main():
    # Example usage for testing
    logging.basicConfig(level=logging.DEBUG) # Ensure logs are visible for testing
    logger.info("Starting Furby connection test...")

    discovered_furbys = await PyFluffConnect.discover_furbys(timeout=5.0)

    if not discovered_furbys:
        logger.info("No Furbys found during discovery. Exiting test.")
        return

    # Take the first discovered Furby
    furby_device = discovered_furbys[0]
    logger.info(f"Proceeding with Furby: {furby_device.name} ({furby_device.address})")

    fluff_instance = PyFluffConnect(furby_device) # or use furby_device.address

    connection_status = await fluff_instance.connect()
    logger.info(f"Connection status: {'Connected' if connection_status else 'Failed'}")

    if fluff_instance.is_connected:
        logger.info("Successfully connected to Furby.")
        try:
            logger.info("Attempting to get services...")
            services = await fluff_instance.client.get_services()
            # logger.info("Services found:") # Less verbose logging
            # for service in services:
            #     logger.debug(f"  Service UUID: {service.uuid}")
            #     for char in service.characteristics:
            #         logger.debug(f"    Characteristic UUID: {char.uuid}, Properties: {char.properties}")

            def gp_data_received(data: bytes):
                logging.info(f"GP Data Received: {data.hex()}")

            def nordic_data_received(data: bytes):
                logging.info(f"Nordic Data Received: {data.hex()}")

            logger.info("Starting notifications...")
            await fluff_instance.start_gp_notifications(gp_data_received)
            await fluff_instance.start_nordic_notifications(nordic_data_received)

            logger.info("Sleeping for 5 seconds to listen for notifications...")
            await asyncio.sleep(5)

            logger.info("Testing GeneralPlus write (idle command b'\\x00')...")
            await fluff_instance.general_plus_write(b'\x00')
            await asyncio.sleep(1) # Short delay after write if expecting immediate notification

            logger.info("Stopping notifications...")
            await fluff_instance.stop_gp_notifications()
            await fluff_instance.stop_nordic_notifications()
            await asyncio.sleep(1) # Give time for stop to process

        except BleakError as e:
            logger.error(f"BleakError during operations: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during operations: {e}")
        finally:
            logger.info("Attempting to disconnect...")
            await fluff_instance.disconnect()
            logger.info("Disconnected from Furby.")
    else:
        logger.warning("Could not connect to Furby. Skipping operations.")

    logger.info("Furby connection test finished.")

if __name__ == "__main__":
    asyncio.run(main())
