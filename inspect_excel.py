import pandas as pd
import os

def inspect_excel():
    path = "protocol data.xlsx"
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return
    
    try:
        df = pd.read_excel(path)
        print("Headers:", df.columns.tolist())
        print("First 5 rows:")
        print(df.head())
    except Exception as e:
        print(f"Error reading excel: {e}")

if __name__ == "__main__":
    inspect_excel()
