/**
 * Static mock data used when the app is running in Guest / demo mode.
 * Guest mode bypasses all backend calls so recruiters can explore the UI
 * even when the Azure backend is offline.
 *
 * Numbers are based on the real InsightHub dataset (10K customers, 50K orders,
 * 119K+ fact rows) so the shapes and magnitudes are representative.
 */

import type { KPISummary, RevenueTrend, CampaignROIRow } from '../types/api'

// ── KPI Summary ──────────────────────────────────────────────────────────────
// Total revenue: $99,960,000  |  Orders: 34,716  |  Active customers: 7,835

export const GUEST_KPI: KPISummary = {
  total_revenue: 99_960_000,
  total_orders: 34_716,
  total_customers: 7_835,
  avg_order_value: 2_879,
  gross_profit: 35_985_600,
  gross_margin_pct: 36.0,
  total_tickets: 4_250,
  avg_csat: 3.8,
  open_tickets: 620,
  total_campaigns: 100,
  top_campaign_roi_pct: 287,
  period_label: 'Jan 2023 – Jun 2025',
}

// ── Revenue Trend (30 months Jan 2023 – Jun 2025) ───────────────────────────
// Sum: $99,960,000  |  Dashboard chart shows last 24 months via slice(-24)

export const GUEST_REVENUE_TREND: RevenueTrend[] = [
  // 2023 — ramp-up year
  { period: '2023-01', revenue: 2_750_000, gross_profit: 935_000,   order_count: 955,  avg_order_value: 2_880 },
  { period: '2023-02', revenue: 2_430_000, gross_profit: 826_200,   order_count: 844,  avg_order_value: 2_879 },
  { period: '2023-03', revenue: 2_890_000, gross_profit: 982_600,   order_count: 1_003, avg_order_value: 2_881 },
  { period: '2023-04', revenue: 2_650_000, gross_profit: 901_000,   order_count: 920,  avg_order_value: 2_880 },
  { period: '2023-05', revenue: 2_960_000, gross_profit: 1_006_400, order_count: 1_028, avg_order_value: 2_879 },
  { period: '2023-06', revenue: 3_120_000, gross_profit: 1_060_800, order_count: 1_083, avg_order_value: 2_881 },
  // ← chart slice(-24) starts here (Jul 2023)
  { period: '2023-07', revenue: 2_850_000, gross_profit: 969_000,   order_count: 990,  avg_order_value: 2_879 },
  { period: '2023-08', revenue: 2_780_000, gross_profit: 945_200,   order_count: 965,  avg_order_value: 2_881 },
  { period: '2023-09', revenue: 3_050_000, gross_profit: 1_067_500, order_count: 1_059, avg_order_value: 2_880 },
  { period: '2023-10', revenue: 3_340_000, gross_profit: 1_169_000, order_count: 1_160, avg_order_value: 2_879 },
  { period: '2023-11', revenue: 4_120_000, gross_profit: 1_442_000, order_count: 1_430, avg_order_value: 2_881 },
  { period: '2023-12', revenue: 3_880_000, gross_profit: 1_358_000, order_count: 1_347, avg_order_value: 2_880 },
  // 2024 — growth year
  { period: '2024-01', revenue: 3_050_000, gross_profit: 1_128_500, order_count: 1_059, avg_order_value: 2_880 },
  { period: '2024-02', revenue: 2_870_000, gross_profit: 1_061_900, order_count: 997,  avg_order_value: 2_879 },
  { period: '2024-03', revenue: 3_210_000, gross_profit: 1_188_700, order_count: 1_115, avg_order_value: 2_879 },
  { period: '2024-04', revenue: 3_040_000, gross_profit: 1_124_800, order_count: 1_056, avg_order_value: 2_879 },
  { period: '2024-05', revenue: 3_350_000, gross_profit: 1_239_500, order_count: 1_163, avg_order_value: 2_881 },
  { period: '2024-06', revenue: 3_580_000, gross_profit: 1_325_600, order_count: 1_243, avg_order_value: 2_880 },
  { period: '2024-07', revenue: 3_280_000, gross_profit: 1_213_600, order_count: 1_139, avg_order_value: 2_879 },
  { period: '2024-08', revenue: 3_190_000, gross_profit: 1_180_300, order_count: 1_108, avg_order_value: 2_878 },
  { period: '2024-09', revenue: 3_580_000, gross_profit: 1_325_600, order_count: 1_243, avg_order_value: 2_880 },
  { period: '2024-10', revenue: 3_920_000, gross_profit: 1_449_600, order_count: 1_362, avg_order_value: 2_879 },
  { period: '2024-11', revenue: 4_680_000, gross_profit: 1_731_600, order_count: 1_625, avg_order_value: 2_880 },
  { period: '2024-12', revenue: 4_350_000, gross_profit: 1_609_500, order_count: 1_510, avg_order_value: 2_881 },
  // 2025 H1
  { period: '2025-01', revenue: 3_420_000, gross_profit: 1_265_400, order_count: 1_188, avg_order_value: 2_879 },
  { period: '2025-02', revenue: 3_080_000, gross_profit: 1_139_600, order_count: 1_070, avg_order_value: 2_879 },
  { period: '2025-03', revenue: 3_650_000, gross_profit: 1_350_500, order_count: 1_268, avg_order_value: 2_878 },
  { period: '2025-04', revenue: 3_520_000, gross_profit: 1_302_400, order_count: 1_222, avg_order_value: 2_881 },
  { period: '2025-05', revenue: 3_780_000, gross_profit: 1_398_600, order_count: 1_313, avg_order_value: 2_879 },
  { period: '2025-06', revenue: 3_590_000, gross_profit: 1_328_300, order_count: 1_247, avg_order_value: 2_879 },
]

