# Data Retention Schedule

**Document Type:** Compliance
**Version:** 1.4
**Effective Date:** January 1, 2025
**Owner:** Legal & Compliance
**Review Cycle:** Annual

---

## 1. Purpose

This schedule defines how long InsightHub retains different categories of data and when data must be deleted or anonymised. Retention periods are set to meet legal obligations, support business operations, and minimise privacy risk through data minimisation.

## 2. Retention Schedule

### 2.1 Customer Data

| Data Type | Retention Period | Basis | Action at Expiry |
|---|---|---|---|
| Customer PII (name, email, address) | 7 years from last transaction | Legal obligation (consumer regulations) | Anonymise or delete |
| Order history (non-PII) | 10 years | Legal / tax | Retain anonymised |
| Payment card data | Per PCI DSS (never stored in plain text) | PCI DSS | Not retained |
| Customer support tickets | 5 years from closure | Legitimate interests | Delete |
| Marketing consent records | Consent period + 3 years | GDPR accountability | Delete |
| Inactive account PII (no login 3+ years) | Delete or anonymise at 3-year mark | GDPR minimisation | Anonymise |

### 2.2 Employee Data

| Data Type | Retention Period | Basis | Action at Expiry |
|---|---|---|---|
| Employee personnel file (HR records) | 7 years post-termination | Employment law | Securely delete |
| Payroll and compensation records | 7 years | Tax / legal obligation | Securely delete |
| Performance reviews | 5 years post-termination | Legitimate interests | Securely delete |
| Disciplinary records | 5 years post-resolution | HR policy | Securely delete |
| Training records (mandatory compliance) | Duration of employment + 3 years | Regulatory / audit | Archive then delete |
| Access logs (IT systems) | 1 year | IT security | Auto-purge |
| Video surveillance (office) | 30 days | Security / GDPR | Auto-purge |

### 2.3 Financial Records

| Data Type | Retention Period | Basis |
|---|---|---|
| Financial statements and accounts | 7 years | IRS / SOX |
| Invoices and purchase orders | 7 years | IRS requirement |
| Expense receipts and claims | 7 years | IRS |
| Bank statements and reconciliations | 7 years | IRS |
| Tax returns and filings | 7 years | IRS |

### 2.4 Contracts and Legal Documents

| Data Type | Retention Period | Basis |
|---|---|---|
| Signed customer contracts | 10 years after expiry | Limitation periods |
| Vendor/supplier contracts | 10 years after expiry | Limitation periods |
| Employment contracts | 7 years post-termination | Employment law |
| NDAs | 10 years after expiry | Limitation periods |
| Insurance policies | 7 years after expiry | Insurance law |

### 2.5 Operational and System Data

| Data Type | Retention Period | Basis |
|---|---|---|
| Application logs (production) | 1 year | IT security / debugging |
| Database audit logs | 2 years | Compliance / forensics |
| Email correspondence (business) | 3 years | Business records |
| Internal chat logs (Slack) | 1 year | Operational / GDPR |
| Marketing campaign performance data | 5 years (anonymised after 2 years) | Analytics |
| Web analytics (non-PII) | 3 years | Business analytics |
| CCTV / access control logs | 30 days | Security / GDPR |

## 3. Deletion Standards

When data reaches its retention expiry:

- **Structured data (databases):** Automated deletion scripts run quarterly. Records are flagged 90 days before expiry; confirmed for deletion by the Data Owner.
- **Unstructured data (files, email):** IT Operations processes deletion. Evidence of deletion is logged in the Data Disposal Register.
- **Third-party systems:** IT Operations sends deletion instructions to all relevant vendors and obtains written confirmation.

Data is not simply hidden or archived — it must be permanently deleted or anonymised (irreversible pseudonymisation).

## 4. Legal Hold

When data is relevant to actual or anticipated litigation, regulatory investigation, or audit, a **Legal Hold** overrides the retention schedule. Legal issues Legal Hold notices via the Data Disposal System. Data under Legal Hold must not be deleted until the hold is released by Legal in writing.

## 5. Retention Exceptions

Exceptions to the retention schedule require:
- A written business justification
- Legal review and approval
- Documentation in the Retention Exception Register (Confluence)

## 6. Responsibilities

| Role | Responsibility |
|---|---|
| Data Owners (team leads) | Confirm data ready for deletion at expiry |
| IT Operations | Execute technical deletion; maintain Disposal Register |
| Legal | Issue Legal Holds; approve exceptions; maintain schedule |
| Employees | Not to retain copies of data outside approved systems |

---

*Questions: Contact Legal & Compliance at legal@insighthub.com.*
