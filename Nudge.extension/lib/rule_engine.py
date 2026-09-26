# -*- coding: utf-8 -*-
"""Rule engine (P8) - host-free RCC classification and audit rules.

Moved verbatim from BOQ.pushbutton/script.py in the v1.24.0 split
(PROJECT_STRUCTURE.md section 9, the P8 landing point). These are the
decision rules the Slab/Foundation classifier is built on: label
normalization, structural code-token matching, identity signals, the
routing key used to de-duplicate elements across logical sheets, and
the audit validation the export refuses to ignore.

Pure Python - no Revit or pyRevit symbol appears here. The functions
that take an `element` only read it through getattr, so the harness can
exercise every rule with a plain stand-in object. The Revit-bound
readers (get_element_identity_text, _element_family_type_names,
_read_identity_parameter) stay in script.py by design, and
classify_rcc_element there is the thin wrapper that reads an element
and hands the text to classify_identity_text below.
"""
import re

from parameter_engine import safe_text


def normalize_label(value):
    try:
        text = str(value or '').lower()
    except:
        text = ''

    # Keep codes such as S1 / GS / CF intact while normalizing
    # spaces, underscores, hyphens, and punctuation.
    try:
        text = re.sub(r'[_\-]+', ' ', text)
        text = re.sub(r'[^a-z0-9]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
    except:
        pass

    return text

def code_token_match(text, prefixes):
    """Match complete RCC codes without accepting unsafe bare prefixes."""
    try:
        normalized = normalize_label(text)
        alternatives = []
        for prefix in prefixes:
            prefix_text = str(prefix or '').lower()
            if prefix_text in ('f', 'cf', 'wf'):
                # Owner-confirmed footing codes may carry one variant
                # letter after the number (F2A, CF1A, WF1).
                alternatives.append(re.escape(prefix_text) + r'[0-9]+[a-z]?')
            elif prefix_text == 's':
                alternatives.append(re.escape(prefix_text) + r'[0-9]+')
            elif prefix_text:
                alternatives.append(re.escape(prefix_text) + r'[0-9]*')
        if not alternatives:
            return False
        pattern = r'(?<![a-z0-9])(?:' + '|'.join(alternatives) + r')(?![a-z0-9])'
        return re.search(pattern, normalized) is not None
    except:
        return False

def _contains_rcc_identity_signal(value):
    """True only for construction words or complete RCC identity codes."""
    text = normalize_label(value)
    if not text:
        return False
    if any(
        phrase in text
        for phrase in (
            'pcc', 'footing', 'raft', 'grade slab', 'gradeslab',
            'fold slab', 'foldslab', 'slab', 'chajja'
        )
    ):
        return True
    return (
        code_token_match(text, ('f', 'cf', 'wf', 's'))
        or code_token_match(text, ('gs',))
    )

def _element_source_category(element, fallback=''):
    try:
        category = element.Category
        if category is not None and category.Name:
            return str(category.Name)
    except:
        pass
    return str(fallback or 'Unknown')

def _element_routing_key(element, fallback_index=None):
    try:
        return ('id', int(element.Id.IntegerValue))
    except:
        try:
            return ('id', int(element.Id.Value))
        except:
            return (
                'object',
                id(element) if fallback_index is None else fallback_index
            )

def _safe_element_id_text(element):
    key = _element_routing_key(element)
    return str(key[1]) if key[0] == 'id' else 'N/A'

def classify_identity_text(text, source_name):
    """Decide one logical RCC route from already-normalized identity text.

    This is the whole Slab/Foundation rule chain and nothing else: it
    reads no element and touches no Revit API, so a route can be argued
    about, tested and changed here rather than inside the reader that
    feeds it. `text` is what get_element_identity_text produced (already
    lowercased and normalized) and `source_name` is the raw Revit
    category the element was collected from.

    Returns a dict with `logical_group`, `subtype` and `reason`. The
    reason is user-facing - it appears in the routing audit - so it says
    which rule fired rather than restating the result.
    """
    normalized_source = normalize_label(source_name)

    # Foundation identities deliberately precede generic slab wording.
    if re.search(r'(?<![a-z0-9])pcc(?![a-z0-9])', text):
        return _route('Foundation', 'PCC', 'Explicit PCC identity')

    if (
        'combined footing' in text
        or 'combine footing' in text
        or code_token_match(text, ('cf',))
    ):
        return _route(
            'Foundation', 'Combined Footing',
            'Combined footing name or exact CF<number> code'
        )

    if 'footing' in text or code_token_match(text, ('f', 'wf')):
        return _route(
            'Foundation', 'Footing',
            'Footing name or exact F<number>/WF<number> code'
        )

    if 'combined raft' in text or 'combine raft' in text:
        return _route('Foundation', 'Combined Raft', 'Combined raft identity')

    if re.search(r'(?<![a-z0-9])raft(?![a-z0-9])', text):
        return _route('Foundation', 'Raft', 'Explicit raft identity')

    if (
        'grade slab' in text
        or 'gradeslab' in text
        or code_token_match(text, ('gs',))
    ):
        return _route('Slab', 'Grade Slab', 'Grade Slab name or exact GS code')

    if 'fold slab' in text or 'foldslab' in text:
        return _route('Slab', 'Fold Slab', 'Explicit Fold Slab identity')

    if 'slab' in text or code_token_match(text, ('s',)):
        return _route('Slab', 'Slab', 'Slab name or exact S<number> code')

    if re.search(r'(?<![a-z0-9])chajja(?:[0-9]+)?(?![a-z0-9])', text):
        return _route('Slab', 'Slab', 'Chajja is a logical slab')

    if re.search(r'(?<![a-z0-9])(?:lobby|ramp)(?![a-z0-9])', text):
        return _route('Slab', 'Slab', 'Lobby/Ramp floor type is a logical slab')

    # Nothing matched. An unknown element is never dropped and never
    # guessed into a priced subtype - it stays under the sheet its own
    # Revit category implies, marked Other for the audit to report.
    if 'foundation' in normalized_source:
        return _route(
            'Foundation', 'Other',
            'Unknown identity retained under source Foundation as Other'
        )

    return _route(
        'Slab', 'Other',
        'Unknown identity retained under source Floor as Other'
    )

def _route(logical_group, subtype, reason):
    return {
        'logical_group': logical_group,
        'subtype': subtype,
        'reason': reason,
    }

def build_logical_rcc_collections(floor_elements, foundation_elements, classify):
    """Classify raw collections once and return mutually exclusive lists.

    `classify(element, source_name)` is the Revit-bound classifier from
    script.py; it is injected rather than imported so this routing and
    its audit stay host-free. Both raw collections can feed either
    logical sheet, so an element is routed exactly once, by routing key,
    and anything seen twice is recorded as a duplicate instead of being
    counted twice.
    """
    slab_elements = []
    foundation_output = []
    results = []
    seen = {}
    source_duplicate_ids = []
    source_pairs = (
        ('Floors', list(floor_elements or [])),
        ('Structural Foundations', list(foundation_elements or [])),
    )

    sequence = 0
    for source_name, source_elements in source_pairs:
        for element in source_elements:
            sequence += 1
            key = _element_routing_key(element, sequence)
            if key in seen:
                source_duplicate_ids.append(_safe_element_id_text(element))
                continue
            seen[key] = True
            result = classify(element, source_name)
            result['routing_key'] = key
            results.append(result)
            if result['logical_group'] == 'Foundation':
                foundation_output.append(element)
            else:
                slab_elements.append(element)

    slab_keys = set(_element_routing_key(e) for e in slab_elements)
    foundation_keys = set(
        _element_routing_key(e) for e in foundation_output
    )
    destination_duplicates = sorted(
        str(key[1]) for key in slab_keys.intersection(foundation_keys)
    )
    unclassified = [
        result for result in results
        if result.get('logical_group') not in ('Slab', 'Foundation')
    ]
    other_results = [
        result for result in results if result.get('subtype') == 'Other'
    ]
    unique_total = len(results)
    audit = {
        'total_floor_source': len(source_pairs[0][1]),
        'total_foundation_source': len(source_pairs[1][1]),
        'eligible_unique': unique_total,
        'logical_slab': len(slab_elements),
        'logical_foundation': len(foundation_output),
        'source_duplicate_ids': source_duplicate_ids,
        'destination_duplicate_ids': destination_duplicates,
        'unclassified': unclassified,
        'other': other_results,
        'results': results,
        'balanced': (
            len(slab_elements) + len(foundation_output) == unique_total
            and not destination_duplicates
            and not unclassified
        ),
    }
    return {
        'Slab': slab_elements,
        'Foundation': foundation_output,
        'results': results,
        'audit': audit,
    }

def validate_classification_audit(audit):
    """Return (valid, summary); export must not ignore a discrepancy."""
    valid = bool(audit and audit.get('balanced'))
    summary = (
        'Floors={0}; Structural Foundations={1}; Slab={2}; '
        'Foundation={3}; Duplicates={4}; Unclassified={5}; Other={6}'
    ).format(
        audit.get('total_floor_source', 0) if audit else 0,
        audit.get('total_foundation_source', 0) if audit else 0,
        audit.get('logical_slab', 0) if audit else 0,
        audit.get('logical_foundation', 0) if audit else 0,
        (
            len(audit.get('source_duplicate_ids', []))
            + len(audit.get('destination_duplicate_ids', []))
        ) if audit else 0,
        len(audit.get('unclassified', [])) if audit else 0,
        len(audit.get('other', [])) if audit else 0,
    )
    return valid, summary

def classification_audit_has_findings(audit):
    """True only when the routing audit needs user/developer attention."""
    valid, _summary = validate_classification_audit(audit)
    if not valid:
        return True
    if not audit:
        return True
    return bool(
        audit.get('source_duplicate_ids', [])
        or audit.get('destination_duplicate_ids', [])
        or audit.get('unclassified', [])
        or audit.get('other', [])
    )


def classification_audit_detail_results(audit):
    """Return only routing rows that explain an audit finding.

    A project may contain thousands of correctly classified elements and only
    one controlled ``Other`` route. Emitting every healthy row in that case
    makes pyRevit's output window expensive enough to stall the export. Keep
    the diagnostic trace focused on unclassified, Other, and duplicate rows.
    """
    if not audit:
        return []

    duplicate_ids = set(
        safe_text(value, '') for value in (
            list(audit.get('source_duplicate_ids', []))
            + list(audit.get('destination_duplicate_ids', []))
        )
    )
    finding_keys = set()

    for result in (
        list(audit.get('unclassified', []))
        + list(audit.get('other', []))
    ):
        finding_keys.add(result.get('routing_key'))

    details = []
    seen = set()
    for result in audit.get('results', []):
        routing_key = result.get('routing_key')
        element_id = safe_text(result.get('element_id', ''), '')
        if routing_key not in finding_keys and element_id not in duplicate_ids:
            continue
        unique_key = routing_key or ('ElementId', element_id)
        if unique_key in seen:
            continue
        seen.add(unique_key)
        details.append(result)

    return details


def build_compact_classification_findings(audit, max_items=10):
    """Build a small user-facing list of only problematic routing rows."""
    def compact(value, fallback="-"):
        text = safe_text(value, fallback).strip()
        if not text:
            text = fallback
        if len(text) > 60:
            text = text[:57] + "..."
        return text

    details = classification_audit_detail_results(audit)
    try:
        limit = max(1, int(max_items))
    except:
        limit = 10

    lines = []
    for result in details[:limit]:
        family_type = "{} / {}".format(
            compact(result.get("family")),
            compact(result.get("type_name"))
        )
        identity_parts = []
        for label, key in (
            ("Mark", "mark"),
            ("ID_UNMT", "id_unmt"),
            ("ITEM DES.", "item_description"),
            ("CODE_UNIMONT", "code_unimont")
        ):
            value = compact(result.get(key), "")
            if value:
                identity_parts.append("{}={}".format(label, value))
        if not identity_parts:
            identity_parts.append("Identity=-")

        lines.append(
            "ID {} | {} | {} | {} | {}".format(
                compact(result.get("element_id"), "N/A"),
                compact(result.get("source_category")),
                family_type,
                "; ".join(identity_parts),
                compact(result.get("reason"))
            )
        )

    if len(details) > limit:
        lines.append("...and {} more finding(s)".format(len(details) - limit))

    duplicate_ids = list(audit.get("source_duplicate_ids", [])) if audit else []
    duplicate_ids.extend(
        list(audit.get("destination_duplicate_ids", [])) if audit else []
    )
    represented_ids = set(
        compact(result.get("element_id"), "N/A")
        for result in details[:limit]
    )
    for duplicate_id in duplicate_ids:
        duplicate_text = compact(duplicate_id, "N/A")
        if duplicate_text not in represented_ids:
            lines.append("ID {} | Duplicate routing source".format(duplicate_text))

    return "\n".join(lines)


CONCRETE_GRADE_VALUES = ("M10", "M15", "M20", "M25", "M30", "M35", "M40", "M45", "M50", "M55", "M60", "M65", "M70", "M75", "M80")


def normalize_concrete_grade(text):
    """
    P2: normalize a free-text fragment to a canonical concrete grade
    token ("M25"). Accepts M25 / m-25 / M 25 spellings. Returns ""
    when no recognizable grade token is present, so callers can fall
    through to the next resolution source.
    """
    try:
        candidate = str(text or "")
    except:
        return ""

    match = re.search(
        r"\bM\s*-?\s*(\d{2})\b",
        candidate,
        re.IGNORECASE
    )

    if not match:
        return ""

    normalized = "M" + match.group(1)

    if normalized in CONCRETE_GRADE_VALUES:
        return normalized

    return ""


def filter_logical_elements(elements, logical_tab, filter_name,
                            logical_group_of, slab_subtype_of,
                            foundation_subtype_of):
    """The Slab / Foundation tab's elements for one subtype filter.

    Moved from script.py's filter_elements in the P8 split (v1.48.0) with
    the three classifiers handed in, as build_logical_rcc_collections
    takes its classifier: `logical_group_of(element)` gives 'Slab' or
    'Foundation', and the two subtype readers the element's subtype. The
    "All ... Types" filter keeps every element of that logical group; any
    other filter keeps that subtype; any other tab keeps everything.
    """
    if logical_tab == 'Slab':
        if filter_name == 'All Slab Types':
            return [
                e for e in elements
                if logical_group_of(e) == 'Slab'
            ]

        return [
            e for e in elements
            if slab_subtype_of(e) == filter_name
        ]

    if logical_tab == 'Foundation':
        if filter_name == 'All Foundation Types':
            return [
                e for e in elements
                if logical_group_of(e) == 'Foundation'
            ]

        return [
            e for e in elements
            if foundation_subtype_of(e) == filter_name
        ]

    return list(elements)
