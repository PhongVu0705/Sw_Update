from csv_processor import export_filtered_csv
from opelink_comm import OpenLinkComm, select_port

def main():
    while True:
        try:
            input_csv_path = input("Enter input CSV file path: ")
            output_csv_path = input("Enter output CSV file path: ")
            # extracted_messages = extract_messages(input_csv_path, prefix="74")
            # print(f"Extracted {len(extracted_messages)} messages starting with '74'.")

            export_filtered_csv(input_csv_path, output_csv_path, prefix="74", message_only=True)
            break
        except FileNotFoundError:
            print(f"File not found: {input_csv_path}. Please try again.")
        except Exception as e:
            print(f"An error occurred while processing the CSV file: {e}")
    
        
if __name__ == "__main__":
    main()