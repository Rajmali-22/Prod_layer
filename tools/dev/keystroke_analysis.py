import json
from datetime import datetime
import matplotlib.pyplot as plt

# Load keylog data
with open('data/keylog.json', 'r') as f:
    data = json.load(f)

# Calculate time differences between consecutive keystrokes
timestamps = []
time_diffs = []

for i in range(1, len(data)):
    t1 = datetime.fromisoformat(data[i-1]['timestamp'])
    t2 = datetime.fromisoformat(data[i]['timestamp'])
    diff = (t2 - t1).total_seconds()

    # Filter out very long pauses (> 60 sec) for better visualization
    if diff < 60:
        timestamps.append(i)
        time_diffs.append(diff)

# Calculate 10-key moving average
moving_avg = []
for i in range(len(time_diffs)):
    start = max(0, i - 9)
    avg = sum(time_diffs[start:i+1]) / len(time_diffs[start:i+1])
    moving_avg.append(avg)

# Create the graph
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))

# Plot 1: Time differences
ax1.bar(timestamps, time_diffs, color='steelblue', alpha=0.7, label='Time Diff (sec)')
ax1.axhline(y=2, color='red', linestyle='--', linewidth=2, label='2 sec threshold')
ax1.set_xlabel('Keystroke Index')
ax1.set_ylabel('Time Difference (seconds)')
ax1.set_title('Time Between Keystrokes')
ax1.legend()
ax1.set_ylim(0, 30)

# Plot 2: Moving average comparison
ax2.plot(timestamps, time_diffs, 'b-', alpha=0.5, label='Actual Time Diff')
ax2.plot(timestamps, moving_avg, 'orange', linewidth=2, label='10-Key Moving Avg')
ax2.axhline(y=2, color='red', linestyle='--', linewidth=2, label='2 sec threshold')
ax2.set_xlabel('Keystroke Index')
ax2.set_ylabel('Time (seconds)')
ax2.set_title('Time Diff vs 10-Key Moving Average')
ax2.legend()
ax2.set_ylim(0, 30)

plt.tight_layout()
plt.savefig('data/keystroke_analysis.png', dpi=150)
plt.show()

# Print basic stats
print(f"\n=== Keystroke Analysis ===")
print(f"Total keystrokes: {len(data)}")
print(f"Avg time between keys: {sum(time_diffs)/len(time_diffs):.2f} sec")
print(f"Pauses > 2 sec: {sum(1 for d in time_diffs if d > 2)}")
print(f"Pauses > moving avg: {sum(1 for i, d in enumerate(time_diffs) if d > moving_avg[i])}")
