/**
 * Seed Property — Unbound Gateway Phase I stub.
 *
 * Mirrors the Python ``validation/argus_unbound.py::build_stub_property`` so
 * the page renders a known-good Argus cashflow on first load. The values
 * here are the ones we pin against Argus to the dollar in CI.
 */
export type PropertyPayload = Record<string, unknown>;

const PBR_BY_YEAR = [
  4_453_848, 4_531_793, 4_667_751, 4_807_780, 4_952_016, 5_100_580,
  5_253_596, 5_411_201, 5_573_534, 5_740_739, 5_946_861,
];

const OPEX_CATS = {
  "Real Estate Taxes": [
    860_004, 885_804, 912_372, 939_744, 967_932, 996_972, 1_026_888,
    1_057_692, 1_089_420, 1_122_108, 1_155_768,
  ],
  Insurance: [
    240_000, 247_200, 254_616, 262_260, 270_120, 278_220, 286_572,
    295_164, 304_020, 313_140, 322_536,
  ],
  "Property Management Fee": [
    64_923, 250_838, 258_369, 266_116, 274_098, 282_322, 290_791,
    299_512, 308_504, 317_760, 240_827,
  ],
  CAM: [
    345_000, 355_356, 366_012, 376_992, 388_296, 399_948, 411_948,
    424_308, 437_040, 450_144, 463_656,
  ],
} as const;

const CAPEX_CATS = {
  "Non-Leasing Capital Expense": [6_522_072],
  "Capital Reserves": [
    0, 0, 57_072, 58_776, 60_540, 62_352, 64_224, 66_156, 68_136, 70_188,
    72_288,
  ],
} as const;

const ACQUISITION_YEAR = 2026;

function indexedAnnualSchedule(values: readonly number[], filterZero = false) {
  const out: Record<string, number> = {};
  values.forEach((v, i) => {
    if (filterZero && v === 0) return;
    out[String(ACQUISITION_YEAR + i)] = v;
  });
  return out;
}

export function unboundSeed(): PropertyPayload {
  const rentSteps = [
    { start_date: "2026-06-01", annual_psf: String(PBR_BY_YEAR[0]) },
    ...PBR_BY_YEAR.slice(1).map((pbr, i) => ({
      start_date: `${2027 + i}-01-01`,
      annual_psf: String(pbr),
    })),
  ];

  return {
    name: "Unbound Gateway - Phase I (seeded)",
    rentable_sf: 1,
    leases: [
      {
        suite_id: "100",
        tenant_name: "Unbound Tenant",
        area_sf: 1,
        start_date: "2026-06-01",
        end_date: "2036-06-01",
        base_rent_steps: rentSteps,
        free_rent_months: 5,
        ti_psf: "7643630",
        lc_pct_first_year_rent: "0.98705286",
        expense_structure: "NNN",
        market_leasing_assumption: {
          market_rent_psf: String(PBR_BY_YEAR[0]),
          market_rent_growth_pct: "0.03",
          new_term_months: 120,
          rent_escalation_pct: "0.03",
          free_rent_months_new: 5,
          renewal_probability: "1.0",
          downtime_months_new: 5,
          expense_structure: "NNN",
        },
      },
    ],
    opex_annual: {},
    opex_categories: Object.fromEntries(
      Object.entries(OPEX_CATS).map(([cat, vals]) => [cat, indexedAnnualSchedule(vals)])
    ),
    capex_annual: {},
    capex_categories: Object.fromEntries(
      Object.entries(CAPEX_CATS).map(([cat, vals]) => [cat, indexedAnnualSchedule(vals, true)])
    ),
    acquisition_date: "2026-01-01",
    acquisition_price: "1",
    hold_years: 11,
    exit_cap_rate: "0.05",
    general_vacancy_pct: "0",
    credit_loss_pct: "0",
  };
}
