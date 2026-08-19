import pyvisa
import csv
import json
from pathlib import Path
from datetime import datetime
import time


try:
    from pyvisa.errors import VisaIOError
except Exception:
    VisaIOError = Exception


visaResourceAddr = 'USB0::0x0699::0x0401::C011280::INSTR'
class DPO4054:
    # def __init__(self, resource_name=visaResourceAddr,auto_connect=True):
    #     """
    #     Initializes the connection to the DPO4054 oscilloscope.
    #
    #     :param resource_name: VISA resource name for the oscilloscope (e.g., 'USB0::0x0699::0x0408::C010101::INSTR').
    #     """
    #     self.resource_name = resource_name
    #     self.rm = pyvisa.ResourceManager()
    #     self.scope = None
    #     self.channel_labels = {}
    #     self.settings_folder = Path("scope_settings")
    #     self.settings_folder.mkdir(parents=True, exist_ok=True)
    #     try:
    #         self.scope = self.rm.open_resource(self.resource_name)
    #         print(f"Connected to: {self.scope.query('*IDN?')}")
    #     except Exception as e:
    #         raise ConnectionError(f"Failed to connect to the oscilloscope: {e}")
    def __init__(self, resource_name=visaResourceAddr, auto_connect=True):
        """
        Initialize DPO4054 oscilloscope object.

        :param resource_name: VISA resource name for the oscilloscope.
        :param auto_connect: If True, connect during initialization.
        """
        self.resource_name = resource_name
        self.rm = pyvisa.ResourceManager()
        self.scope = None
        self.channel_labels = {}
        self.settings_folder = Path("scope_settings")
        self.settings_folder.mkdir(parents=True, exist_ok=True)

        if auto_connect:
            self.connect()
    # def connect(self):
    #     """Connect to the oscilloscope."""
    #     try:
    #         self.scope = self.rm.open_resource(self.resource_name)
    #         print(f"Connected to: {self.scope.query('*IDN?')}")
    #     except Exception as e:
    #         raise ConnectionError(f"Failed to connect to the oscilloscope: {e}")

    # def disconnect(self):
    #     """Close the connection to the oscilloscope."""
    #     if self.scope:
    #         self.scope.close()

    def connect(self):
        """
        Connect to oscilloscope.
        Safe to call multiple times.
        """
        if self.scope is not None:
            return

        try:
            self.scope = self.rm.open_resource(self.resource_name)
            idn = self.scope.query("*IDN?").strip()
            print(f"Connected to: {idn}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to the oscilloscope: {e}")
    def disconnect(self):
        """
        Disconnect oscilloscope safely.
        """
        if self.scope is not None:
            self.scope.close()
            self.scope = None

        if self.rm is not None:
            self.rm.close()
            self.rm = None
    def trigger(self):
        """
        Initiates a single acquisition trigger on the oscilloscope.
        """
        if not self.scope:
            raise ConnectionError("Oscilloscope not connected. Call connect() first.")
        self.scope.write("ACQUIRE:STATE ON")
        # print("Trigger initiated.")
    def force_trigger(self):
        """
        Forces a trigger event on the oscilloscope.
        """
        if not self.scope:
            raise ConnectionError("Oscilloscope not connected. Call connect() first.")
        self.scope.write("TRIG FORC")
        # print("Force trigger initiated.")

    # def save_scope_settings(self, file_name=None):
    #     """
    #     Save current oscilloscope setup to a JSON file.
    #
    #     If file_name is not provided, a timestamped file is created
    #     in the default settings folder.
    #
    #     :param file_name: Optional file name or full path.
    #                       Example: "my_setup.json"
    #     :return: Path to saved file.
    #     """
    #     if file_name is None:
    #         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #         file_path = self.settings_folder / f"dpo4554_setup_{timestamp}.json"
    #     else:
    #         file_path = Path(file_name)
    #
    #         # If only filename is given, save inside default folder
    #         if not file_path.is_absolute() and file_path.parent == Path("."):
    #             file_path = self.settings_folder / file_path
    #
    #     file_path.parent.mkdir(parents=True, exist_ok=True)
    #
    #     try:
    #         idn = self.scope.query("*IDN?").strip()
    #     except Exception:
    #         idn = "Unknown"
    #
    #     self.scope.write("*CLS")
    #
    #     try:
    #         setup_string = self.scope.query("*LRN?").strip()
    #     except Exception:
    #         setup_string = self.scope.query("SET?").strip()
    #
    #     data = {
    #         "instrument": idn,
    #         "saved_at": datetime.now().isoformat(timespec="seconds"),
    #         "setup_format": "tektronix_scpi_lrn",
    #         "setup": setup_string,
    #     }
    #
    #     file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    #
    #     return file_path
    #
    # def apply_scope_settings(
    #         self,
    #         file_name,
    #         wait_complete=False,
    #         check_error=True,
    #         restore_delay_s=2.0,
    #         opc_timeout_ms=30000,
    # ):
    #     """
    #     Apply oscilloscope setup from a saved JSON file.
    #
    #     :param file_name: File name or full path.
    #     :param wait_complete: If True, use *OPC? after restore.
    #                           For Tektronix scopes this can timeout if scope enters RUN mode.
    #                           Default is False.
    #     :param check_error: Check oscilloscope error status after applying setup.
    #     :param restore_delay_s: Fixed delay after sending setup.
    #     :param opc_timeout_ms: Temporary VISA timeout for *OPC?, in milliseconds.
    #     :return: Loaded setup dictionary.
    #     """
    #     file_path = Path(file_name)
    #
    #     # If only filename is given, search inside default folder
    #     if not file_path.is_absolute() and file_path.parent == Path("."):
    #         file_path = self.settings_folder / file_path
    #
    #     if not file_path.exists():
    #         raise FileNotFoundError(f"Scope setup file not found: {file_path}")
    #
    #     data = json.loads(file_path.read_text(encoding="utf-8"))
    #
    #     setup_string = data.get("setup")
    #     if not setup_string:
    #         raise ValueError("Invalid setup file: missing or empty 'setup' field.")
    #
    #     # Clear old status/errors
    #     self.scope.write("*CLS")
    #
    #     # Send saved setup back to scope
    #     self.scope.write(setup_string)
    #
    #     # Give the oscilloscope time to process the long setup command
    #     time.sleep(restore_delay_s)
    #
    #     if wait_complete:
    #         old_timeout = self.scope.timeout
    #
    #         try:
    #             self.scope.timeout = opc_timeout_ms
    #             self.scope.query("*OPC?")
    #         except VisaIOError as e:
    #             raise TimeoutError(
    #                 "Timeout while waiting for *OPC? after restoring scope settings. "
    #                 "The setup may still have been applied. "
    #                 "Try wait_complete=False, increase opc_timeout_ms, or stop acquisition before restore."
    #             ) from e
    #         finally:
    #             self.scope.timeout = old_timeout
    #
    #     if check_error:
    #         try:
    #             esr_text = self.scope.query("*ESR?").strip()
    #             esr = int(esr_text)
    #         except Exception as e:
    #             raise RuntimeError(
    #                 "Could not read *ESR? after applying scope settings."
    #             ) from e
    #
    #         if esr != 0:
    #             try:
    #                 error_text = self.scope.query("ALLEV?").strip()
    #             except Exception:
    #                 error_text = "Could not read ALLEV?"
    #
    #             raise RuntimeError(
    #                 f"Scope reported error after applying setup. "
    #                 f"ESR={esr}, ALLEV={error_text}"
    #             )
    #
    #     return data
    def save_scope_settings(self, file_name=None, ask_before_overwrite=True):
        """
        Save current oscilloscope setup to a JSON file.

        If file_name is not provided, a timestamped file is created
        in the default settings folder.

        If file already exists, user is asked before overwriting.
        If user does not want to overwrite, user can enter a new filename.

        :param file_name: Optional file name or full path.
                          Example: "my_setup.json"
        :param ask_before_overwrite: If True, ask user before overwriting existing file.
        :return: Path to saved file, or None if saving was cancelled.
        """
        if file_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = self.settings_folder / f"dpo4554_setup_{timestamp}.json"
        else:
            file_path = Path(file_name)

            # If only filename is given, save inside default folder
            if not file_path.is_absolute() and file_path.parent == Path("."):
                file_path = self.settings_folder / file_path

        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Ask before overwriting existing file
        while file_path.exists() and ask_before_overwrite:
            answer = input(
                f"File already exists:\n"
                f"{file_path}\n\n"
                f"Overwrite it? [y/N]: "
            ).strip().lower()

            if answer in ("y", "yes"):
                break

            new_file_name = input(
                "Enter new filename, or press Enter to cancel: "
            ).strip()

            if not new_file_name:
                print("Saving cancelled.")
                return None

            file_path = Path(new_file_name)

            # If only filename is given, save inside default folder
            if not file_path.is_absolute() and file_path.parent == Path("."):
                file_path = self.settings_folder / file_path

            # Add .json automatically if user forgot extension
            if file_path.suffix == "":
                file_path = file_path.with_suffix(".json")

            file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            idn = self.scope.query("*IDN?").strip()
        except Exception:
            idn = "Unknown"

        self.scope.write("*CLS")

        try:
            setup_string = self.scope.query("*LRN?").strip()
        except Exception:
            setup_string = self.scope.query("SET?").strip()

        data = {
            "instrument": idn,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "setup_format": "tektronix_scpi_lrn",
            "setup": setup_string,
        }

        file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")

        print(f"Scope settings saved to: {file_path}")

        return file_path
    def save_image_path(self, path=""):
        self.scope.write("SAVe:IMAGe:FILEFormat PNG")
        self.scope.write("SAVe:IMAGe:INKSaver OFF")
        self.scope.write("HARDCopy STARt")
        imgData = self.scope.read_raw()

        # Generate a filename based on the current Date & Time

        imgFile = open(path, "wb")
        imgFile.write(imgData)
        # print("File location", path)
        imgFile.close()

    def save_waveform_to_csv(self, channel, filename):
        """
        Save the waveform data from a specific channel to a CSV file.

        :param channel: Channel number (e.g., 1, 2, 3, or 4).
        :param filename: The output CSV file name.
        """
        if not self.scope:
            raise ConnectionError("Oscilloscope not connected. Call connect() first.")

        # Select the channel
        self.scope.write(f"DATA:SOURCE CH{channel}")

        # Set the data format to ASCII for easier processing
        self.scope.write("DATA:ENC ASCII")

        # Query the waveform data
        raw_data = self.scope.query("CURVE?")

        # Parse the waveform data
        waveform_data = [float(value) for value in raw_data.split(',')]

        # Get scaling factors
        x_increment = float(self.scope.query("WFMPRE:XINCR?"))
        x_origin = float(self.scope.query("WFMPRE:XZERO?"))
        y_multiplier = float(self.scope.query("WFMPRE:YMULT?"))
        y_offset = float(self.scope.query("WFMPRE:YOFF?"))
        y_zero = float(self.scope.query("WFMPRE:YZERO?"))

        # Create CSV file with the waveform data
        with open(filename, mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["Time (s)", "Voltage (V)"])

            for i, y_raw in enumerate(waveform_data):
                time = x_origin + i * x_increment
                voltage = (y_raw - y_offset) * y_multiplier + y_zero
                writer.writerow([time, voltage])

        # print(f"Waveform saved to {filename}")

    def save_all_channels_to_csv(self, base_filename):
        """
        Save waveforms from all enabled channels to separate CSV files.

        :param base_filename: Base filename (e.g., 'waveform') - channels will append numbers (e.g., 'waveform_CH1.csv').
        """
        if not self.scope:
            raise ConnectionError("Oscilloscope not connected. Call connect() first.")

        # Check for enabled channels
        for channel in range(1, 5):
            channel_status = self.scope.query(f"SELECT:CH{channel}?").strip()
            if channel_status == '1':
                self.save_waveform_to_csv(channel, f"{base_filename}_CH{channel}.csv")

    def save_all_channels_to_single_csv(self, filename):
        """
        Save waveforms from all enabled channels to a single CSV file with each channel as a separate column.

        :param filename: The output CSV file name.
        """
        if not self.scope:
            raise ConnectionError("Oscilloscope not connected. Call connect() first.")

        # Data container for all channels
        channel_data = {}
        time_data = None

        for channel in range(1, 5):
            # Check if the channel is enabled
            channel_status = self.scope.query(f"SELECT:CH{channel}?").strip()
            if channel_status == '1':
                # Select the channel
                self.scope.write(f"DATA:SOURCE CH{channel}")

                # Set the data format to ASCII for easier processing
                self.scope.write("DATA:ENC ASCII")

                # Query the waveform data
                raw_data = self.scope.query("CURVE?")

                # Parse the waveform data
                waveform_data = [float(value) for value in raw_data.split(',')]

                # Get scaling factors
                x_increment = float(self.scope.query("WFMPRE:XINCR?"))
                x_origin = float(self.scope.query("WFMPRE:XZERO?"))
                y_multiplier = float(self.scope.query("WFMPRE:YMULT?"))
                y_offset = float(self.scope.query("WFMPRE:YOFF?"))
                y_zero = float(self.scope.query("WFMPRE:YZERO?"))

                # Calculate time and voltage data
                times = [x_origin + i * x_increment for i in range(len(waveform_data))]
                voltages = [(y_raw - y_offset) * y_multiplier + y_zero for y_raw in waveform_data]

                # Store time data only once
                if time_data is None:
                    time_data = times

                # Store channel data
                label = self.scope.query(f"CH{channel}:LABEL?").strip()
                if not label:
                    label = f"CH{channel}"
                channel_data[label] = voltages

        # Write data to CSV
        with open(filename, mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file)

            # Write header row
            header = ["Time (s)"] + list(channel_data.keys())
            writer.writerow(header)

            # Write rows
            for i in range(len(time_data)):
                row = [time_data[i]] + [channel_data[ch][i] for ch in channel_data.keys()]
                writer.writerow(row)

    def set_channel_label(self, channel, label):
        """
        Set a label for a specific channel and display it on the oscilloscope screen.

        :param channel: Channel number (1-4).
        :param label: Label for the channel.
        """
        if channel < 1 or channel > 4:
            raise ValueError("Channel must be between 1 and 4.")
        self.channel_labels[channel] = label

        # Set label on oscilloscope screen
        self.scope.write(f"CH{channel}:LABEL \"{label}\"")

    def get_channel_label(self, channel):
        """
        Read label from a specific oscilloscope channel.

        :param channel: Channel number, 1-4.
        :return: Channel label as string.
        """
        if channel < 1 or channel > 4:
            raise ValueError("Channel must be between 1 and 4.")

        response = self.scope.query(f"CH{channel}:LABEL?").strip()

        # Tektronix may return:
        #   "INPUT"
        # or, if headers are enabled:
        #   :CH1:LABEL "INPUT"
        if '"' in response:
            label = response.split('"', 1)[1].rsplit('"', 1)[0]
        else:
            label = response.replace(f":CH{channel}:LABEL", "").strip()

        self.channel_labels[channel] = label
        return label

    def get_ch_max(self, ch_num):
        self.scope.write('MEASUrement:IMMed:TYPe MAXimum')
        self.scope.write(f'MEASUrement:IMMed:SOUrce CH{ch_num}')  # Switch to channel 2
        max_value = self.scope.query('MEASUrement:IMMed:VALue?')
        return max_value

    def set_trigger_level(self, level, channel=None, verify=True):
        """
        Set A trigger level.

        :param level: Trigger level in volts, or "TTL" / "ECL".
                      Example: 1.5, 0.2, -1.0, "TTL"
        :param channel: Optional channel number 1-4.
                        If None, sets general A trigger level.
                        If 1-4, sets trigger level for that channel.
        :param verify: If True, read back trigger level after setting.
        :return: Actual trigger level returned by scope if verify=True, else None.
        """
        if self.scope is None:
            raise ConnectionError("Oscilloscope is not connected.")

        if isinstance(level, str):
            level_value = level.strip().upper()

            if level_value not in ("TTL", "ECL"):
                raise ValueError("String level must be 'TTL' or 'ECL'.")
        else:
            level_value = float(level)

        if channel is None:
            command = "TRIGGER:A:LEVEL"
        else:
            if channel < 1 or channel > 4:
                raise ValueError("Channel must be between 1 and 4.")

            command = f"TRIGGER:A:LEVEL:CH{channel}"

        self.scope.write(f"{command} {level_value}")

        if verify:
            return self.get_trigger_level(channel=channel)

        return None

    def get_trigger_level(self, channel=None):
        """
        Read A trigger level.

        :param channel: Optional channel number 1-4.
                        If None, reads general A trigger level.
                        If 1-4, reads trigger level for that channel.
        :return: Trigger level as float if possible, otherwise raw response string.
        """
        if self.scope is None:
            raise ConnectionError("Oscilloscope is not connected.")

        if channel is None:
            command = "TRIGGER:A:LEVEL?"
        else:
            if channel < 1 or channel > 4:
                raise ValueError("Channel must be between 1 and 4.")

            command = f"TRIGGER:A:LEVEL:CH{channel}?"

        response = self.scope.query(command).strip()

        # Response can be:
        # ":TRIGGER:A:LEVEL:CH2 1.3000E+00"
        # or just:
        # "1.3000E+00"
        value_text = response.split()[-1]

        try:
            return float(value_text)
        except ValueError:
            return response

    def set_edge_trigger_source(self, channel):
        """
        Set A edge trigger source to CH1-CH4.

        :param channel: Channel number 1-4.
        """
        if self.scope is None:
            raise ConnectionError("Oscilloscope is not connected.")

        if channel < 1 or channel > 4:
            raise ValueError("Channel must be between 1 and 4.")

        self.scope.write(f"TRIGGER:A:EDGE:SOURCE CH{channel}")

    def rearm_trigger_after_image(self, trigger_channel=None, restore_level=True):
        """
        Re-arm DPO4054 trigger/acquisition after screen image read.

        This is useful if HARDCOPY/image transfer leaves trigger/acquisition
        in a stale state on older DPO4000 firmware.

        :param trigger_channel: Optional trigger channel 1-4.
                                If provided, channel trigger level is read and restored.
        :param restore_level: Re-write current trigger level.
        """
        if self.scope is None:
            raise ConnectionError("Oscilloscope is not connected.")

        # Let image transfer finish internally
        time.sleep(0.3)

        try:
            self.scope.write("*CLS")
        except Exception:
            pass

        # Re-write current trigger mode
        try:
            trig_mode = self.scope.query("TRIGGER:A:MODE?").strip().split()[-1]
            self.scope.write(f"TRIGGER:A:MODE {trig_mode}")
        except Exception:
            pass

        # Re-write trigger level
        if restore_level:
            try:
                if trigger_channel is None:
                    level = self.scope.query("TRIGGER:A:LEVEL?").strip().split()[-1]
                    self.scope.write(f"TRIGGER:A:LEVEL {level}")
                else:
                    if trigger_channel < 1 or trigger_channel > 4:
                        raise ValueError("trigger_channel must be 1-4.")

                    level = self.scope.query(
                        f"TRIGGER:A:LEVEL:CH{trigger_channel}?"
                    ).strip().split()[-1]

                    self.scope.write(
                        f"TRIGGER:A:LEVEL:CH{trigger_channel} {level}"
                    )
            except Exception:
                pass

        # Re-start acquisition
        self.scope.write("ACQUIRE:STATE RUN")

        time.sleep(0.2)

    def nudge_trigger_level_knob(self):
        """
        Workaround for DPO4054 trigger not re-arming after screenshot read.
        Simulates moving trigger level knob up and back.
        """
        if self.scope is None:
            raise ConnectionError("Oscilloscope is not connected.")

        self.scope.write("FPANEL:TURN TRIGLEVEL,1")
        time.sleep(0.1)
        self.scope.write("FPANEL:TURN TRIGLEVEL,-1")
        time.sleep(0.2)
        self.scope.write("ACQUIRE:STATE RUN")
# if __name__ == "__main__":
    # # Example usage
    # scope = DPO4054()
    #
    # try:
    #     scope.connect()
    #     # scope.save_all_channels_to_single_csv("waveform_all_channels.csv")
    #     # scope.set_channel_label(1, "Vc_galaxy")
    #     # scope.set_channel_label(2, "Vc_mcc")
    #     # scope.set_channel_label(3, "V_in")
    #     # scope.set_channel_label(4, "")
    #     # scope.set_channel_label(3, "VREG-5V")
    #     # scope.set_channel_label(4, "SW_NODE")
    #     scope.save_all_channels_to_single_csv("mcc_vs_llf_vishay.csv")
    #
    # finally:
    #     scope.disconnect()