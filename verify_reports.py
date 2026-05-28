import sys
import os
import datetime

# Add root to path
sys.path.append(os.path.dirname(os.path.abspath(__name__)))

from modules.reports import generate_daily_report

def test_reports():
    mock_common = {
        "prepared_by": "Test User",
        "service_overview": "The service flowed smoothly with high engagement.",
        "challenges": "Minor issues with equipment at the start.",
        "workflow_suggestions": "Check equipment 30 mins earlier.",
        "assignments": {
            "Entrance Allocation": ["John Doe", "Jane Smith"],
            "Tag Allocation": ["Alice Brown"],
            "Counting": ["Bob Wilson"],
            "Tag Collection": ["Charlie Davis"]
        }
    }

    days_to_test = [
        ("Thursday", {**mock_common, "male": 35, "female": 55, "total": 90}),
        ("Sunday",   {**mock_common, "male": 40, "female": 60, "total": 100}),
        ("Tuesday",  {**mock_common, "male": 25, "female": 35, "total": 60}),
        ("Friday",   {**mock_common, "male": 20, "female": 30, "total": 50}),
        ("Saturday", {
            **mock_common,
            "general_meeting": {"male": 10, "female": 15, "total": 25},
            "chaplaincy_meeting": {"male": 5, "female": 5, "total": 10},
            "chop": {"male": 8, "female": 12, "total": 20},
            "word_feast": {"male": 15, "female": 20, "total": 35}
        })
    ]

    for day, data in days_to_test:
        print(f"\n--- Testing {day} ---")
        data["day_name"] = day
        try:
            path = generate_daily_report(data)
            print(f"Success! Report saved to: {path}")
        except Exception as e:
            print(f"Failed to generate {day} report: {e}")

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    test_reports()
