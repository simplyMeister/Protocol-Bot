from openpyxl import Workbook
import os

def create_dummy_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Members"
    
    # Headers
    ws.append(["Name", "College", "Hall"])
    
    # Dummy Data
    data = [
        ("David Oyedepo", "COE", "Daniel"),     # Tuesday, Alpha
        ("Faith Oyedepo", "CLDS", "Joseph"),    # Tuesday, Omega
        ("Abioye David", "CST", "Paul"),        # Thursday, Alpha
        ("Isaac Oyedepo", "CMSS", "Mary"),      # Thursday, Omega
        ("Thomas Aremu", "COE", "Esther"),      # Tuesday, Alpha
        ("David Ibiyeomie", "CST", "Deborah"),  # Thursday, Omega
        ("Paul Enenche", "CLDS", "Daniel"),     # Tuesday, Alpha
        ("Sam Adeyemi", "CMSS", "Joseph")       # Thursday, Omega
    ]
    
    for row in data:
        ws.append(row)
        
    path = os.path.join("data", "members.xlsx")
    wb.save(path)
    print(f"Created {path}")

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    create_dummy_excel()
