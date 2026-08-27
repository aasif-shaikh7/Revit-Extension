# -*- coding: utf-8 -*-
"""Rewrite build_site_summary_sheet: per-category VOLUME + SHUTTERING.

The detail sheets stay selection-only, but the element rows in
data_result still carry Qty: Volume (m3) and Qty: Shuttering (m2) (they
come from build_element_data). The front Summary now aggregates those
two metrics per category directly from data_result so they appear even
though the detail tabs no longer show them.
"""
import io
import re
import py_compile

PATH = r"Aasif.extension\Aasif.tab\Generate.panel\BOQ.pushbutton\script.py"

with io.open(PATH, "r", encoding="utf-8", newline="") as fh:
    src = fh.read()

DEF_START = src.find("def build_site_summary_sheet(")
if DEF_START == -1:
    raise SystemExit("FATAL: summary def not found")

START = re.compile(r"^    present_categories = \[", re.M)
start_match = START.search(src, DEF_START)
if not start_match:
    raise SystemExit("FATAL: present_categories not found")

END_ANCHOR = "    return (out_rows, meta)"
end_pos = src.find(END_ANCHOR, start_match.start())
if end_pos == -1:
    raise SystemExit("FATAL: end anchor not found")
end_pos_full = end_pos + len(END_ANCHOR)

new_body = (
    "    present_categories = [\n"
    "        category_name\n"
    "        for category_name in SITE_CATEGORY_ORDER\n"
    "        if category_name in site_detail_meta\n"
    "    ]\n"
    "\n"
    "    if not present_categories:\n"
    "        return ([], {})\n"
    "\n"
    "    header_label_map = {\n"
    "        \"Beam\": \"BEAM\",\n"
    "        \"Column\": \"COLUMN\",\n"
    "        \"Slab\": \"SLAB\",\n"
    "        \"Foundation\": \"FOUNDATION\"\n"
    "    }\n"
    "\n"
    "    # Element rows in data_result still carry the metric columns even\n"
    "    # though the selection-only detail sheets hide them. Aggregate\n"
    "    # VOLUME and SHUTTERING per category straight from data_result so\n"
    "    # the Summary keeps both figures while the detail tabs stay clean.\n"
    "    def aggregate_metric(category_name, metric_key):\n"
    "        total = 0.0\n"
    "        for row in (data_result.get(category_name) or []):\n"
    "            try:\n"
    "                metric_value = float(row.get(metric_key, 0) or 0)\n"
    "            except:\n"
    "                metric_value = 0.0\n"
    "            total += metric_value\n"
    "        return round(total, 2) if total else \"\"\n"
    "\n"
    "    out_rows = [\n"
    "        [str(project_name or \"\")],\n"
    "        [\"RCC - CONCRETE FINISHING BOQ\"],\n"
    "        [\"ITEM-WISE SUMMARY - CONCRETE AND SHUTTERING\"],\n"
    "        [],\n"
    "        [\n"
    "            (\"MERGE_V\", \"SNO\"),\n"
    "            (\"MERGE_V\", \"CATEGORY\"),\n"
    "            \"ELEMENTS\",\n"
    "            \"VOLUME (m3)\",\n"
    "            \"SHUTTERING (m2)\"\n"
    "        ],\n"
    "        [\"\", \"\", \"\", \"\", \"\"],\n"
    "    ]\n"
    "\n"
    "    first_data_row = len(out_rows) + 1\n"
    "\n"
    "    item_number = 1\n"
    "\n"
    "    for category_name in present_categories:\n"
    "\n"
    "        category_meta = site_detail_meta.get(category_name, {})\n"
    "\n"
    "        out_rows.append(\n"
    "            [\n"
    "                item_number,\n"
    "                header_label_map[category_name],\n"
    "                category_meta.get(\"elements\", 0),\n"
    "                aggregate_metric(category_name, \"Qty: Volume (m3)\"),\n"
    "                aggregate_metric(category_name, \"Qty: Shuttering (m2)\")\n"
    "            ]\n"
    "        )\n"
    "\n"
    "        item_number += 1\n"
    "\n"
    "    total_row_number = len(out_rows) + 1\n"
    "\n"
    "    vol_col = 4\n"
    "    shut_col = 5\n"
    "\n"
    "    vol_letter = xlsx_column_name(vol_col)\n"
    "    shut_letter = xlsx_column_name(shut_col)\n"
    "\n"
    "    out_rows.append(\n"
    "        [\n"
    "            \"TOTAL\",\n"
    "            \"\",\n"
    "            \"\",\n"
    "            (\n"
    "                \"FORMULA\",\n"
    "                \"SUM({0}{1}:{0}{2})\".format(\n"
    "                    vol_letter, first_data_row, total_row_number - 1)\n"
    "            ),\n"
    "            (\n"
    "                \"FORMULA\",\n"
    "                \"SUM({0}{1}:{0}{2})\".format(\n"
    "                    shut_letter, first_data_row, total_row_number - 1)\n"
    "            )\n"
    "        ]\n"
    "    )\n"
    "\n"
    "    meta = {\n"
    "        \"present_categories\": present_categories,\n"
    "        \"columns\": {\n"
    "            \"Volume (m3)\": vol_letter,\n"
    "            \"Shuttering (m2)\": shut_letter\n"
    "        },\n"
    "        \"total_columns\": 5,\n"
    "        \"bands\": (5, 6),\n"
    "        \"grid_start\": first_data_row,\n"
    "        \"levels\": []\n"
    "    }\n"
    "\n"
    "    return (out_rows, meta)"
)

new_src = src[:start_match.start()] + new_body + src[end_pos_full:]

with io.open(PATH, "w", encoding="utf-8", newline="") as fh:
    fh.write(new_src)

print("OK: summary now aggregates VOLUME + SHUTTERING per category")

py_compile.compile(PATH, doraise=True)
print("COMPILE OK")