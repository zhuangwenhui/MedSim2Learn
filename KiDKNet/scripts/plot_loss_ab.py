import json, os, sys, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
DF=sys.argv[1] if len(sys.argv)>1 else "/workspace/project/MedSim2Learn/DataFlow/KiDKNet"
CONDS=(sys.argv[2].split(",") if len(sys.argv)>2 else ["c1","c3"])
FIX,UNC=os.path.join(DF,"outputs/cv5"),os.path.join(DF,"outputs/cv5_unc")
OUT=os.path.join(UNC,"report/rq3_loss_ab.png"); REAL_ONLY={"c3","c7"}; GREY,PURP="#8C8C8C","#8172B3"
def met(p,c,k):
    if not os.path.exists(p): return None
    s=json.load(open(p)); ro=s.get("real_only_slice") or {}
    src=ro if (c in REAL_ONLY and ro and k in ro) else s["pooled"]; return src[k]["mean"],src[k]["std"]
rows=[]
for c in CONDS:
    f=met(os.path.join(FIX,c,"cross_fold_summary.json"),c,"magnitude_mean_absolute_error")
    u=met(os.path.join(UNC,c,"cross_fold_summary.json"),c,"magnitude_mean_absolute_error")
    if f and u: rows.append((c,f,u))
if not rows: print("[rq3] no condition with both fixed+unc yet"); sys.exit(0)
os.makedirs(os.path.dirname(OUT),exist_ok=True)
x=np.arange(len(rows)); w=0.36; fig,ax=plt.subplots(figsize=(4+1.8*len(rows),5))
fm=[r[1][0] for r in rows]; fs=[r[1][1] for r in rows]; um=[r[2][0] for r in rows]; us=[r[2][1] for r in rows]
ax.bar(x-w/2,fm,w,yerr=fs,capsize=4,color=GREY,edgecolor="black",lw=.5,label="fixed-lambda")
ax.bar(x+w/2,um,w,yerr=us,capsize=4,color=PURP,edgecolor="black",lw=.5,label="learned uncertainty")
for i in range(len(rows)):
    ax.text(x[i]-w/2,fm[i]+fs[i],"%.3f"%fm[i],ha="center",va="bottom",fontsize=8)
    ax.text(x[i]+w/2,um[i]+us[i],"%.3f"%um[i],ha="center",va="bottom",fontsize=8)
ax.set_xticks(x); ax.set_xticklabels([r[0] for r in rows]); ax.set_ylabel("magnitude MAE (real-comparable, lower better)")
ax.set_title("RQ3: fixed-lambda vs learned-uncertainty loss weighting\n(5-fold CV, error bars = fold std)",fontsize=10)
ax.legend(fontsize=9); ax.grid(axis="y",alpha=.25); fig.savefig(OUT,dpi=140,bbox_inches="tight")
print("[fig] wrote",OUT)
for c,f,u in rows: print("  %s magMAE fixed %.4f+/-%.4f -> unc %.4f+/-%.4f (dMean %+.4f, dStd %+.4f)"%(c,f[0],f[1],u[0],u[1],u[0]-f[0],u[1]-f[1]))
