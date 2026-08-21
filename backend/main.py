import os
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
        print("Không chọn cổng COM. Dừng chương trình.")
        return

    port_name = selected_port["port"]
    comm = OpenLinkComm(
        port=port_name,
        baud_rate=115200,
        on_rx=on_rx_callback,
        on_tx=on_tx_callback,
    )

    if not comm.connect():
        print(f"Không thể kết nối cổng: {port_name}!")
        return

    print(f"\n✅ Kết nối thành công cổng {port_name}")

    try:
        while True:
            print_queued_messages()
            print("\n================ CHỌN CHỨC NĂNG ================")
            print("1. Nhập file .BIN để nạp Firmware (Tạo Script TXT -> Xác nhận Update)")
            print("2. Nhập file .CSV tập lệnh để gửi đơn thuần")
            print("3. Nhập trực tiếp chuỗi Hex gửi thủ công")
            print("q. Thoát chương trình")
            
            choice = input("\n[LỰA CHỌN] > ").strip().strip("\"'")

            if choice.lower() in ["q", "exit"]:
                print("Đang thoát...")
                break

            # OPTION 1: NẠP TỪ FILE BIN
            if choice == "1" or choice.lower().endswith(".bin"):
                bin_path = choice if choice.lower().endswith(".bin") else input("👉 Nhập đường dẫn file .BIN: ").strip().strip("\"'")
                if not os.path.exists(bin_path):
                    print(f"❌ File không tồn tại: {bin_path}")
                    continue

                tool_choice = input("👉 Chọn Tool (M12/M18) [Default: M12]: ").strip().upper()
                tool_type = "M18" if tool_choice == "M18" else "M12"

                # Sinh kịch bản lệnh bằng script_builder
                script_data = generate_and_save_bin_script(bin_path, tool_type=tool_type)

                if script_data:
                    confirm = input("\n❓ Bạn có muốn UPDATE vào Tool bằng tập lệnh này không? (Y/N): ").strip().upper()
                    if confirm in ["Y", "YES"]:
                        # Chạy chuỗi lệnh Flashing
                        execute_bin_flashing_sequence(comm, script_data)
                    else:
                        print("⏸️ Đã hủy tiến trình Update.")

            # OPTION 2: NẠP TỪ FILE CSV
            elif choice == "2" or choice.lower().endswith(".csv"):
                csv_path = choice if choice.lower().endswith(".csv") else input("👉 Nhập đường dẫn file .CSV: ").strip().strip("\"'")
                if not os.path.exists(csv_path):
                    print(f"❌ File không tồn tại: {csv_path}")
                    continue

                # Hỏi người dùng chọn Tool để quyết định lệnh Target
                tool_choice = input("👉 Chọn Tool (M12/M18) [Default: M12]: ").strip().upper()
                tool_type = "M18" if tool_choice == "M18" else "M12"

                print(f"\n🔄 Đang xử lý lọc dữ liệu CSV từ: {csv_path}...")
                
                # Gọi hàm xử lý trọn gói từ csv_processor
                csv_cmds = get_commands_from_csv(csv_path, prefix="74")

                if not csv_cmds:
                    print("⚠️ Không tìm thấy lệnh phù hợp hoặc file rỗng!")
                    continue

                # --- THÊM 2 LỆNH KHỞI TẠO TRƯỚC KHI GỬI CSV ---
                init_cmds = []
                
                # Lệnh 1: Target
                cmd1_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
                init_cmds.append(build_frame(cmd1_base))

                # Lệnh 2: Metcopassword (Sử dụng SeqIdTracker bắt đầu từ 05 vì lệnh 1 đã dùng 01)
                seq = SeqIdTracker(start=5)
                seq_id = seq.get_and_inc()
                cmd2_base = f"01 {seq_id} 0A 00 3B 33 33 33 33 33 33 33 33"
                init_cmds.append(build_frame(cmd2_base))

                # Ghép 2 lệnh khởi tạo vào trước danh sách lệnh CSV
                full_cmds = init_cmds + csv_cmds

                print(f"🚀 Bắt đầu gửi {len(full_cmds)} lệnh (2 lệnh Khởi tạo + {len(csv_cmds)} lệnh CSV)...")
                
                # Chạy toàn bộ danh sách lệnh
                execute_command_list(comm, full_cmds)

            # OPTION 3: NHẬP LỆNH HEX ĐƠN LẺ
            else:
                execute_command_list(comm, [choice])

    except KeyboardInterrupt:
        print("\nĐã hủy bởi người dùng.")
    except Exception as e:
        print(f"\nĐã xảy ra lỗi: {e}")
    finally:
        comm.disconnect()
        print("🔌 Đã ngắt kết nối cổng COM.")


if __name__ == "__main__":
    main()