# Extracted Chunks: synthetic_test.pdf (article_id=PDF:synthetic_test.pdf)

### Chunk 1 [text | page_1_text]

# Quarterly Network Incident Report

This section summarizes ticket volume by region and severity for Q2. The table below uses a two-level spanning header: the top row groups two quarters, each split into Open/Closed sub-columns — a structure that a naive grid extractor typically flattens.

---

### Chunk 2 [table | page_1_table]

```json
[
  {
    "Region": "EMEA",
    "Q1": {
      "Open": 12,
      "Closed": 10
    },
    "Q2": {
      "Open": 9,
      "Closed": 8
    }
  },
  {
    "Region": "APAC",
    "Q1": {
      "Open": 7,
      "Closed": 7
    },
    "Q2": {
      "Open": 11,
      "Closed": 6
    }
  },
  {
    "Region": "AMER",
    "Q1": {
      "Open": 15,
      "Closed": 13
    },
    "Q2": {
      "Open": 10,
      "Closed": 10
    }
  }
]
```

---

### Chunk 3 [text | page_2_text]

# Incident Postmortem Summary

On 2026-08-14 the edge load balancer in the Cairo point of presence began dropping TLS handshakes for roughly six percent of inbound sessions. Root cause was traced to a certificate rotation script that failed to reload the new chain on two of four nodes. Mitigation: manual reload plus a health check that now verifies certificate serial numbers match across the pool before traffic is re-admitted.

---

### Chunk 4 [text | page_3_text]

ملخص تقرير الحادثة: في الرابع عشر من أغسطس تعطل موازن التحميل الطرفي في مركز بيانات القاهرة، مما أدى إلى فشل عملية المصافحة الأمنية لحوالي ستة بالمئة من الجلسات الواردة. يعود السبب الجذري إلى برنامج تدوير الشهادات الذي لم يعد تحميل السلسلة الجديدة على عقدتين من أصل أربع عقد.

---

### Chunk 5 [text | page_4_text]

Figure 3. Certificate rotation failure path.

---

### Chunk 6 [diagram | page_4_diagram]

```mermaid
%% Summary: Certificate rotation failure path diagram showing the sequence of cron firing, pushing a new chain to all nodes, reloading, and resulting in a stale chain or health check flags mismatch.
flowchart LR
    A["Certificate rotation cron fires"] <-- B["Push new chain to all nodes"]
    B --- C["Reload succeeds on node?"]
    B --- D["Node keeps stale chain"]
    C <-- E["Health check flags mismatch"]
```

---

