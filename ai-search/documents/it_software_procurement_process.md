# Software Procurement Process

**Document Type:** IT Policy
**Version:** 2.2
**Effective Date:** March 1, 2025
**Owner:** IT Operations
**Review Cycle:** Annual

---

## 1. Purpose

This document describes the process for requesting, evaluating, approving, and managing software tools at InsightHub. It ensures that all software is properly assessed for security, licensing compliance, and cost efficiency before use on company systems.

## 2. Scope

This process applies to all software, SaaS subscriptions, and cloud service purchases, whether paid or free, desktop or web-based. It applies to all employees and contractors.

## 3. Approval Thresholds

The required approvals depend on annual contract value:

| Annual Cost | Required Approvals |
|---|---|
| Free tools | IT Security review + Manager approval |
| Up to $500 | Manager + IT Security review |
| $501 – $5,000 | Manager + IT Security + Finance |
| $5,001 – $25,000 | Manager + IT Security + Finance + VP |
| Over $25,000 | Manager + IT Security + Finance + CTO |

All software regardless of cost requires an IT Security review before installation or access.

## 4. Request Process

### Step 1: Submit a Request

Submit a Software Procurement Request via the IT Service Desk ticket system (Jira Service Management). Include:

- Software name and vendor
- Business justification (what problem does it solve?)
- Number of intended users
- Estimated annual cost
- Data types that will be processed (does it handle customer data, PII, or financial data?)
- Alternative tools already available that were considered

### Step 2: IT Security Review

IT Security will assess the tool within **5 business days** for:

- Data processing practices and privacy policy
- SOC 2 Type II or ISO 27001 certification (required for tools that handle Confidential data)
- Penetration testing recency (within 12 months)
- Data residency (EU data must remain in EU or adequate country)
- Single sign-on (SSO) support (required for tools used by more than 5 employees)
- Vendor financial stability

IT Security may approve, reject, or approve with conditions (e.g., restricted data types).

### Step 3: Legal Review

If the tool processes customer data, a **Data Processing Agreement (DPA)** must be signed before use. Legal will review vendor contracts for:

- IP ownership clauses
- Liability and indemnification terms
- Data return and deletion obligations on termination

Legal review takes **up to 10 business days**.

### Step 4: Finance Approval

For purchases above $500/year, Finance will confirm:

- Budget availability in the requesting team's cost centre
- Preferred payment method (corporate card or PO)
- Multi-year discounts or negotiated terms

### Step 5: Provisioning

Once all approvals are complete, IT Operations will:

- Arrange licence procurement and payment
- Configure SSO integration where available
- Provision access to approved users via the identity management system
- Add the tool to the Software Asset Register

## 5. Renewals and Cancellations

The IT Operations team sends renewal reminders **90 days before** each contract anniversary. Requestors must confirm continued need and usage metrics. Unused licences (no login in 90 days) will be cancelled at renewal.

## 6. Software Asset Register

IT Operations maintains a central Software Asset Register (in Confluence) listing all licensed tools, owners, costs, renewal dates, and approved user groups. The register is reviewed quarterly.

## 7. Unapproved Software

Installing or using unapproved software is a violation of the Acceptable Use Policy. Unapproved tools found during device scans will be removed immediately and the incident referred to the employee's manager.

## 8. Free and Open-Source Software (FOSS)

Free software still requires an IT Security review. Open-source software used in production code must:

- Have a licence compatible with commercial use (MIT, Apache 2.0, BSD preferred)
- Be reviewed by an Engineering Lead for supply chain risk
- Be recorded in the Software Asset Register

---

*Submit software requests at: itservicedesk.insighthub.com or Slack #it-requests.*
