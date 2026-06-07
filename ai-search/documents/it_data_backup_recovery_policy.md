# Data Backup and Recovery Policy

**Document Type:** IT Policy
**Version:** 2.1
**Effective Date:** January 1, 2025
**Owner:** IT Operations
**Review Cycle:** Annual

---

## 1. Purpose

This policy defines InsightHub's requirements for backing up data, the recovery time and recovery point objectives for each system tier, and the procedures for restoring data following an incident. Its goal is to ensure business continuity and data integrity.

## 2. System Tiers

Systems are classified into three tiers based on their criticality:

| Tier | Classification | Examples | RTO | RPO |
|---|---|---|---|---|
| Tier 1 | Mission-Critical | E-commerce platform, payment processing, Azure SQL databases | 4 hours | 1 hour |
| Tier 2 | Business-Important | CRM, ERP, HR system, corporate email | 8 hours | 4 hours |
| Tier 3 | Non-Critical | Internal wikis, development environments, test databases | 24 hours | 24 hours |

**RTO (Recovery Time Objective):** Maximum acceptable downtime before the system must be restored.
**RPO (Recovery Point Objective):** Maximum acceptable data loss, measured in time.

## 3. Backup Frequency and Retention

### 3.1 Tier 1 Systems

| Backup Type | Frequency | Retention |
|---|---|---|
| Transaction log / continuous | Every 15 minutes | 7 days |
| Full backup | Daily (2:00 AM UTC) | 35 days |
| Weekly full backup | Every Sunday | 12 weeks |
| Monthly full backup | First Sunday of month | 12 months |
| Annual archive | January 1 | 7 years |

### 3.2 Tier 2 Systems

| Backup Type | Frequency | Retention |
|---|---|---|
| Incremental backup | Daily | 14 days |
| Full backup | Weekly | 8 weeks |
| Monthly archive | Monthly | 12 months |

### 3.3 Tier 3 Systems

| Backup Type | Frequency | Retention |
|---|---|---|
| Full backup | Weekly | 4 weeks |
| Monthly archive | Monthly | 6 months |

## 4. Backup Technology

### 4.1 Cloud Infrastructure (Azure)

- **Azure SQL Database:** Automated geo-redundant backups managed by Azure SQL. Point-in-time restore enabled for all production databases. Backup storage is replicated to a paired Azure region.
- **Azure Blob Storage:** Geo-redundant storage (GRS) with soft-delete enabled (7-day recovery window for accidental deletions).
- **Azure App Services and Functions:** Configuration backed up daily via Azure Backup.

### 4.2 Endpoint Backup

- Company laptops are backed up daily via **Microsoft OneDrive** continuous sync for user documents, and **Azure Backup Agent** for full device backup (weekly).
- Employees are responsible for ensuring work files are saved in OneDrive, not local-only storage.

### 4.3 On-Premises / Hybrid

- Development build servers: backed up nightly to Azure Blob with 30-day retention.
- Network attached storage (NAS): daily snapshot with 14-day retention.

## 5. Backup Monitoring and Alerts

IT Operations monitors all backup jobs via **Azure Monitor** and receives automated alerts for:

- Failed backup jobs (alert within 15 minutes of failure)
- Backup job completion status (daily summary report at 6:00 AM)
- Backup storage capacity (alert at 80% capacity)

Failed backup alerts are treated as Severity 2 incidents and must be investigated within 2 hours.

## 6. Recovery Testing

Recovery capability must be tested on a regular schedule:

| Test Type | Frequency | Scope |
|---|---|---|
| File-level restore test | Monthly | Sample restore from each Tier 1 system |
| Database point-in-time restore | Quarterly | Full restore test to isolated environment |
| Full system restore | Semi-annual | Tier 1 systems; full DR environment |
| Tabletop exercise | Annual | Cross-functional teams; scenario-based |

Test results are documented in the IT Runbook (Confluence). Any gaps identified must have a remediation plan within 30 days.

## 7. Disaster Recovery (DR) Plan

In the event of a major system failure:

1. **Incident declared** by on-call engineer or IT Operations Manager
2. **Triage:** determine affected systems, scope, and estimated recovery time
3. **Communication:** notify stakeholders using the Incident Communication template (Confluence)
4. **Recovery:** execute the relevant runbook (per-system runbooks in Confluence)
5. **Validation:** confirm data integrity and service functionality before returning systems to production
6. **Post-incident review:** within 5 business days, complete a Root Cause Analysis (RCA) document

The DR plan is tested in full once per year (see Section 6).

## 8. Data Deletion and End-of-Life

When systems are decommissioned or hardware is retired:

- Storage media is wiped using DoD 5220.22-M standard or physically destroyed.
- A **Certificate of Data Destruction** is issued and filed in the Asset Register.
- Cloud resources are deleted and subscription/resource group removal confirmed in Azure Portal.

---

*IT Operations on-call: see the Runbook in Confluence for current contacts.*
