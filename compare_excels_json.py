import pandas as pd
import os
import json
import datetime

def compare_excels():
    files = ["Book1.xlsx", "protocol data.xlsx"]
    results = {}
    for file in files:
        if not os.path.exists(file):
            results[file] = "Not found"
            continue
        
        try:
            df = pd.read_excel(file)
            cols = df.columns.tolist()
            # Convert non-serializable objects (like Timestamp) to strings
            if isinstance(first_row, dict):
                first_row = {
                    k: (str(v) if isinstance(v, (pd.Timestamp, datetime.date, datetime.datetime)) else (None if pd.isna(v) else v))
                    for k, v in first_row.items()
                }
            
            results[file] = {
                "columns": cols,
                "first_row": first_row
            }
        except Exception as e:
            results[file] = f"Error: {str(e)}"

    with open("excel_comparison.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    compare_excels()
