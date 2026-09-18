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
readers (get_element_identity_text, classify_rcc_element,
build_logical_rcc_collections) stay in script.py by design.
"""
import re


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
