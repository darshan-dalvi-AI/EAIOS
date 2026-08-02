"""Generate DYD Technologies' structured data.

One script so every file agrees with every other: the incident that breaches an
SLA is the incident the credit note references, and the hours on a timesheet are
the hours that make a project's margin what the P&L says it is. Cross-app
questions are only impressive if the numbers reconcile.
"""
import csv, random, datetime as dt, os
random.seed(20260805)
OUT = "/tmp/dyd/out"
os.makedirs(OUT, exist_ok=True)

def w(name, header, rows):
    with open(f"{OUT}/{name}", "w", newline="", encoding="utf-8") as f:
        c = csv.writer(f); c.writerow(header); c.writerows(rows)
    print(f"{name}: {len(rows)} rows")

# ── clients ───────────────────────────────────────────────────────────────
CLIENTS = [
    # id, name, industry, engagement, mrr, start, end, tier, uptime, credit%, cap%, csat
    ("C01","Northwind Retail","Retail","Managed Services",1850000,"2025-04-01","2027-03-31","Platinum",99.90,5.0,15,4.1),
    ("C02","Meridian Bank","BFSI","Project + AMC",3200000,"2025-07-01","2027-06-30","Platinum",99.95,7.5,20,4.6),
    ("C03","Halcyon Health","Healthcare","Managed Services",1450000,"2026-01-01","2027-12-31","Gold",99.50,3.0,10,4.4),
    ("C04","Vertex Logistics","Logistics","Staff Augmentation",980000,"2025-10-01","2026-09-30","Silver",99.00,2.0,10,3.4),
    ("C05","Aurora Energy","Energy","Fixed-price Project",2400000,"2026-02-01","2027-01-31","Gold",99.50,3.0,10,4.2),
]
w("10_clients_contracts.csv",
  ["client_id","client_name","industry","engagement_type","mrr_inr","contract_start","contract_end",
   "sla_tier","uptime_target_pct","service_credit_pct_per_breach","credit_cap_pct_of_monthly","csat_score"],
  CLIENTS)

# ── projects ──────────────────────────────────────────────────────────────
PROJECTS = [
    ("P01","Northwind OMS Modernisation","C01","Application Development","2025-04-15","2026-10-31","Amber",18500000,14900000,"Rohan Deshpande",22),
    ("P02","Northwind 24x7 NOC","C01","Managed Services","2025-04-01","2027-03-31","Green",22200000,15400000,"Sneha Kulkarni",31),
    ("P03","Meridian Core Banking Migration","C02","Cloud Migration","2025-07-15","2026-12-31","Red",42000000,38600000,"Rohan Deshpande",9),
    ("P04","Meridian Payments API","C02","Application Development","2026-01-10","2026-09-30","Green",9800000,4100000,"Aditi Rane",34),
    ("P05","Meridian AMC","C02","Managed Services","2025-09-01","2027-06-30","Green",14400000,9200000,"Sneha Kulkarni",29),
    ("P06","Halcyon HIPAA Cloud Landing Zone","C03","Cloud Migration","2026-01-15","2026-08-31","Green",12600000,7300000,"Kabir Menon",27),
    ("P07","Halcyon Patient Portal","C03","Application Development","2026-03-01","2026-11-30","Amber",8400000,3900000,"Aditi Rane",19),
    ("P08","Vertex Fleet Tracking Squad","C04","Staff Augmentation","2025-10-01","2026-09-30","Amber",11760000,8900000,"Neha Bhosale",14),
    ("P09","Vertex Warehouse Integrations","C04","Application Development","2026-02-01","2026-07-31","Red",5200000,5600000,"Neha Bhosale",-8),
    ("P10","Aurora SCADA Data Platform","C05","Data & AI","2026-02-15","2027-01-31","Green",28800000,11200000,"Kabir Menon",33),
    ("P11","Aurora Predictive Maintenance","C05","Data & AI","2026-04-01","2026-12-31","Green",9600000,2800000,"Ishaan Verma",36),
    ("P12","Internal - K-OS Platform R&D","INT","Internal","2026-01-01","2026-12-31","Green",4000000,2600000,"Ishaan Verma",0),
]
w("11_projects.csv",
  ["project_id","project_name","client_id","service_line","start_date","end_date","health",
   "budget_inr","spent_to_date_inr","delivery_manager","margin_pct"], PROJECTS)

# ── employees ─────────────────────────────────────────────────────────────
FIRST = ["Rohan","Sneha","Aditi","Kabir","Neha","Ishaan","Priya","Arjun","Meera","Vikram","Ananya","Siddharth",
         "Divya","Karan","Tanvi","Rahul","Pooja","Nikhil","Riya","Aman","Shruti","Varun","Kavya","Manish","Isha","Yash"]
LAST = ["Deshpande","Kulkarni","Rane","Menon","Bhosale","Verma","Iyer","Nair","Joshi","Patil","Sharma","Gupta",
        "Reddy","Chauhan","Mehta","Sinha","Pawar","Bansal","Shetty","Khanna","Desai","Rao","Pillai","Malhotra","Ghosh","Jain"]
ROLES = [("Delivery Manager","M3",3800),("Solution Architect","M2",3200),("Tech Lead","L4",2400),
         ("Senior Engineer","L3",1800),("Engineer","L2",1200),("Associate Engineer","L1",850),
         ("SRE","L3",1900),("Data Engineer","L3",2000),("QA Engineer","L2",1100),("Security Analyst","L3",2100)]
