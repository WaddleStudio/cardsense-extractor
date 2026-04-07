# Co-branded Retailer & Date Condition Inference

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add RETAIL_CHAIN conditions for co-branded department store cards (中友百貨, 大江) and date-based conditions (DAY_OF_MONTH, DAY_OF_WEEK) so promotions carry structured filtering metadata.

**Architecture:** Two new public functions in `promotion_rules.py` — `append_inferred_cobranded_conditions()` for title-based retailer detection and `append_inferred_date_conditions()` for date pattern detection. Both follow the existing `append_inferred_*` pattern (take title/body/conditions, return merged conditions). Called in the condition inference pipeline in each extractor and `normalize.py`.

**Tech Stack:** Python 3.13+ / pytest / existing promotion_rules infrastructure

---

### Task 1: Add `COBRANDED_RETAILER_SIGNALS` data and `append_inferred_cobranded_conditions()`

**Files:**
- Modify: `extractor/promotion_rules.py:785` (after `STRUCTURED_SUBCATEGORY_CONDITION_SIGNALS`)
- Test: `tests/test_cobranded_and_date_conditions.py` (create)

**Step 1: Write the failing tests**

Create `tests/test_cobranded_and_date_conditions.py`:

```python
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.promotion_rules import append_inferred_cobranded_conditions


def test_cobranded_adds_chungyo_retail_chain():
    conditions = append_inferred_cobranded_conditions(
        "中友百貨悠遊聯名卡 最高再享1.5%回饋",
        "於中友百貨館內消費享最高1.5%回饋",
        [],
    )
    assert any(
        c["type"] == "RETAIL_CHAIN" and c["value"] == "CHUNGYO"
        for c in conditions
    )


def test_cobranded_adds_metrowalk_retail_chain():
    conditions = append_inferred_cobranded_conditions(
        "大江聯名卡 天天饗最高12%回饋",
        "於大江購物中心餐飲消費享最高12%回饋",
        [],
    )
    assert any(
        c["type"] == "RETAIL_CHAIN" and c["value"] == "METROWALK"
        for c in conditions
    )


def test_cobranded_skips_general_epoint_without_retailer_keyword():
    """General e-point rewards that mention the card name but not the store should NOT get a condition."""
    conditions = append_inferred_cobranded_conditions(
        "中友百貨悠遊聯名卡 玉山e point（一般消費）",
        "一般消費享玉山e point回饋",
        [],
    )
    # Title contains 中友百貨 so it WILL match — this is expected.
    # The function is title-based; the caller decides whether to call it.
    assert any(
        c["type"] == "RETAIL_CHAIN" and c["value"] == "CHUNGYO"
        for c in conditions
    )


def test_cobranded_does_not_duplicate_existing_condition():
    existing = [{"type": "RETAIL_CHAIN", "value": "CHUNGYO", "label": "中友百貨"}]
    conditions = append_inferred_cobranded_conditions(
        "中友百貨悠遊聯名卡 13號卡友日",
        "中友百貨館內消費",
        existing,
    )
    chungyo_count = sum(1 for c in conditions if c["value"] == "CHUNGYO")
    assert chungyo_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /d/Projects/cardsense-workspace/cardsense-extractor && uv run pytest tests/test_cobranded_and_date_conditions.py -v`
