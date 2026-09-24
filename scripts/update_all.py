import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(name):
    print("\\n==",name,"==")
    subprocess.check_call([sys.executable,str(ROOT/"scripts"/name)])
if __name__=="__main__":
    for f in ["update_master.py","update_close.py","update_institutional.py","update_ai.py"]:
        run(f)
