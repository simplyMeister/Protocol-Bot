import pandas as pd
import os

def compare_excels():
    files = ["Book1.xlsx", "protocol data.xlsx"]
    for file in files:
        if not os.path.exists(file):
            print(f"Error: {file} not found.")
            continue
        
        try:
            df = pd.read_excel(file)
            print(f"\n--- {file} ---")
            print("Columns:", df.columns.tolist())
            if not df.empty:
                print("First row:", df.iloc[0].to_dict())
            else:
                print("File is empty.")
        except Exception as e:
            print(f"Error reading {file}: {e}")

if __name__ == "__main__":
    compare_excels()
