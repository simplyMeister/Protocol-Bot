import sys
import os
import datetime
import json

# Add root to path
sys.path.append(os.path.dirname(os.path.abspath(__name__)))

from modules.attendance import generate_weekly_roster, get_next_service_dates

def test_roster_fairness():
    present_members = ["User1", "User2", "User3", "User4", "User5", "User6", "User7", "User8"]
    all_members_data = {m: {"name": m, "college": "COE", "hall": "Daniel"} for m in present_members}
    
    # 1. Test Date Calculation
    dates = get_next_service_dates()
    print("Next Service Dates:")
    for service, date in dates.items():
        print(f"  {service}: {date}")
    
    # 2. Test First Roster (Empty History)
    history = {}
    roster1 = generate_weekly_roster(present_members, all_members_data, history)
    
    # Extract people who served in Thursday Chapel
    thu_assigned = roster1["Thursday Chapel"]["Entrance Allocation"] + \
                   roster1["Thursday Chapel"]["Tag Allocation"] + \
                   roster1["Thursday Chapel"]["Counting"] + \
                   roster1["Thursday Chapel"]["Tag Collection"]
    
    print(f"\nWeek 1 Thursday Assigned: {thu_assigned}")
    
    # 3. Test Second Roster (With history from Week 1)
    history["Thursday Chapel"] = thu_assigned
    roster2 = generate_weekly_roster(present_members, all_members_data, history)
    
    thu_assigned_2 = roster2["Thursday Chapel"]["Entrance Allocation"] + \
                     roster2["Thursday Chapel"]["Tag Allocation"] + \
                     roster2["Thursday Chapel"]["Counting"] + \
                     roster2["Thursday Chapel"]["Tag Collection"]
    
    print(f"Week 2 Thursday Assigned: {thu_assigned_2}")
    
    # Check for overlaps
    overlap = set(thu_assigned) & set(thu_assigned_2)
    if overlap:
        print(f"Warning: Overlap found: {overlap} (This is okay if total pool is small, but check distribution)")
    else:
        print("Success! No overlap in consecutive weeks for the same service.")

if __name__ == "__main__":
    test_roster_fairness()
