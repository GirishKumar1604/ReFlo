# 🚀 ReFlo Operations PR  
### *Pull Requests for Business Operations*

> What pull requests do for code, ReFlo does for spreadsheets.

---

## 🎥 Demo Video

[[Watch Demo](https://docs.google.com/videos/d/1FrNDbT24LJRdNb2GvnNJdGwqd4kd_Q80Kf2f33lGrLY/edit?usp=sharing)]
---

## ⚡ TL;DR

ReFlo transforms messy operational spreadsheets into **structured, reviewable, and actionable workflows**.

Instead of directly editing data:
- 🧠 AI proposes changes  
- 👤 Humans review & approve  
- ⚙️ System applies safely  
- 📊 Outputs are generated automatically  

---

## 🧠 Problem

Operations teams still rely heavily on spreadsheets for critical workflows like:

- Accounts receivable  
- CRM updates  
- Internal tracking  

But spreadsheets are:

- ❌ Messy (inconsistent headers, formats)  
- ❌ Manual (error-prone updates)  
- ❌ Unstructured (no approval workflow)  
- ❌ Opaque (no clear prioritization or visibility)  

👉 Result: **slow execution, high risk, no accountability**

---

## 💡 Solution

**ReFlo Operations PR** introduces an **approval-first workflow layer** on top of Google Sheets.

Instead of editing spreadsheets directly:

1. 📥 Read messy data  
2. 🧠 Generate structured proposals  
3. 👀 Review changes like a PR  
4. ✅ Approve selected updates  
5. ⚙️ Apply changes safely  
6. 📊 Generate outputs (queue + reports)  

---

## 🧾 Demo Use Case

### Accounts Receivable (Collections)

ReFlo helps teams:

- Identify overdue invoices  
- Prioritize high-risk accounts  
- Generate daily collections queue  
- Track recovery potential  
- Improve operational visibility  

---

## ⚙️ What It Does

Given a single operator prompt, ReFlo:

- Reads messy operational sheets  
- Maps non-standard headers → business concepts  
- Generates structured patch proposals  
- Enables row/field-level approval  
- Applies approved changes safely  
- Generates:
  - 📋 Collections Queue  
  - 📊 Reports  
  - 📈 Dashboard insights  

---

## 🧱 Core Sheets Structure

| Tab | Purpose |
|-----|--------|
| **Receivables Raw** | Raw messy input data |
| **Proposed Changes** | Suggested updates (review layer) |
| **Collections Queue** | Actionable follow-ups |
| **Report** | Summary + insights |

---

## 📊 Executive Dashboard

On running the system, you get:

- 💰 Total Outstanding  
- ⚠️ At Risk Amount  
- 📈 Projected Recovery  
- 🟢 Health Meter (Red / Yellow / Green)  
- 📅 Aging Buckets (0–30, 31–60, 61+)  
- 🚨 Action Alerts  
- 🔍 Anomaly Detection  

---

## 🖥️ How to Run Locally

### 1. Start the server

```bash
python3 sheetops_gws_demo.py serve --host 127.0.0.1 --port 8000
