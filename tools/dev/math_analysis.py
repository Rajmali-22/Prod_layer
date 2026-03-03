import json
from datetime import datetime

# Load keylog data
with open('data/keylog.json', 'r') as f:
    data = json.load(f)

# Calculate time differences
time_diffs = []
for i in range(1, len(data)):
    t1 = datetime.fromisoformat(data[i-1]['timestamp'])
    t2 = datetime.fromisoformat(data[i]['timestamp'])
    diff = (t2 - t1).total_seconds()
    if diff < 60:  # Filter extreme outliers
        time_diffs.append(diff)

# Calculate 10-key moving average
moving_avg = []
for i in range(len(time_diffs)):
    start = max(0, i - 9)
    avg = sum(time_diffs[start:i+1]) / len(time_diffs[start:i+1])
    moving_avg.append(avg)

# Count triggers
fixed_2sec_triggers = sum(1 for d in time_diffs if d > 2)
moving_avg_triggers = sum(1 for i, d in enumerate(time_diffs) if d > moving_avg[i])

# Calculate improvement
reduction = fixed_2sec_triggers - moving_avg_triggers
percent_reduction = (reduction / fixed_2sec_triggers) * 100 if fixed_2sec_triggers > 0 else 0

# API calls saved (assuming each trigger = 1 API call)
# If avg API cost = $0.01 per call
api_cost_fixed = fixed_2sec_triggers * 0.01
api_cost_moving = moving_avg_triggers * 0.01
cost_saved = api_cost_fixed - api_cost_moving

print("=" * 50)
print("MATHEMATICAL COMPARISON")
print("=" * 50)
print(f"\nTotal keystrokes analyzed: {len(time_diffs)}")
print(f"\n--- TRIGGER COUNT ---")
print(f"Fixed 2 sec threshold:    {fixed_2sec_triggers} triggers")
print(f"10-key moving average:    {moving_avg_triggers} triggers")
print(f"\n--- IMPROVEMENT ---")
print(f"Reduction:                {reduction} fewer triggers")
print(f"Improvement:              {percent_reduction:.1f}%")
print(f"\n--- COST ANALYSIS (at $0.01/call) ---")
print(f"Fixed method cost:        ${api_cost_fixed:.2f}")
print(f"Moving avg cost:          ${api_cost_moving:.2f}")
print(f"Cost saved:               ${cost_saved:.2f}")
print(f"\n--- EFFICIENCY RATIO ---")
print(f"Moving avg is {fixed_2sec_triggers/moving_avg_triggers:.2f}x more efficient")
print("=" * 50)
