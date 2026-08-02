"""DYD — service credit calculator.

Implements MSA v4.2 section 3 exactly as written, including the cap. Run it to
see what DYD owes each client this period, and where the cap stops the
commercial mechanism from applying any further pressure.

Runs in the K-OS Code app: pure standard library, no network, no file access.
The figures are embedded so the script is self-contained.
"""

# tier -> (credit % per breached target, cap as % of the monthly fee)
TIERS = {
    "Platinum": (7.5, 20),
    "Gold":     (3.0, 10),
    "Silver":   (2.0, 10),
}

# client, tier, monthly fee (INR), breached targets, total incidents
CLIENTS = [
    ("Northwind Retail",  "Platinum", 1_850_000,  1, 12),
    ("Meridian Bank",     "Platinum", 3_200_000,  0,  5),
    ("Halcyon Health",    "Gold",     1_450_000,  2,  8),
    ("Vertex Logistics",  "Silver",     980_000, 10, 14),
    ("Aurora Energy",     "Gold",     2_400_000,  0,  7),
]


def credit(tier: str, fee: int, breaches: int) -> tuple[int, int, bool]:
    """Return (payable, uncapped, capped?) for one client-month."""
    pct, cap_pct = TIERS[tier]
    uncapped = int(fee * breaches * pct / 100)
    cap = int(fee * cap_pct / 100)
    return min(uncapped, cap), uncapped, uncapped > cap


def breaches_to_reach_cap(tier: str) -> int:
    pct, cap_pct = TIERS[tier]
    return int(-(-cap_pct // pct))  # ceiling division; int so it prints "5" not "5.0"


print("DYD Technologies — service credits, current period")
print("MSA v4.2 §3:  credit = breaches x tier% x monthly fee, capped\n")

hdr = f"{'Client':<20}{'Tier':<10}{'Breach':>8}{'Rate':>7}{'Uncapped':>13}{'Payable':>12}"
print(hdr)
print("-" * len(hdr))

total = 0
at_cap = []
for name, tier, fee, breaches, incidents in CLIENTS:
    payable, uncapped, was_capped = credit(tier, fee, breaches)
    total += payable
    rate = 100 * breaches / incidents if incidents else 0
    flag = "  <- CAPPED" if was_capped else ""
    if was_capped:
        at_cap.append((name, tier, breaches))
    print(f"{name:<20}{tier:<10}{breaches:>4}/{incidents:<3}{rate:>6.0f}%"
          f"{uncapped:>13,}{payable:>12,}{flag}")

print("-" * len(hdr))
print(f"{'TOTAL PAYABLE':<45}{total:>25,}\n")

if at_cap:
    print("Clients at the credit cap")
    print("The cap is the point where further failure becomes free to DYD, which")
    print("is why breach RATE is a delivery metric and not only a billing input.\n")
    for name, tier, breaches in at_cap:
        need = breaches_to_reach_cap(tier)
        free = breaches - need
        print(f"  {name}: cap reached at {need} breaches, {breaches} occurred")
        print(f"    -> {free} breaches cost DYD nothing financially")
        print(f"    -> MSA §4: 3 consecutive months at the cap = termination for cause\n")

print("Cap thresholds by tier")
for tier in TIERS:
    print(f"  {tier:<10} cap reached at {breaches_to_reach_cap(tier)} breaches in a month")
