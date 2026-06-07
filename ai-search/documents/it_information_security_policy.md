# Information Security Policy

**Document Type:** IT Policy
**Version:** 5.1
**Effective Date:** January 1, 2025
**Owner:** IT Security
**Review Cycle:** Annual

---

## 1. Purpose

This policy establishes the minimum information security controls that all InsightHub employees, contractors, and third parties must follow to protect company data, systems, and customer information.

## 2. Data Classification

All company data must be classified into one of four tiers:

| Classification | Description | Examples |
|---|---|---|
| **Public** | Approved for external release | Marketing collateral, press releases |
| **Internal** | For employees only | Internal announcements, process docs |
| **Confidential** | Sensitive; need-to-know basis | Financial projections, HR records |
| **Restricted** | Highest sensitivity; tightly controlled | PII, authentication credentials, payment data |

Data owners (the originating team) are responsible for assigning and maintaining classification labels.

## 3. Password and Authentication Policy

### 3.1 Password Requirements

All user-created passwords must meet the following standards:

- Minimum **12 characters**
- Mix of uppercase, lowercase, numbers, and special characters
- No dictionary words or name-based patterns
- Not reused from any of the previous 12 passwords

### 3.2 Multi-Factor Authentication (MFA)

MFA is **mandatory** for all company accounts including:

- Microsoft 365 / Azure AD
- GitHub and code repositories
- AWS and Azure cloud consoles
- VPN access
- Any SaaS application that stores Confidential or Restricted data

The approved MFA methods are: Microsoft Authenticator app (preferred), hardware token (FIDO2 key), or SMS (last resort only). MFA bypass is not permitted.

### 3.3 Password Manager

All employees are provisioned with a company-managed password manager (1Password). Use of personal password managers for company credentials is not permitted.

## 4. Device Security

- **Encryption:** All company-issued laptops and mobile devices must have full-disk encryption enabled (BitLocker for Windows, FileVault for macOS).
- **Screen Lock:** Devices must auto-lock after **5 minutes** of inactivity.
- **MDM Enrolment:** All devices must be enrolled in Microsoft Intune before accessing company systems.
- **Personal Devices:** Bring-Your-Own-Device (BYOD) is only permitted after IT Security approval and MDM enrolment.
- **Physical Security:** Devices must not be left unattended in public spaces. Theft must be reported to IT within 1 hour.

## 5. Network Security

- **VPN:** All remote access to internal systems requires an active VPN connection. The approved VPN client is Cisco AnyConnect.
- **Public Wi-Fi:** Company data must not be accessed over public Wi-Fi without VPN active.
- **Office Network:** The corporate Wi-Fi network is monitored. Connecting personal devices requires the guest network.

## 6. Access Control (Principle of Least Privilege)

Access to systems and data is granted based on the minimum required to perform job functions. Access requests are submitted via the IT Service Desk and approved by the requesting employee's manager plus the system owner. Access reviews are conducted **quarterly** for all Confidential and Restricted systems.

## 7. Incident Reporting

All suspected security incidents must be reported **within 1 hour of discovery** to:

- Email: security@insighthub.com
- Slack: #security-incidents
- Phone: IT Security on-call (see the IT Runbook for the current on-call number)

Incidents include: phishing emails, malware, unauthorised access, lost devices, data loss or exposure, and suspicious account activity.

## 8. Security Awareness Training

All employees must complete quarterly security awareness training:

- **Q1:** Phishing and social engineering simulation
- **Q2:** Data handling and classification
- **Q3:** Secure coding practices (technical roles) / Cloud security basics (all)
- **Q4:** Incident response and reporting

Training is mandatory and tracked in the Learning Portal. Non-completion is escalated to the employee's manager after 14 days.

## 9. Third-Party and Vendor Security

Vendors who access InsightHub systems or data must:

- Complete a security assessment before contract award (IT Security manages this)
- Sign a Data Processing Agreement (DPA) where applicable
- Adhere to this policy and any additional contractual security obligations

## 10. Policy Violations

Violation of this policy may result in immediate revocation of system access and disciplinary action up to termination, depending on severity and intent. Intentional data exfiltration will be reported to law enforcement.

---

*Report security concerns at any time to security@insighthub.com. No concern is too small.*
