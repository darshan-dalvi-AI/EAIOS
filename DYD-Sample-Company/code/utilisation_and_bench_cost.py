"""DYD — utilisation and the true cost of the bench.

The handbook targets 80% utilisation. This works out who is under it, what the
bench is actually costing, and which skills the idle capacity is stuck in --
because bench is usually a reskilling problem wearing a sales problem's clothes.

Runs in the K-OS Code app: standard library only.
"""
from collections import defaultdict

# (name, role, skill, cost/hr, bill/hr, utilisation, bench days YTD)
STAFF = [
    ("Rohan Deshpande",  "Delivery Manager",   "Java/Spring",     3800, 7000, 0.92,  0),
    ("Sneha Kulkarni",   "Solution Architect", "AWS",             3200, 6100, 0.88,  0),
    ("Aditi Rane",       "Tech Lead",          "React/TypeScript",2400, 4600, 0.95,  0),
    ("Kabir Menon",      "Senior Engineer",    "Kubernetes",      1800, 3500, 0.97,  0),
    ("Neha Bhosale",     "Engineer",           "Python/FastAPI",  1200, 2300, 0.81,  0),
    ("Ishaan Verma",     "Associate Engineer", "Go",               850, 1600, 0.64, 41),
    ("Priya Iyer",       "SRE",                "Terraform",       1900, 3600, 0.90,  0),
    ("Arjun Nair",       "Data Engineer",      "Databricks",      2000, 3900, 0.93,  0),
    ("Meera Joshi",      "QA Engineer",        "Java/Spring",     1100, 2100, 0.58, 52),
    ("Vikram Patil",     "Security Analyst",   "Splunk",          2100, 4000, 0.72, 22),
    ("Ananya Sharma",    "Senior Engineer",    "Oracle DB",       1800, 3400, 0.49, 61),
    ("Siddharth Gupta",  "Engineer",           "Oracle DB",       1200, 2200, 0.44, 58),
    ("Divya Reddy",      "Engineer",           "Java/Spring",     1200, 2250, 0.51, 47),
    ("Karan Chauhan",    "Associate Engineer", "Java/Spring",      850, 1550, 0.46, 55),
    ("Tanvi Mehta",      "QA Engineer",        "Node.js",         1100, 2000, 0.68, 34),
    ("Rahul Sinha",      "Senior Engineer",    "Kafka",           1800, 3450, 0.94,  0),
    ("Pooja Pawar",      "Data Engineer",      "Snowflake",       2000, 3800, 0.55, 44),
    ("Nikhil Bansal",    "Tech Lead",          "Oracle DB",       2400, 4400, 0.53, 49),
]

TARGET = 0.80
HOURS_PER_BENCH_DAY = 8
DEMAND = {"Terraform", "Databricks", "Kubernetes", "Snowflake"}

under = [s for s in STAFF if s[5] < TARGET]
bench = [s for s in STAFF if s[6] > 30]

print("DYD Technologies — utilisation and bench")
print(f"Handbook target: {TARGET:.0%} of available hours\n")

avg = sum(s[5] for s in STAFF) / len(STAFF)
print(f"Headcount analysed      {len(STAFF)}")
print(f"Average utilisation     {avg:.0%}")
print(f"Below target            {len(under)}  ({len(under)/len(STAFF):.0%} of staff)")
print(f"Bench over 30 days      {len(bench)}\n")

idle_cost = sum(s[6] * HOURS_PER_BENCH_DAY * s[3] for s in bench)
lost_rev  = sum(s[6] * HOURS_PER_BENCH_DAY * s[4] for s in bench)
print(f"Bench days total        {sum(s[6] for s in bench)}")
print(f"Idle COST (salary)      INR {idle_cost:,}")
print(f"Revenue NOT earned      INR {lost_rev:,}")
print(f"Combined margin impact  INR {idle_cost + lost_rev:,}\n")

print("Bench concentrated in these skills")
by_skill = defaultdict(lambda: [0, 0])
for s in bench:
    by_skill[s[2]][0] += 1
    by_skill[s[2]][1] += s[6]
for skill, (n, days) in sorted(by_skill.items(), key=lambda x: -x[1][1]):
    tag = "" if skill in DEMAND else "   <- NOT in current demand"
    print(f"  {skill:<20} {n} people, {days:>3} days{tag}")

print("\nReskilling candidates (idle, in a skill we are not selling)")
for s in sorted(bench, key=lambda s: -s[6]):
    if s[2] not in DEMAND:
        print(f"  {s[0]:<20} {s[2]:<18} {s[6]:>3} days idle, util {s[5]:.0%}")

print(f"\nDemand skills we are short of: {', '.join(sorted(DEMAND))}")
print("Handbook §5: bench past 30 days requires a named reskilling or")
print("redeployment plan. Bench is a management problem, not an employee one.")
