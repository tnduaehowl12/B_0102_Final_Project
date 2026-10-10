#!/usr/bin/env python3
# latency_check.py -p csv:=... 로 남긴 CSV(t_recv,topic,delay_ms) → 지연·수신율 그래프 PNG
#   python3 plot_latency.py ~/scv_logs/2026-10-10_robot3_latency.csv out.png
import sys
from collections import Counter, defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

src, out = sys.argv[1], sys.argv[2]
data = defaultdict(list)
for line in open(src):
    t, topic, d = line.strip().split(',')
    data[topic].append((float(t), float(d)))
t0 = min(v[0][0] for v in data.values())

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
for topic, rows in sorted(data.items()):
    t = [r[0] - t0 for r in rows]
    d = sorted(r[1] for r in rows)
    label = f'{topic}: mean {sum(d) / len(d):.0f} / p95 {d[int(0.95 * (len(d) - 1))]:.0f} / max {d[-1]:.0f} ms (n={len(d)})'
    ax1.plot(t, [r[1] for r in rows], '.', ms=2, label=label)
    hz = Counter(int(x) for x in t)
    secs = sorted(hz)[:-1]   # 마지막 1초는 덜 찬 구간이라 뺌
    ax2.plot(secs, [hz[k] for k in secs], '-', label=topic)
ax1.set_ylabel('delay (ms) = recv - header.stamp')
ax1.legend(loc='upper right')
ax2.set_ylabel('msgs / 1 s')
ax2.set_xlabel('time (s)')
ax2.legend(loc='lower right')
fig.suptitle(src.split('/')[-1])
fig.tight_layout()
fig.savefig(out, dpi=110)
print(out)