// ── Top Campaigns (8 rows) ───────────────────────────────────────────────────

export const GUEST_CAMPAIGNS: CampaignROIRow[] = [
  {
    campaign_name: 'Summer Sales Blast',
    campaign_type: 'Email',
    region: 'National',
    budget: 245_000,
    spend: 238_400,
    revenue: 683_900,
    roi_pct: 186.9,
    impressions: 1_240_000,
    clicks: 87_300,
    conversions: 3_842,
    ctr_pct: 7.04,
    conversion_rate_pct: 4.40,
    roi_band: 'High',
  },
  {
    campaign_name: 'Back to School 2024',
    campaign_type: 'PPC',
    region: 'Northeast',
    budget: 310_000,
    spend: 298_700,
    revenue: 757_300,
    roi_pct: 153.5,
    impressions: 2_100_000,
    clicks: 94_500,
    conversions: 2_940,
    ctr_pct: 4.50,
    conversion_rate_pct: 3.11,
    roi_band: 'High',
  },
  {
    campaign_name: 'Holiday Season Push',
    campaign_type: 'Social Media',
    region: 'National',
    budget: 520_000,
    spend: 504_300,
    revenue: 1_261_200,
    roi_pct: 150.1,
    impressions: 5_800_000,
    clicks: 174_000,
    conversions: 4_610,
    ctr_pct: 3.00,
    conversion_rate_pct: 2.65,
    roi_band: 'High',
  },
  {
    campaign_name: 'Q1 New Year Launch',
    campaign_type: 'Email',
    region: 'National',
    budget: 185_000,
    spend: 179_200,
    revenue: 404_800,
    roi_pct: 125.9,
    impressions: 920_000,
    clicks: 64_400,
    conversions: 2_387,
    ctr_pct: 7.00,
    conversion_rate_pct: 3.71,
    roi_band: 'High',
  },
  {
    campaign_name: 'Spring Refresh 2024',
    campaign_type: 'Display',
    region: 'West',
    budget: 220_000,
    spend: 211_600,
    revenue: 452_100,
    roi_pct: 113.7,
    impressions: 3_400_000,
    clicks: 68_000,
    conversions: 1_587,
    ctr_pct: 2.00,
    conversion_rate_pct: 2.33,
    roi_band: 'High',
  },
  {
    campaign_name: 'Customer Loyalty Drive',
    campaign_type: 'Email',
    region: 'National',
    budget: 140_000,
    spend: 133_700,
    revenue: 277_300,
    roi_pct: 107.4,
    impressions: 680_000,
    clicks: 47_600,
    conversions: 1_743,
    ctr_pct: 7.00,
    conversion_rate_pct: 3.66,
    roi_band: 'High',
  },
  {
    campaign_name: 'Product Launch Alpha',
    campaign_type: 'Social Media',
    region: 'National',
    budget: 290_000,
    spend: 281_400,
    revenue: 562_800,
    roi_pct: 100.0,
    impressions: 3_100_000,
    clicks: 93_000,
    conversions: 2_046,
    ctr_pct: 3.00,
    conversion_rate_pct: 2.20,
    roi_band: 'Medium',
  },
  {
    campaign_name: 'Regional Expansion West',
    campaign_type: 'PPC',
    region: 'West',
    budget: 175_000,
    spend: 168_900,
    revenue: 320_900,
    roi_pct: 89.9,
    impressions: 1_150_000,
    clicks: 41_400,
    conversions: 1_118,
    ctr_pct: 3.60,
    conversion_rate_pct: 2.70,
    roi_band: 'Medium',
  },
]

// ── Sample AI Insights (static, pre-expanded detail) ────────────────────────

export interface GuestInsightData {
  category: string
  title: string
  narrative: string
  confidence: number
  period_start: string
  period_end: string
  key_findings: string[]
  recommendations: string[]
  risk_flags?: string[]
}

