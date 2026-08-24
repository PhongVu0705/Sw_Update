import os
import queue
import shutil
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

from opelink_comm import OpenLinkComm, list_ports
from command_runner import (
    on_rx_callback,
    on_tx_callback,
    print_queued_messages,
    execute_command_list,
    execute_bin_flashing_sequence,
    send_and_get_final_rx,
)
from script_builder import (
    generate_and_save_bin_script,
    SeqIdTracker,
    build_frame,
    build_frame_custom_checksum,
)
from csv_processor import get_commands_from_csv

# ============================================================
# UI CONFIGURATION
# ============================================================
ctk.set_appearance_mode("light")
_theme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "milwaukee_theme.json")
ctk.set_default_color_theme(_theme_path)

BAUD_RATE = 115200

# Border style dùng chung cho các khối (frame) trong GUI - làm viền đậm hơn
BLOCK_BORDER_WIDTH = 1
BLOCK_BORDER_COLOR = "#4a4a4a"


class SwUpdateApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SW Update Tool - Firmware Flashing")
        self.geometry("1000x750")
        self.minsize(900, 650)

        # Connection state
        self.comm = None
        self.connected = False
        self.worker_thread = None
        self.ports_info = []  # Store port info (port, description)

        # GUI log queue (thread-safe)
        self.gui_log_queue = queue.Queue()

        # ============ BUILD UI ============
        self._build_ui()

        # Start log polling loops
        self.after(100, self._poll_log_queue)
        self.after(100, self._poll_serial_messages)

        # Auto-scan COM ports on startup
        self.refresh_ports()

    # ============================================================
    # BUILD UI
    # ============================================================
    def _build_ui(self):
        # ---------- Header ----------
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(15, 5))

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="SW UPDATE TOOL",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        self.title_label.pack(side="left")

        self.status_label = ctk.CTkLabel(
            self.header_frame,
            text="● Not connected",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#d01b2e",
        )
        self.status_label.pack(side="right")

        # ---------- Connection section ----------
        self.conn_frame = ctk.CTkFrame(
            self, corner_radius=10,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        self.conn_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(self.conn_frame, text="COM PORT:", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(15, 5), pady=10
        )

        self.port_combo = ctk.CTkComboBox(self.conn_frame, width=400, values=["Scanning..."])
        self.port_combo.pack(side="left", padx=5, pady=10)

        self.refresh_btn = ctk.CTkButton(
            self.conn_frame, text="Refresh", width=100, command=self.refresh_ports
        )
        self.refresh_btn.pack(side="left", padx=5, pady=10)

        self.connect_btn = ctk.CTkButton(
            self.conn_frame, text="Connect", width=120, command=self.toggle_connect
        )
        self.connect_btn.pack(side="left", padx=5, pady=10)

        # ---------- Function tabs ----------
        self.tabview = ctk.CTkTabview(
            self, corner_radius=10,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        self.tabview.pack(fill="both", expand=True, padx=20, pady=10)

        # ===== TAB 1: FIRMWARE UPDATE (BIN) =====
        self.tab_bin = self.tabview.add("Firmware Update (BIN)")
        self._build_bin_tab(self.tab_bin)

        # ===== TAB 2: SEND CSV COMMANDS =====
        self.tab_csv = self.tabview.add("Send CSV Commands")
        self._build_csv_tab(self.tab_csv)

        # ===== TAB 3: MANUAL HEX =====
        self.tab_hex = self.tabview.add("Send Command")
        self._build_hex_tab(self.tab_hex)

        # ---------- Log area ----------
        self.log_frame = ctk.CTkFrame(
            self, corner_radius=10,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        self.log_frame.pack(fill="both", expand=True, padx=20, pady=(5, 10))

        ctk.CTkLabel(
            self.log_frame, text="ACTIVITY LOG", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.log_textbox = ctk.CTkTextbox(self.log_frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

        # ---------- Footer ----------
        self.footer_label = ctk.CTkLabel(
            self,
            text="SW Update Tool v1.0.0 | Made By Grey Le Phong Vu",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.footer_label.pack(side="bottom", pady=5)

    def _build_bin_tab(self, parent):
        # File selection frame
        file_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        file_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(file_frame, text="BIN File:", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(10, 5), pady=10
        )

        self.bin_path_var = ctk.StringVar(value="")
        self.bin_path_entry = ctk.CTkEntry(file_frame, textvariable=self.bin_path_var, width=400)
        self.bin_path_entry.pack(side="left", padx=5, pady=10, fill="x", expand=True)

        self.bin_browse_btn = ctk.CTkButton(
            file_frame, text="Browse...", width=120, command=self.browse_bin_file
        )
        self.bin_browse_btn.pack(side="left", padx=5, pady=10)

        # Tool type selection frame
        tool_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        tool_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(tool_frame, text="Tool Type:", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(10, 10), pady=10
        )

        self.tool_type_var = ctk.StringVar(value="M12")
        self.m12_radio = ctk.CTkRadioButton(
            tool_frame, text="M12", variable=self.tool_type_var, value="M12"
        )
        self.m12_radio.pack(side="left", padx=10, pady=10)

        self.m18_radio = ctk.CTkRadioButton(
            tool_frame, text="M18", variable=self.tool_type_var, value="M18"
        )
        self.m18_radio.pack(side="left", padx=10, pady=10)

        # Update button
        self.update_btn = ctk.CTkButton(
            parent,
            text="UPDATE FIRMWARE",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=45,
            fg_color="#d01b2e",
            hover_color="#b21424",
            command=self.start_bin_update,
        )
        self.update_btn.pack(fill="x", padx=15, pady=15)

        # Progress bar frame
        progress_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        progress_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.progress_label = ctk.CTkLabel(
            progress_frame, text="Progress: 0%", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.progress_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=20)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.progress_bar.set(0)

        # # Instructions
        # info_text = (
        #     "💡 Instructions:\n"
        #     "1. Select the firmware .BIN file to flash\n"
        #     "2. Select the Tool type (M12 or M18)\n"
        #     "3. Click 'UPDATE FIRMWARE' - the process runs automatically (no confirmation needed)\n"
        #     "4. Monitor progress in the LOG window below"
        # )
        # ctk.CTkLabel(
        #     parent, text=info_text, justify="left", font=ctk.CTkFont(size=12), text_color="gray"
        # ).pack(anchor="w", padx=20, pady=(0, 10))

    def _build_csv_tab(self, parent):
        # File selection frame
        file_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        file_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(file_frame, text="CSV File:", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(10, 5), pady=10
        )

        self.csv_path_var = ctk.StringVar(value="")
        self.csv_path_entry = ctk.CTkEntry(file_frame, textvariable=self.csv_path_var, width=400)
        self.csv_path_entry.pack(side="left", padx=5, pady=10, fill="x", expand=True)

        self.csv_browse_btn = ctk.CTkButton(
            file_frame, text="Browse...", width=120, command=self.browse_csv_file
        )
        self.csv_browse_btn.pack(side="left", padx=5, pady=10)

        # Tool type selection frame
        tool_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        tool_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(tool_frame, text="Tool Type:", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(10, 10), pady=10
        )

        self.csv_tool_type_var = ctk.StringVar(value="M12")
        ctk.CTkRadioButton(
            tool_frame, text="M12", variable=self.csv_tool_type_var, value="M12"
        ).pack(side="left", padx=10, pady=10)
        ctk.CTkRadioButton(
            tool_frame, text="M18", variable=self.csv_tool_type_var, value="M18"
        ).pack(side="left", padx=10, pady=10)

        # Send button
        self.csv_send_btn = ctk.CTkButton(
            parent,
            text="SEND CSV COMMANDS",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=45,
            fg_color="#d01b2e",
            hover_color="#b21424",
            command=self.start_csv_send,
        )
        self.csv_send_btn.pack(fill="x", padx=15, pady=15)

        # Progress bar frame
        csv_progress_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        csv_progress_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.csv_progress_label = ctk.CTkLabel(
            csv_progress_frame, text="Progress: 0%", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.csv_progress_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.csv_progress_bar = ctk.CTkProgressBar(csv_progress_frame, height=20)
        self.csv_progress_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.csv_progress_bar.set(0)

        # info_text = (
        #     "💡 Instructions:\n"
        #     "1. Select the .CSV file containing the command set (column 'Message')\n"
        #     "2. Select the Tool type (M12 or M18)\n"
        #     "3. Click 'SEND CSV COMMANDS' to send all commands\n"
        #     "4. The system automatically adds 2 init commands (Target + Metcopassword)"
        # )
        # ctk.CTkLabel(
        #     parent, text=info_text, justify="left", font=ctk.CTkFont(size=12), text_color="gray"
        # ).pack(anchor="w", padx=20, pady=(0, 10))

    def _build_hex_tab(self, parent):
        # Hex input frame
        hex_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        hex_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(hex_frame, text="Hex String:", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(10, 5), pady=10
        )

        self.hex_entry = ctk.CTkEntry(hex_frame, width=500, placeholder_text="e.g. 70 01 01 11")
        self.hex_entry.pack(side="left", padx=5, pady=10, fill="x", expand=True)

        # Send button
        self.hex_send_btn = ctk.CTkButton(
            parent,
            text="SEND HEX",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=45,
            fg_color="#d01b2e",
            hover_color="#b21424",
            command=self.send_manual_hex,
        )
        self.hex_send_btn.pack(fill="x", padx=15, pady=15)

        # ===== Command buttons frame =====
        cmd_frame = ctk.CTkFrame(
            parent, corner_radius=8,
            border_width=BLOCK_BORDER_WIDTH, border_color=BLOCK_BORDER_COLOR,
        )
        cmd_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(
            cmd_frame, text="QUICK COMMANDS:", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # Grid layout: 3 columns x 2 rows (wraps to 2 rows when window is small)
        self.cmd_grid = ctk.CTkFrame(cmd_frame, fg_color="transparent")
        self.cmd_grid.pack(fill="x", padx=10, pady=(0, 10))

        # Configure grid columns to expand equally
        for col in range(3):
            self.cmd_grid.grid_columnconfigure(col, weight=1, uniform="cmd_btn")

        # Button 1: Check FW version
        self.cmd_fw_version_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Check FW Version",
            height=40,
            command=lambda: self.send_quick_command("fw_version"),
        )
        self.cmd_fw_version_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # Button 2: Check MPBID
        self.cmd_mpbid_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Check MPBID",
            height=40,
            command=lambda: self.send_quick_command("mpbid"),
        )
        self.cmd_mpbid_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Button 3: Check FW P/N
        self.cmd_fw_pn_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Check FW P/N",
            height=40,
            command=lambda: self.send_quick_command("fw_pn"),
        )
        self.cmd_fw_pn_btn.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Button 4: Read Data calibration
        self.cmd_calibration_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Read Data Calibration",
            height=40,
            command=lambda: self.send_quick_command("calibration"),
        )
        self.cmd_calibration_btn.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        # Button 5: Target M18
        self.cmd_target_m18_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Target M18",
            height=40,
            command=lambda: self.send_quick_command("target_m18"),
        )
        self.cmd_target_m18_btn.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Button 6: Target M12
        self.cmd_target_m12_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Target M12",
            height=40,
            command=lambda: self.send_quick_command("target_m12"),
        )
        self.cmd_target_m12_btn.grid(row=1, column=2, padx=5, pady=5, sticky="ew")

        # Button 7: Send Default Metco Password
        self.cmd_metco_password_btn = ctk.CTkButton(
            self.cmd_grid,
            text="Send Default Metco Password",
            height=40,
            command=lambda: self.send_quick_command("metco_password"),
        )
        self.cmd_metco_password_btn.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

        # info_text = (
        #     "💡 Instructions:\n"
        #     "1. Enter the Hex string to send (bytes separated by spaces)\n"
        #     "2. Click 'SEND HEX' to send a single command to the MCU\n"
        #     "3. The MCU response will be displayed in the LOG window"
        # )
        # ctk.CTkLabel(
        #     parent, text=info_text, justify="left", font=ctk.CTkFont(size=12), text_color="gray"
        # ).pack(anchor="w", padx=20, pady=(0, 10))

    # ============================================================
    # LOG & MESSAGE HANDLING
    # ============================================================
    def _log(self, message: str):
        """Put message into GUI log queue (thread-safe)."""
        self.gui_log_queue.put(message)

    def _poll_log_queue(self):
        """Read log from queue and display in textbox (runs on main thread)."""
        try:
            while True:
                msg = self.gui_log_queue.get_nowait()
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", msg + "\n")
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _poll_serial_messages(self):
        """Read TX/RX messages from command_runner msg_queue and display."""
        print_queued_messages(log_callback=self._log)
        self.after(100, self._poll_serial_messages)

    # ============================================================
    # COM PORT CONNECTION
    # ============================================================
    def refresh_ports(self):
        """Scan available COM ports and display with descriptions."""
        self.ports_info = list_ports()
        if self.ports_info:
            # Format: "COM3 - USB Serial Port (COM3)"
            port_display = [
                f"{p['port']} - {p['description']}" for p in self.ports_info
            ]
            self.port_combo.configure(values=port_display)
            if port_display:
                self.port_combo.set(port_display[0])
        else:
            self.ports_info = []
            self.port_combo.configure(values=["No COM ports found"])
            self.port_combo.set("No COM ports found")

    def toggle_connect(self):
        """Connect / disconnect COM port."""
        if not self.connected:
            self._connect()
        else:
            self._disconnect()

    def _connect(self):
        port_display = self.port_combo.get().strip()
        if not port_display or "No COM ports" in port_display:
            messagebox.showerror("Error", "Please select a valid COM port!")
            return

        # Extract port name from display string (e.g. "COM3 - USB Serial Port" -> "COM3")
        port_name = port_display.split(" - ")[0].strip()

        self.comm = OpenLinkComm(
            port=port_name,
            baud_rate=BAUD_RATE,
            on_rx=on_rx_callback,
            on_tx=on_tx_callback,
        )

        if self.comm.connect():
            self.connected = True
            self.connect_btn.configure(text="🔌 Disconnect", fg_color="#d01b2e", hover_color="#b21424")
            self.status_label.configure(text=f"● Connected: {port_name}", text_color="#2E7D32")
            self._log(f"Successfully connected to port {port_name}")
        else:
            self.comm = None
            messagebox.showerror("Error", f"Unable to connect to port: {port_name}!")

    def _disconnect(self):
        if self.comm:
            self.comm.disconnect()
            self.comm = None
        self.connected = False
        self.connect_btn.configure(text="🔌 Connect", fg_color="#d01b2e", hover_color="#b21424")
        self.status_label.configure(text="● Not connected", text_color="#d01b2e")
        self._log("🔌 Disconnected from COM port.")

    # ============================================================
    # FILE SELECTION
    # ============================================================
    def browse_bin_file(self):
        file_path = filedialog.askopenfilename(
            title="Select firmware .BIN file",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")],
        )
        if file_path:
            self.bin_path_var.set(file_path)
            self._log(f"Selected BIN file: {file_path}")

    def browse_csv_file(self):
        file_path = filedialog.askopenfilename(
            title="Select .CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if file_path:
            self.csv_path_var.set(file_path)
            self._log(f"Selected CSV file: {file_path}")

    # ============================================================
    # FIRMWARE UPDATE (BIN) HANDLING
    # ============================================================
    def start_bin_update(self):
        """Start firmware update process in background thread."""
        if not self.connected or not self.comm:
            messagebox.showwarning("Warning", "Please connect to a COM port first!")
            return

        bin_path = self.bin_path_var.get().strip().strip("\"'")
        if not bin_path:
            messagebox.showwarning("Warning", "Please select a .BIN file!")
            return

        if not os.path.exists(bin_path):
            messagebox.showerror("Error", f"File does not exist: {bin_path}")
            return

        tool_type = self.tool_type_var.get()

        # Disable button while running
        self.update_btn.configure(state="disabled", text="⏳ Updating...")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Progress: 0%")

        self.worker_thread = threading.Thread(
            target=self._bin_update_worker,
            args=(bin_path, tool_type),
            daemon=True,
        )
        self.worker_thread.start()

    def _bin_update_worker(self, bin_path: str, tool_type: str):
        """Worker thread: Generate script and auto-flash (no confirmation needed)."""
        try:
            self._log(f"\n{'='*60}")
            self._log(f"STARTING FIRMWARE UPDATE")
            self._log(f"   File: {bin_path}")
            self._log(f"   Tool: {tool_type}")
            self._log(f"{'='*60}")

            # 1. Generate command script
            script_data = generate_and_save_bin_script(
                bin_path, tool_type=tool_type, log_callback=self._log
            )

            if not script_data:
                self._log("Failed to generate command script!")
                return

            # 2. Automatically run flashing sequence (no confirmation)
            self._log("\nAutomatically starting update (no confirmation needed)...")
            execute_bin_flashing_sequence(
                self.comm,
                script_data,
                log_callback=self._log,
                progress_callback=self._update_progress,
            )

        except Exception as e:
            self._log(f"Error during update: {e}")
        finally:
            # Restore button
            self.after(0, self._reset_update_btn)

    def _update_progress(self, fraction: float, current: int, total: int):
        """Update progress bar (called from worker thread, safe via after)."""
        self.after(0, lambda: self._set_progress(fraction, current, total))

    def _set_progress(self, fraction: float, current: int, total: int):
        """Set progress bar value and label (runs on main thread)."""
        self.progress_bar.set(fraction)
        self.progress_label.configure(
            text=f"Progress: {int(fraction * 100)}% ({current}/{total} commands)"
        )

    def _reset_update_btn(self):
        self.update_btn.configure(state="normal", text="🚀 UPDATE FIRMWARE")
        self.progress_bar.set(1.0)
        self.progress_label.configure(text="Progress: 100% - Complete")

    # ============================================================
    # CSV COMMAND SENDING
    # ============================================================
    def start_csv_send(self):
        """Start CSV command sending in background thread."""
        if not self.connected or not self.comm:
            messagebox.showwarning("Warning", "Please connect to a COM port first!")
            return

        csv_path = self.csv_path_var.get().strip().strip("\"'")
        if not csv_path:
            messagebox.showwarning("Warning", "Please select a .CSV file!")
            return

        if not os.path.exists(csv_path):
            messagebox.showerror("Error", f"File does not exist: {csv_path}")
            return

        tool_type = self.csv_tool_type_var.get()

        # Disable button while running
        self.csv_send_btn.configure(state="disabled", text="⏳ Sending...")
        self.csv_progress_bar.set(0)
        self.csv_progress_label.configure(text="Progress: 0%")

        self.worker_thread = threading.Thread(
            target=self._csv_send_worker,
            args=(csv_path, tool_type),
            daemon=True,
        )
        self.worker_thread.start()

    def _csv_send_worker(self, csv_path: str, tool_type: str):
        """Worker thread: Filter CSV and send commands."""
        try:
            self._log(f"\n{'='*60}")
            self._log(f"SENDING CSV COMMANDS")
            self._log(f"   File: {csv_path}")
            self._log(f"   Tool: {tool_type}")
            self._log(f"{'='*60}")

            # Filter commands from CSV
            self._log(f"\nProcessing CSV data filter...")
            csv_cmds = get_commands_from_csv(csv_path, prefix="74", log_callback=self._log)

            if not csv_cmds:
                self._log("No matching commands found or file is empty!")
                return

            # Add 2 init commands
            init_cmds = []

            # Command 1: Target
            cmd1_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
            init_cmds.append(build_frame(cmd1_base))

            # Command 2: Metcopassword
            seq = SeqIdTracker(start=5)
            seq_id = seq.get_and_inc()
            cmd2_base = f"01 {seq_id} 0A 00 3B 33 33 33 33 33 33 33 33"
            init_cmds.append(build_frame(cmd2_base))

            full_cmds = init_cmds + csv_cmds

            self._log(f"Sending {len(full_cmds)} commands (2 init + {len(csv_cmds)} CSV commands)...")
            execute_command_list(
                self.comm,
                full_cmds,
                log_callback=self._log,
                progress_callback=self._csv_update_progress,
            )

        except Exception as e:
            self._log(f"Error during CSV sending: {e}")
        finally:
            self.after(0, self._reset_csv_btn)

    def _csv_update_progress(self, fraction: float, current: int, total: int):
        """Update CSV progress bar (called from worker thread, safe via after)."""
        self.after(0, lambda: self._set_csv_progress(fraction, current, total))

    def _set_csv_progress(self, fraction: float, current: int, total: int):
        """Set CSV progress bar value and label (runs on main thread)."""
        self.csv_progress_bar.set(fraction)
        self.csv_progress_label.configure(
            text=f"Progress: {int(fraction * 100)}% ({current}/{total} commands)"
        )

    def _reset_csv_btn(self):
        self.csv_send_btn.configure(state="normal", text="📤 SEND CSV COMMANDS")
        self.csv_progress_bar.set(1.0)
        self.csv_progress_label.configure(text="Progress: 100% - Complete")

    # ============================================================
    # MANUAL HEX SENDING
    # ============================================================
    def send_manual_hex(self):
        """Send a single hex command."""
        if not self.connected or not self.comm:
            messagebox.showwarning("Warning", "Please connect to a COM port first!")
            return

        hex_cmd = self.hex_entry.get().strip()
        if not hex_cmd:
            messagebox.showwarning("Warning", "Please enter a Hex string!")
            return

        # Disable button while sending
        self.hex_send_btn.configure(state="disabled", text="⏳ Sending...")

        self.worker_thread = threading.Thread(
            target=self._hex_send_worker,
            args=(hex_cmd,),
            daemon=True,
        )
        self.worker_thread.start()

    def _hex_send_worker(self, hex_cmd: str):
        """Worker thread: Send single hex command."""
        try:
            # self._log(f"\n{'='*60}")
            # self._log(f"⌨️ SENDING MANUAL HEX")
            # self._log(f"{'='*60}")
            execute_command_list(self.comm, [hex_cmd], log_callback=self._log)
        except Exception as e:
            self._log(f"Error sending Hex: {e}")
        finally:
            self.after(0, self._reset_hex_btn)

    def _reset_hex_btn(self):
        self.hex_send_btn.configure(state="normal", text="📤 SEND HEX")

    # ============================================================
    # QUICK COMMAND SENDING
    # ============================================================
    def send_quick_command(self, command_type: str):
        """Send a quick command and display the result in a popup window."""
        if not self.connected or not self.comm:
            messagebox.showwarning("Warning", "Please connect to a COM port first!")
            return

        # Define the commands (full frames with checksum)
        commands = {
            "fw_version": "01 00 03 00 0D 04 00 15",
            "mpbid": "01 00 03 00 04 05 00 0D",
            "fw_pn": "01 00 03 00 09 04 00 11",
            "calibration": "01 00 03 61 00 FA 01 5F",
            "target_m18": "70 01 01 01 00 73",
            "target_m12": "70 01 01 11 00 83",
            "metco_password": "01 01 0A 00 3B 33 33 33 33 33 33 33 33 01 DF",
        }

        if command_type not in commands:
            return

        full_cmd = commands[command_type]

        # Disable all quick command buttons while running
        self._set_quick_buttons_state("disabled")

        self.worker_thread = threading.Thread(
            target=self._quick_command_worker,
            args=(command_type, full_cmd),
            daemon=True,
        )
        self.worker_thread.start()

    def _set_quick_buttons_state(self, state: str):
        """Enable/disable all quick command buttons."""
        for btn in [
            self.cmd_fw_version_btn,
            self.cmd_mpbid_btn,
            self.cmd_fw_pn_btn,
            self.cmd_calibration_btn,
            self.cmd_target_m18_btn,
            self.cmd_target_m12_btn,
            self.cmd_metco_password_btn,
        ]:
            btn.configure(state=state)

    def _quick_command_worker(self, command_type: str, full_cmd: str):
        """Worker thread: Send quick command and process response."""
        try:
            self._log(f"\n{'='*60}")
            self._log(f"QUICK COMMAND: {command_type}")
            self._log(f"{'='*60}")

            rx = send_and_get_final_rx(self.comm, full_cmd, log_callback=self._log)

            if rx is None:
                self.after(0, lambda: self._show_result_window(
                    command_type, "Timeout or no response from MCU!"
                ))
                return

            first_byte = rx[0]

            if first_byte in (0x80, 0x81):
                # Show result
                result = self._parse_response(command_type, rx)
                self.after(0, lambda: self._show_result_window(command_type, result))
            elif first_byte in (0x82, 0x83):
                # Cannot get data
                self.after(0, lambda: self._show_result_window(
                    command_type, "Cannot get data"
                ))
            else:
                self.after(0, lambda: self._show_result_window(
                    command_type, f"Unexpected response: {rx.hex(' ').upper()}"
                ))

        except Exception as e:
            self._log(f"Error during quick command: {e}")
            self.after(0, lambda: self._show_result_window(command_type, f"Error: {e}"))
        finally:
            self.after(0, lambda: self._set_quick_buttons_state("normal"))

    def _parse_response(self, command_type: str, rx: bytes) -> str:
        """Parse the response data based on command type."""
        # Frame format: Header(1) + Seq(1) + Len(1) + Data(len) + Checksum(2)
        # Data starts at index 3, length is at index 2
        if len(rx) >= 3:
            data_len = rx[2]
            data = rx[3:3 + data_len]
        else:
            data = rx[3:]

        if command_type == "fw_pn":
            # Remove all spaces and convert into decimal
            hex_str = data.hex()
            dec_value = int(hex_str, 16)
            return f"FW P/N (Decimal): {dec_value}"
        else:
            return f"Data: {data.hex(' ').upper()}"

    def _show_result_window(self, command_type: str, result: str):
        """Display a small window with the data result."""
        title_map = {
            "fw_version": "Check FW Version",
            "mpbid": "Check MPBID",
            "fw_pn": "Check FW P/N",
            "calibration": "Read Data Calibration",
            "target_m18": "Target M18",
            "target_m12": "Target M12",
            "metco_password": "Send Default Metco Password",
        }
        title = title_map.get(command_type, command_type)

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("400x200")
        win.resizable(False, False)

        # Center the window
        win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 200) // 2
        win.geometry(f"+{x}+{y}")

        # Always on top + modal (blocks interaction with the main window
        # until this popup is closed)
        win.attributes("-topmost", True)
        win.lift()
        win.focus_force()
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(
            win,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            win,
            text=result,
            font=ctk.CTkFont(size=14),
            wraplength=350,
            justify="center",
        ).pack(pady=10, padx=20)

        ctk.CTkButton(
            win,
            text="OK",
            width=100,
            command=win.destroy,
        ).pack(pady=15)

    # ============================================================
    # TEMP FOLDER CLEANUP
    # ============================================================
    def cleanup_temp_folder(self):
        """Delete the temp folder and all its contents."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            temp_dir = os.path.join(script_dir, "temp")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                self._log("Temp folder deleted successfully.")
        except Exception as e:
            self._log(f"Unable to delete temp folder: {e}")

    # ============================================================
    # CLOSE APPLICATION
    # ============================================================
    def on_close(self):
        """Handle window close."""
        if self.connected and self.comm:
            self.comm.disconnect()
        self.cleanup_temp_folder()
        self.destroy()


def main():
    app = SwUpdateApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()