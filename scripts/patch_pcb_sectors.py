#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("data/sectors.json")
d = json.loads(p.read_text(encoding="utf-8"))

replacement = [{'name': 'PCB', 'stocks': [{'ticker': '2313', 'name': '華通'}, {'ticker': '2316', 'name': '楠梓電'}, {'ticker': '2368', 'name': '金像電'}, {'ticker': '3044', 'name': '健鼎'}, {'ticker': '3715', 'name': '定穎投控'}, {'ticker': '5439', 'name': '高技'}, {'ticker': '5469', 'name': '瀚宇博'}, {'ticker': '6191', 'name': '精成科'}, {'ticker': '8155', 'name': '博智'}, {'ticker': '2493', 'name': '揚博'}, {'ticker': '6727', 'name': '亞泰金屬'}, {'ticker': '7795', 'name': '長廣'}, {'ticker': '8021', 'name': '尖點'}, {'ticker': '3498', 'name': '陽程'}], 'subgroups': [{'name': 'PCB 板廠', 'tickers': ['2313', '2316', '2368', '3044', '3715', '5439', '5469', '6191', '8155']}, {'name': 'PCB 設備／耗材', 'tickers': ['2493', '6727', '7795', '8021', '3498']}]}, {'name': 'ABF', 'stocks': [{'ticker': '3037', 'name': '欣興'}, {'ticker': '3189', 'name': '景碩'}, {'ticker': '8046', 'name': '南電'}, {'ticker': '4958', 'name': '臻鼎-KY'}]}, {'name': '銅箔／CCL', 'stocks': [{'ticker': '4989', 'name': '榮科'}, {'ticker': '8358', 'name': '金居'}, {'ticker': '1303', 'name': '南亞'}, {'ticker': '2383', 'name': '台光電'}, {'ticker': '6213', 'name': '聯茂'}, {'ticker': '6274', 'name': '台燿'}, {'ticker': '6672', 'name': '騰輝電子-KY'}, {'ticker': '8039', 'name': '台虹'}], 'subgroups': [{'name': '銅箔', 'tickers': ['4989', '8358']}, {'name': 'CCL', 'tickers': ['1303', '2383', '6213', '6274', '6672', '8039']}]}, {'name': '玻纖布／玻纖紗', 'stocks': [{'ticker': '1802', 'name': '台玻'}, {'ticker': '1815', 'name': '富喬'}, {'ticker': '5340', 'name': '建榮'}, {'ticker': '5475', 'name': '德宏'}]}]

out = []
replaced = False
for sec in d.get("sectors", []):
    if sec.get("name") == "PCB／ABF／CCL":
        out.extend(replacement)
        replaced = True
    else:
        out.append(sec)

if not replaced:
    # 若已改過，不重複插入；確認四個新族群存在即可
    names = {x.get("name") for x in out}
    if not {"PCB","ABF","銅箔／CCL","玻纖布／玻纖紗"}.issubset(names):
        raise SystemExit("找不到 PCB／ABF／CCL，且新分類不完整，停止修改")

d["sectors"] = out
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("OK:", len(out), "sectors")
for name in ("PCB","ABF","銅箔／CCL","玻纖布／玻纖紗"):
    s = next(x for x in out if x.get("name") == name)
    print(name, len(s.get("stocks", [])), "檔")