export const GUEST_INSIGHT_DATA: GuestInsightData[] = [
  {
    category: 'Sales',
    title: 'Q2 2025 Revenue Acceleration — 12% QoQ Growth Ahead of Forecast',
    narrative:
      'Total revenue reached $10.8M in Q2 2025, representing a 12% quarter-over-quarter increase and surpassing the projected target by 11.7%. Order volume climbed to 3,828 units across the period, with average order value rising from $2,724 to $2,879 — indicating successful upsell execution alongside volume growth. Electronics and Clothing categories contributed 68% of incremental revenue. Gross margin held at 37%, consistent with Q1 performance and confirming that growth is not being purchased through discounting.',
    confidence: 0.92,
    period_start: '2025-04-01',
    period_end: '2025-06-30',
    key_findings: [
      'Revenue of $10.8M in Q2 2025 is the second-highest quarterly result in the dataset, trailing only Q4 2024 ($13.0M).',
      'Average order value increased 5.7% QoQ from $2,724 to $2,879, driven by Electronics bundle sales and cross-sell attach rates.',
      'Electronics (38%) and Clothing (30%) together account for 68% of Q2 incremental revenue; Sports & Outdoors declined 4% QoQ.',
      'Gross margin held at 37.0%, unchanged from Q1 — pricing discipline is intact through the growth acceleration.',
    ],
    recommendations: [
      'Accelerate the Electronics bundle strategy into Q3 before back-to-school demand peaks; set a stretch target of $2,950 AOV.',
      'Investigate the 4% Sports & Outdoors decline — if seasonal, plan inventory rebalancing for Q3; if structural, review assortment.',
      'Commission a margin-mix analysis to quantify the revenue impact of a 1-percentage-point margin expansion across Clothing.',
    ],
  },
  {
    category: 'Customers',
    title: 'Premium Segment Churn Risk — 23% At-Risk Rate Exposes $12M Annual Revenue',
    narrative:
      'The Premium customer cohort (2,140 accounts) exhibits a 23% churn-risk rate in the trailing 90 days, up 5 percentage points from the prior quarter. Premium customers represent 41% of total revenue despite comprising only 21% of the active base — a revenue-per-customer ratio 2.6× higher than the Standard segment. Single-category purchasers with declining order frequency account for 78% of the at-risk cohort. Standard and Budget segments remain stable at 9% and 7% churn risk respectively.',
    confidence: 0.87,
    period_start: '2025-01-01',
    period_end: '2025-06-30',
    key_findings: [
      'Premium churn risk rose from 18% to 23% QoQ — the highest rate recorded in the analysis window.',
      '78% of at-risk Premium customers are single-category purchasers; cross-category buyers show a 3.1% churn rate versus 31% for single-category.',
      'At-risk Premium accounts represent an estimated $11.8M in annualised revenue if they churn at the current projected rate.',
      'Average days-since-last-purchase for the at-risk cohort is 67 days, up from 41 days in the prior quarter.',
    ],
    recommendations: [
      'Launch a 90-day Premium retention programme targeting the 492 highest-value at-risk accounts with personalised re-engagement offers.',
      'Introduce cross-category recommendation nudges at checkout to reduce the proportion of single-category buyers below 60%.',
      'Set an executive-level KPI: Premium churn risk ≤ 15% by Q3 2025, with weekly tracking against the current 23% baseline.',
    ],
    risk_flags: [
      'If the 23% Premium churn risk fully materialises, trailing-twelve-month revenue impact is estimated at $11.8M — a 12% revenue contraction.',
      'No early-warning system is currently in place; churn risk is identified retrospectively after order frequency declines.',
    ],
  },
  {
    category: 'Campaigns',
    title: 'Email Campaigns Outperform Paid Social 2.4× — Significant Reallocation Opportunity',
    narrative:
      'Across the full 30-month analysis window, email campaigns delivered an average ROI of 186.9% versus 100% for paid social placements. The Summer Sales Blast email campaign achieved a record 287% ROI on a $238K spend. Paid social currently receives 43% of the total campaign budget despite generating proportionally lower returns. PPC channels occupy the middle ground at 130% average ROI. Rebalancing 20 percentage points of budget from social to email and PPC — at the same total spend — is modelled to yield an estimated $3.2M in incremental annual revenue.',
    confidence: 0.91,
    period_start: '2023-01-01',
    period_end: '2025-06-30',
    key_findings: [
      'Email campaigns average 186.9% ROI across 14 campaigns; paid social averages 100% ROI across 31 campaigns — a 1.87× gap.',
      'PPC channels average 130% ROI; combined email + PPC average ROI is 158% versus 100% for social-only spend.',
      'Paid social receives 43% of total campaign budget (est. $2.1M annually) despite the lower return profile.',
      'Conversion rate for email (3.7%) is 1.5× higher than PPC (2.4%) and 2.0× higher than paid social (1.8%).',
    ],
    recommendations: [
      'Shift 20% of paid social budget to email in Q3 2025; model projects $3.2M incremental revenue at constant total spend.',
      'Scale the Summer Sales Blast email playbook — A/B test subject lines and send-time optimisation to defend the 287% ROI at higher volume.',
      'Retain paid social for brand-awareness objectives only; remove revenue ROI as the primary success metric for social campaigns.',
    ],
  },
]
