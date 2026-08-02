/**
 * DYD — receivables ageing.
 *
 * Buckets every unpaid invoice and works out where the cash is stuck. The
 * master agreement gives DYD a suspension right at 60 days overdue (MSA §8),
 * so the 60+ buckets are the ones with a decision attached to them.
 *
 * Runs in the K-OS Code app: plain JavaScript, no imports, no network.
 */

// invoice, client, amount (INR), days overdue (0 = paid or not yet due)
const INVOICES = [
  ["INV-2026-103", "Halcyon Health",   2450000, 163],
  ["INV-2026-107", "Halcyon Health",   1850000, 121],
  ["INV-2026-112", "Meridian Bank",    2400000,  88],
  ["INV-2026-118", "Halcyon Health",   1450000, 163],
  ["INV-2026-121", "Northwind Retail", 1200000,  74],
  ["INV-2026-124", "Aurora Energy",    2700000,  52],
  ["INV-2026-126", "Halcyon Health",   1625000,  41],
  ["INV-2026-127", "Meridian Bank",    1300000,  33],
  ["INV-2026-128", "Vertex Logistics", 1200000,  19],
  ["INV-2026-129", "Northwind Retail",  850000,   8],
];

const SUSPENSION_THRESHOLD = 60;   // MSA §8
const INTEREST_PER_MONTH   = 0.015; // 1.5% per month on overdue balances

const BUCKETS = [
  ["Current (0-30)",  0,  30],
  ["31-60 days",     31,  60],
  ["61-90 days",     61,  90],
  ["91-120 days",    91, 120],
  ["120+ days",     121, Infinity],
];

const inr = (n) => "INR " + Math.round(n).toLocaleString("en-IN");

console.log("DYD Technologies — receivables ageing");
console.log("MSA §8: net 45 days, 1.5%/month interest, suspension right at 60 days overdue\n");

const total = INVOICES.reduce((s, i) => s + i[2], 0);
console.log(`Outstanding invoices   ${INVOICES.length}`);
console.log(`Total outstanding      ${inr(total)}\n`);

console.log("Ageing profile");
console.log("-".repeat(58));
for (const [label, lo, hi] of BUCKETS) {
  const rows = INVOICES.filter((i) => i[3] >= lo && i[3] <= hi);
  if (!rows.length) continue;
  const amt = rows.reduce((s, i) => s + i[2], 0);
  const share = (100 * amt / total).toFixed(0);
  const bar = "#".repeat(Math.round(amt / total * 30));
  console.log(`${label.padEnd(16)}${String(rows.length).padStart(3)}  ${inr(amt).padStart(16)}  ${String(share).padStart(3)}%  ${bar}`);
}
console.log("-".repeat(58));

// Concentration by client — one slow payer distorts the whole book.
const byClient = {};
for (const [, client, amt, days] of INVOICES) {
  byClient[client] ??= { amt: 0, n: 0, worst: 0 };
  byClient[client].amt += amt;
  byClient[client].n += 1;
  byClient[client].worst = Math.max(byClient[client].worst, days);
}

console.log("\nBy client");
const ranked = Object.entries(byClient).sort((a, b) => b[1].amt - a[1].amt);
for (const [client, d] of ranked) {
  const share = (100 * d.amt / total).toFixed(0);
  console.log(`  ${client.padEnd(20)} ${inr(d.amt).padStart(16)}  ${String(share).padStart(3)}% of book,  ${d.n} inv,  worst ${d.worst}d`);
}

const [worstClient, worstData] = ranked[0];
console.log(`\n${worstClient} is ${(100 * worstData.amt / total).toFixed(0)}% of the outstanding book.`);

// Suspension-eligible and the interest DYD is entitled to but does not charge.
const eligible = INVOICES.filter((i) => i[3] > SUSPENSION_THRESHOLD);
const eligibleAmt = eligible.reduce((s, i) => s + i[2], 0);

console.log(`\nSuspension-eligible (over ${SUSPENSION_THRESHOLD} days overdue)`);
console.log(`  ${eligible.length} invoices, ${inr(eligibleAmt)} — ${(100 * eligibleAmt / total).toFixed(0)}% of the book`);
for (const [id, client, amt, days] of eligible.sort((a, b) => b[3] - a[3])) {
  const interest = amt * INTEREST_PER_MONTH * (days / 30);
  console.log(`    ${id}  ${client.padEnd(18)} ${inr(amt).padStart(14)}  ${days}d overdue  (interest accrued ${inr(interest)})`);
}

const totalInterest = eligible.reduce((s, i) => s + i[2] * INTEREST_PER_MONTH * (i[3] / 30), 0);
console.log(`\n  Contractual interest accrued: ${inr(totalInterest)}`);
console.log("  DYD does not currently invoice this. That is a commercial choice,");
console.log("  not a contractual limit — and it is worth knowing what it costs.");
