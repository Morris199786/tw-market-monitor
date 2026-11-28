"""Conservative reconciliation of public 13F holdings, not actual trades."""
from collections import defaultdict
def flag(v):
 return str(v or "").strip().upper() in ("Y","YES","TRUE","1")
def amendment(v):
 v=" ".join(str(v or "").upper().split())
 if v=="RESTATEMENT":return "replace"
 if v in ("NEW HOLDINGS","NEW HOLDINGS ENTRIES"):return "add"
 return None
def reconcile(entries):
 """Entries sorted by amendment number; never infer missing amendment types."""
 base=[e for e in entries if not e["form"].endswith("/A")]
 mods=[e for e in entries if e["form"].endswith("/A")]
 if len(base)!=1:return None,"ambiguous_original"
 if any(amendment(e.get("amendment_type")) is None or not str(e.get("amendment_number") or "").isdigit() for e in mods):return None,"unknown_amendment"
 mods.sort(key=lambda e:int(e["amendment_number"]))
 if [int(e["amendment_number"]) for e in mods]!=list(range(1,len(mods)+1)):return None,"amendment_sequence"
 state=dict(base[0]["positions"]); complete=base[0].get("absence_safe",False); last=base[0]
 for e in mods:
  typ=amendment(e["amendment_type"])
  if typ=="replace":state=dict(e["positions"]);complete=e.get("absence_safe",False)
  else:
   # A supplemental report can add entries for the same security.
   # Do not combine overlapping CUSIPs without line-level reconciliation.
   if state.keys() & e["positions"].keys():return None,"overlapping_supplement"
   state.update(e["positions"]);complete=complete and e.get("absence_safe",False)
  last=e
 return dict(positions=state,absence_safe=complete,last=last),"ok"

def compare(old,new,cusip):
 a=old["positions"].get(cusip);b=new["positions"].get(cusip)
 if a is None and b is None:return None
 if a is None:
  if not old["absence_safe"]:return None
  return (0,b,"newly_reported")
 if b is None:
  if not new["absence_safe"]:return None
  return (a,0,"no_longer_reported")
 return (a,b,"paired")