SKILLS = ["Java/Spring","Python/FastAPI","React/TypeScript","AWS","Azure","Kubernetes","PostgreSQL","Kafka",
          "Terraform","Databricks","Splunk","Go","Node.js","Oracle DB","Snowflake"]
emp = []
for i in range(26):
    role, band, cost = ROLES[i % len(ROLES)]
    bill = int(cost * random.uniform(1.55, 2.30))
    util = round(random.uniform(0.42, 0.99), 2)
    bench = 0 if util > 0.75 else random.randint(8, 62)
    emp.append((f"E{i+1:03d}", f"{FIRST[i]} {LAST[i]}", role, band,
                random.choice(SKILLS), random.choice(["Pune","Bengaluru","Remote"]),
                cost, bill, util, bench,
                random.choice(["P01","P02","P03","P04","P05","P06","P07","P08","P09","P10","P11","P12","BENCH"])))
w("12_employees.csv",
  ["employee_id","employee_name","role","band","primary_skill","location",
   "cost_rate_inr_per_hr","bill_rate_inr_per_hr","utilisation","bench_days_ytd","current_project"], emp)

# ── incidents ─────────────────────────────────────────────────────────────
CAUSES = ["Database failover did not promote replica","Expired TLS certificate","Memory leak in order service",
          "Upstream payment gateway timeout","Misconfigured autoscaling policy","Disk full on log volume",
          "Unindexed query after schema change","Kafka consumer lag","DNS propagation delay","Failed batch job retry storm"]
SEV_TARGET = {"SEV-1":1.0,"SEV-2":4.0,"SEV-3":8.0,"SEV-4":24.0}
inc, d0 = [], dt.date(2026,2,1)
# Vertex is deliberately the worst performer; Meridian the best.
MIX = ["C04"]*14 + ["C01"]*12 + ["C03"]*8 + ["C05"]*7 + ["C02"]*5
random.shuffle(MIX)
for i, cid in enumerate(MIX):
    sev = random.choices(["SEV-1","SEV-2","SEV-3","SEV-4"], weights=[1,3,5,4])[0]
    opened = d0 + dt.timedelta(days=random.randint(0,178), hours=random.randint(0,23))
    target = SEV_TARGET[sev]
    # Vertex breaches often; Meridian almost never.
    breach_p = {"C04":0.50,"C01":0.28,"C03":0.18,"C05":0.15,"C02":0.05}[cid]
    resolve_h = round(target * (random.uniform(1.05,2.9) if random.random() < breach_p else random.uniform(0.15,0.92)), 2)
    inc.append((f"INC-{1000+i}", cid, sev, opened.isoformat()+"T"+f"{random.randint(0,23):02d}:00",
                resolve_h, target, "No" if resolve_h > target else "Yes",
                random.choice(CAUSES), random.choice(["P02","P03","P05","P06","P08","P09"])))
w("14_incidents.csv",
  ["incident_id","client_id","severity","opened_at","resolution_hours","sla_target_hours",
   "sla_met","root_cause","project_id"], inc)

# ── invoices ──────────────────────────────────────────────────────────────
inv = []
for i in range(28):
    cid = random.choice([c[0] for c in CLIENTS])
    issued = dt.date(2026,1,1) + dt.timedelta(days=random.randint(0,200))
    due = issued + dt.timedelta(days=45)
    amt = random.choice([850000,1200000,1450000,1850000,2400000,3200000,975000])
    paid = random.random() < 0.68
    paid_on = (due - dt.timedelta(days=random.randint(-18,20))).isoformat() if paid else ""
    overdue = 0 if paid else max(0, (dt.date(2026,8,2) - due).days)
    inv.append((f"INV-2026-{i+101}", cid, amt, issued.isoformat(), due.isoformat(),
                "Paid" if paid else "Unpaid", paid_on, overdue))
w("15_invoices.csv",
  ["invoice_id","client_id","amount_inr","issued_date","due_date","status","paid_date","days_overdue"], inv)

# ── timesheets ────────────────────────────────────────────────────────────
ts = []
for wk in range(18):
    weekend = dt.date(2026,4,3) + dt.timedelta(weeks=wk)
    for e in random.sample(emp, 12):
        proj = e[10]
        if proj == "BENCH": continue
        billable = round(random.uniform(18,44),1)
        ts.append((f"{weekend.isoformat()}", e[0], e[1], proj, billable,
                   round(random.uniform(1,12),1), round(billable*e[7],0)))
w("13_timesheets.csv",
  ["week_ending","employee_id","employee_name","project_id","billable_hours","non_billable_hours","billed_value_inr"], ts)

# ── headline facts for the playbook's expected answers ────────────────────
from collections import defaultdict
br = defaultdict(lambda: [0,0])
for r in inc:
    br[r[1]][1] += 1
    if r[6] == "No": br[r[1]][0] += 1
print("\n--- SLA breach rate by client ---")
for cid,(b,t) in sorted(br.items(), key=lambda x: -x[1][0]/x[1][1]):
    nm = next(c[1] for c in CLIENTS if c[0]==cid)
    print(f"{nm:20s} {b}/{t} breached = {100*b/t:.0f}%")
od = [r for r in inv if r[5]=="Unpaid"]
print(f"\nUnpaid invoices: {len(od)}  total INR {sum(r[2] for r in od):,}")
print(f"Worst overdue: {max(od, key=lambda r: r[7])[0]} at {max(r[7] for r in od)} days")
print(f"\nProjects over budget: {[p[0] for p in PROJECTS if p[8] > p[7]]}")
print(f"Bench >30 days: {sum(1 for e in emp if e[9] > 30)} people")