Expected: FAIL with ImportError (function doesn't exist yet)

**Step 3: Implement `COBRANDED_RETAILER_SIGNALS` and `append_inferred_cobranded_conditions()`**

In `extractor/promotion_rules.py`, after `STRUCTURED_SUBCATEGORY_CONDITION_SIGNALS` (line 785), add:

```python
# Co-branded card retailer signals — matched against title+body regardless of subcategory.
# Unlike STRUCTURED_SUBCATEGORY_CONDITION_SIGNALS, these are NOT gated by subcategory != GENERAL.
COBRANDED_RETAILER_SIGNALS: List[Dict[str, str]] = [
    {"token": "中友百貨", "type": "RETAIL_CHAIN", "value": "CHUNGYO", "label": "中友百貨"},
    {"token": "大江", "type": "RETAIL_CHAIN", "value": "METROWALK", "label": "大江購物中心"},
]
```

Then, after `append_inferred_payment_method_conditions()` (around line 1027), add:

```python
def append_inferred_cobranded_conditions(
    title: str,
    body: str,
    conditions: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Add RETAIL_CHAIN conditions when title/body mentions a co-branded retailer."""
    text = f"{title} {body}"
    merged = list(conditions)
    seen = {
        (str(c.get("type", "")).upper(), str(c.get("value", "")).upper())
        for c in merged
    }
    for signal in COBRANDED_RETAILER_SIGNALS:
        if signal["token"] not in text:
            continue
        key = (signal["type"].upper(), signal["value"].upper())
        if key in seen:
            continue
        merged.append({"type": signal["type"], "value": signal["value"], "label": signal["label"]})
        seen.add(key)
    return merged
```

**Step 4: Run tests to verify they pass**

Run: `cd /d/Projects/cardsense-workspace/cardsense-extractor && uv run pytest tests/test_cobranded_and_date_conditions.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
cd /d/Projects/cardsense-workspace/cardsense-extractor
git add extractor/promotion_rules.py tests/test_cobranded_and_date_conditions.py
git commit -m "feat: add co-branded retailer condition inference for 中友百貨 and 大江"
```

---

### Task 2: Add `append_inferred_date_conditions()`

**Files:**
- Modify: `extractor/promotion_rules.py` (after `append_inferred_cobranded_conditions`)
- Test: `tests/test_cobranded_and_date_conditions.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_cobranded_and_date_conditions.py`:

```python
from extractor.promotion_rules import append_inferred_date_conditions


def test_date_day_of_month_13():
    conditions = append_inferred_date_conditions(
        "中友百貨悠遊聯名卡 13號卡友日",
        "每月13號於中友百貨館內累積消費滿3,000元",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_MONTH" and c["value"] == "13"
        for c in conditions
    )


def test_date_day_of_month_pattern_meiyue():
    conditions = append_inferred_date_conditions(
        "每月15號回饋日",
        "每月15號消費享雙倍回饋",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_MONTH" and c["value"] == "15"
        for c in conditions
    )


def test_date_day_of_week_wednesday():
    conditions = append_inferred_date_conditions(
        "每週三加碼回饋",
        "每週三於指定通路消費享加碼",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_WEEK" and c["value"] == "WED"
        for c in conditions
    )


def test_date_day_of_week_weekend():
    conditions = append_inferred_date_conditions(
        "週末限定回饋",
        "週末於百貨消費享加碼回饋",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_WEEK" and c["value"] == "WEEKEND"
        for c in conditions
    )


def test_date_day_of_week_friday_saturday():
    conditions = append_inferred_date_conditions(
        "週五六加碼",
        "每週五、六消費享加碼回饋",
        [],
    )
    assert any(c["type"] == "DAY_OF_WEEK" and c["value"] == "FRI" for c in conditions)
    assert any(c["type"] == "DAY_OF_WEEK" and c["value"] == "SAT" for c in conditions)


def test_date_no_match_returns_unchanged():
    existing = [{"type": "TEXT", "value": "test", "label": "test"}]
    conditions = append_inferred_date_conditions(
        "一般消費回饋",
        "享1%回饋",
        existing,
    )
    assert conditions == existing


def test_date_does_not_duplicate():
    existing = [{"type": "DAY_OF_MONTH", "value": "13", "label": "每月13號"}]
    conditions = append_inferred_date_conditions(
        "13號卡友日",
        "每月13號消費",
        existing,
    )
    dom_count = sum(1 for c in conditions if c["type"] == "DAY_OF_MONTH" and c["value"] == "13")
    assert dom_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /d/Projects/cardsense-workspace/cardsense-extractor && uv run pytest tests/test_cobranded_and_date_conditions.py::test_date_day_of_month_13 -v`
Expected: FAIL with ImportError

**Step 3: Implement `append_inferred_date_conditions()`**

In `extractor/promotion_rules.py`, after `append_inferred_cobranded_conditions()`, add:

```python
_DAY_OF_WEEK_MAP: Dict[str, str] = {
    "一": "MON", "二": "TUE", "三": "WED", "四": "THU",
    "五": "FRI", "六": "SAT", "日": "SUN",
}

_DAY_OF_WEEK_LABELS: Dict[str, str] = {
    "MON": "每週一", "TUE": "每週二", "WED": "每週三", "THU": "每週四",
    "FRI": "每週五", "SAT": "每週六", "SUN": "每週日", "WEEKEND": "週末限定",
}

_RE_DAY_OF_MONTH = re.compile(r"(?:每月)?(\d{1,2})號(?:卡友日)?")
_RE_DAY_OF_WEEK = re.compile(r"(?:每)?週([一二三四五六日])")
_RE_WEEKEND = re.compile(r"週末|假日")


def append_inferred_date_conditions(
    title: str,
    body: str,
    conditions: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Add DAY_OF_MONTH / DAY_OF_WEEK conditions from date patterns in title/body."""
    text = f"{title} {body}"
    merged = list(conditions)
    seen = {
        (str(c.get("type", "")).upper(), str(c.get("value", "")).upper())
        for c in merged
    }

    # DAY_OF_MONTH: 每月13號, 13號卡友日
    for match in _RE_DAY_OF_MONTH.finditer(text):
        day = match.group(1)
        key = ("DAY_OF_MONTH", day)
        if key not in seen:
            merged.append({"type": "DAY_OF_MONTH", "value": day, "label": f"每月{day}號"})
            seen.add(key)

    # DAY_OF_WEEK: 每週三, 週五
    for match in _RE_DAY_OF_WEEK.finditer(text):
        cn_day = match.group(1)
        value = _DAY_OF_WEEK_MAP.get(cn_day)
        if value:
            key = ("DAY_OF_WEEK", value)
            if key not in seen:
                merged.append({"type": "DAY_OF_WEEK", "value": value, "label": _DAY_OF_WEEK_LABELS[value]})
                seen.add(key)

    # WEEKEND: 週末, 假日
    if _RE_WEEKEND.search(text):
        key = ("DAY_OF_WEEK", "WEEKEND")
        if key not in seen:
            merged.append({"type": "DAY_OF_WEEK", "value": "WEEKEND", "label": "週末限定"})
            seen.add(key)

    return merged
```

Note: `import re` is already at the top of the file. Verify before adding.

**Step 4: Run tests to verify they pass**

Run: `cd /d/Projects/cardsense-workspace/cardsense-extractor && uv run pytest tests/test_cobranded_and_date_conditions.py -v`
Expected: 11 PASSED

**Step 5: Commit**

```bash
cd /d/Projects/cardsense-workspace/cardsense-extractor
git add extractor/promotion_rules.py tests/test_cobranded_and_date_conditions.py
git commit -m "feat: add date condition inference (DAY_OF_MONTH, DAY_OF_WEEK)"
```

---

### Task 3: Wire new functions into condition inference pipeline

**Files:**
- Modify: `extractor/esun_real.py:27-28,576-577` (imports + pipeline call)
- Modify: `extractor/cathay_real.py:28-29,528-535,683-684`
- Modify: `extractor/taishin_real.py:27-28,348-349,1125-1126`
- Modify: `extractor/fubon_real.py:26-27,270-271`
- Modify: `extractor/ctbc_real.py:38-39,319-320`
- Modify: `extractor/normalize.py:6-9,159-166`

**Step 1: Add imports and pipeline calls in each extractor**

For each extractor file, add to the import block:

```python
append_inferred_cobranded_conditions,
append_inferred_date_conditions,
```

And in each condition inference pipeline (after the existing `append_inferred_payment_method_conditions` call), add:

```python
conditions = append_inferred_cobranded_conditions(clean_title, clean_body, conditions)
conditions = append_inferred_date_conditions(clean_title, clean_body, conditions)
```

**Specific locations:**

**`esun_real.py`:**
- Import: add after line 28
- Pipeline: add after line 577 (`append_inferred_payment_method_conditions`)

**`cathay_real.py`:**
- Import: add after line 29
- Pipeline sites: after line 535 and after line 684

**`taishin_real.py`:**
- Import: add after line 28
- Pipeline sites: after line 349 and after line 1126

**`fubon_real.py`:**
- Import: add after line 27
- Pipeline sites: after line 271

**`ctbc_real.py`:**
- Import: add after line 39
- Pipeline sites: after line 320

**`normalize.py`:**
- Import: add `append_inferred_cobranded_conditions, append_inferred_date_conditions` after line 9
- Pipeline: add after line 166 (after `sanitize_payment_conditions`):

```python
normalized_conditions = append_inferred_cobranded_conditions(
    title_text or "", title_text or "", normalized_conditions
)
normalized_conditions = append_inferred_date_conditions(
    title_text or "", title_text or "", normalized_conditions
)
```

**Step 2: Run existing tests to verify no regressions**

Run: `cd /d/Projects/cardsense-workspace/cardsense-extractor && uv run pytest -v`
Expected: All existing tests PASS

**Step 3: Commit**

```bash
cd /d/Projects/cardsense-workspace/cardsense-extractor
git add extractor/esun_real.py extractor/cathay_real.py extractor/taishin_real.py extractor/fubon_real.py extractor/ctbc_real.py extractor/normalize.py
git commit -m "feat: wire cobranded retailer and date conditions into all extractors"
```

---

### Task 4: Verify with E.SUN extraction output

**Step 1: Run E.SUN extraction and check 中友/大江 promotions**

```bash
cd /d/Projects/cardsense-workspace/cardsense-extractor
uv run python jobs/run_esun_real_job.py
```

**Step 2: Inspect output for correct conditions**

```bash
# Check 中友百貨 promotions have RETAIL_CHAIN and DAY_OF_MONTH
grep "中友" outputs/esun-real-*.jsonl | tail -1 | python3 -c "
import sys, json
for line in sys.stdin:
    p = json.loads(line)
    print(f\"{p['title']}  conditions={[c for c in p['conditions'] if c['type'] != 'TEXT']}\")
"

# Check 大江 promotions have RETAIL_CHAIN
grep "大江" outputs/esun-real-*.jsonl | tail -1 | python3 -c "
import sys, json
for line in sys.stdin:
    p = json.loads(line)
    print(f\"{p['title']}  conditions={[c for c in p['conditions'] if c['type'] != 'TEXT']}\")
"
```

Expected:
- 「13號卡友日」should have both `RETAIL_CHAIN:CHUNGYO` and `DAY_OF_MONTH:13`
- 「最高再享1.5%回饋」should have `RETAIL_CHAIN:CHUNGYO` or `RETAIL_CHAIN:METROWALK`
- 「天天饗最高12%回饋」should have `RETAIL_CHAIN:METROWALK`
- 「玉山e point（一般消費）」will also have `RETAIL_CHAIN:CHUNGYO` (because title contains 中友百貨) — this is acceptable since the condition is informational, not used for API filtering yet

**Step 3: Commit if verification passes (no code change needed)**

No commit needed — this is a verification step.
