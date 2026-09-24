from sources import *
def main():
    master=fetch_master()
    save_json(ROOT/"data/master.json",{
        "updated_at":now_tpe().isoformat(timespec="minutes"),
        "count":len(master),"stocks":master
    })
    print("master",len(master))
if __name__=="__main__": main()
