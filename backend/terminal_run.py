import os
import shutil
from opelink_comm import OpenLinkComm, select_port
from csv_processor import get_commands_from_csv
from command_runner import (
    on_rx_callback, 
    on_tx_callback, 
    print_queued_messages,
    execute_command_list, 
    execute_bin_flashing_sequence
)
from script_builder import generate_and_save_bin_script, SeqIdTracker, build_frame

def main():
    selected_port = select_port()
    if not selected_port:
        print("No COM port selected. Stopping program.")
        return

    port_name = selected_port["port"]
    comm = OpenLinkComm(
        port=port_name,
        baud_rate=115200,
        on_rx=on_rx_callback,
        on_tx=on_tx_callback,
    )

    if not comm.connect():
        print(f"Unable to connect to port: {port_name}!")
        return

    print(f"\n✅ Successfully connected to port {port_name}")

    try:
        while True:
            print_queued_messages()
            print("\n================ SELECT FUNCTION ================")
            print("1. Load .BIN file to flash Firmware (Generate TXT Script -> Auto Update)")
            print("2. Load .CSV command file to send commands")
            print("3. Enter Hex string manually")
            print("q. Exit program")
            
            choice = input("\n[CHOICE] > ").strip().strip("\"'")

            if choice.lower() in ["q", "exit"]:
                print("Exiting...")
                break

            # OPTION 1: LOAD FROM BIN FILE
            if choice == "1" or choice.lower().endswith(".bin"):
                bin_path = choice if choice.lower().endswith(".bin") else input("👉 Enter .BIN file path: ").strip().strip("\"'")
                if not os.path.exists(bin_path):
                    print(f"❌ File does not exist: {bin_path}")
                    continue

                tool_choice = input("👉 Select Tool (M12/M18) [Default: M12]: ").strip().upper()
                tool_type = "M18" if tool_choice == "M18" else "M12"

                # Generate command script using script_builder
                script_data = generate_and_save_bin_script(bin_path, tool_type=tool_type)

                if script_data:
                    # Run flashing sequence (auto update, no confirmation needed)
                    execute_bin_flashing_sequence(comm, script_data)

            # OPTION 2: LOAD FROM CSV FILE
            elif choice == "2" or choice.lower().endswith(".csv"):
                csv_path = choice if choice.lower().endswith(".csv") else input("👉 Enter .CSV file path: ").strip().strip("\"'")
                if not os.path.exists(csv_path):
                    print(f"❌ File does not exist: {csv_path}")
                    continue

                # Ask user to select Tool to determine Target command
                tool_choice = input("👉 Select Tool (M12/M18) [Default: M12]: ").strip().upper()
                tool_type = "M18" if tool_choice == "M18" else "M12"

                print(f"\n🔄 Processing CSV data filter from: {csv_path}...")
                
                # Call full processing function from csv_processor
                csv_cmds = get_commands_from_csv(csv_path, prefix="74")

                if not csv_cmds:
                    print("⚠️ No matching commands found or file is empty!")
                    continue

                # --- ADD 2 INIT COMMANDS BEFORE SENDING CSV ---
                init_cmds = []
                
                # Command 1: Target
                cmd1_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
                init_cmds.append(build_frame(cmd1_base))

                # Command 2: Metcopassword (Use SeqIdTracker starting at 05 because command 1 used 01)
                seq = SeqIdTracker(start=5)
                seq_id = seq.get_and_inc()
                cmd2_base = f"01 {seq_id} 0A 00 3B 33 33 33 33 33 33 33 33"
                init_cmds.append(build_frame(cmd2_base))

                # Combine 2 init commands before the CSV command list
                full_cmds = init_cmds + csv_cmds

                print(f"🚀 Sending {len(full_cmds)} commands (2 init + {len(csv_cmds)} CSV commands)...")
                
                # Run the full command list
                execute_command_list(comm, full_cmds)

            # OPTION 3: ENTER SINGLE HEX COMMAND
            else:
                execute_command_list(comm, [choice])

    except KeyboardInterrupt:
        print("\nCancelled by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        comm.disconnect()
        print("🔌 Disconnected from COM port.")
        cleanup_temp_folder()


def cleanup_temp_folder():
    """Delete the temp folder and all its contents."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        temp_dir = os.path.join(script_dir, "temp")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print("Temp folder deleted successfully.")
    except Exception as e:
        print(f"Unable to delete temp folder: {e}")


if __name__ == "__main__":
    main()