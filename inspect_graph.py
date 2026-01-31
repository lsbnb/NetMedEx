#!/usr/bin/env python
"""
檢查最新生成的圖形文件，查看邊的數據結構
"""
import pickle
import glob
from pathlib import Path

# 找到最新的 G.pkl
pkl_files = glob.glob("/home/cylin/NetMedEx/webapp-temp/*/G.pkl")
if not pkl_files:
    print("未找到 G.pkl 文件")
    exit(1)

latest_pkl = max(pkl_files, key=lambda x: Path(x).stat().st_mtime)
print(f"檢查文件: {latest_pkl}\n")

# 加載圖形
with open(latest_pkl, 'rb') as f:
    G = pickle.load(f)

print(f"圖形統計:")
print(f"  節點數: {G.number_of_nodes()}")
print(f"  邊數: {G.number_of_edges()}\n")

# 檢查邊的屬性
print("邊的屬性:")
for i, (u, v, data) in enumerate(G.edges(data=True), 1):
    print(f"\n邊 {i}: {u} <-> {v}")
    print(f"  屬性: {list(data.keys())}")
    for key, value in data.items():
        if key == 'pmids':
            print(f"    {key}: {value[:3] if len(value) > 3 else value}...")
        elif key == 'relations':
            print(f"    {key}: {value[:3] if len(value) > 3 else value}...")
        else:
            print(f"    {key}: {value}")
    if i >= 3:  # 只顯示前3條邊
        break

print(f"\n總共檢查了 {min(3, G.number_of_edges())} 條邊")
