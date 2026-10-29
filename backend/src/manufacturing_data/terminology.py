"""Conservative schema aliases; resolving a name never converts or merges values."""
import re

TERMS = {
    'viable_cell_density': ('vcd', 'viable cell density'),
    'total_cell_density': ('tcd', 'total cell density'),
    'dissolved_oxygen': ('dissolved oxygen', 'do', 'do2'),
    'dissolved_carbon_dioxide': ('dco2', 'dissolved co2', 'dissolved carbon dioxide'),
    'ammonium': ('nh4', 'ammonium'),
    'glucose': ('glc', 'glucose'),
    'viability': ('viability',),
    'ph': ('ph',),
}

def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()

def canonical(header, unit=None):
    # Mean and SEM remain distinct original names in all retrieval results.
    base = normalize(re.sub(r'\([^)]*\)', '', header))
    base = re.sub(r'\b(mean|sem|std|sd)\b', '', base).strip()
    matches = [key for key, aliases in TERMS.items() if base == normalize(key) or base in aliases]
    ambiguous = base in ('do', 'do2') and unit not in ('%', 'percent', '% air saturation', 'mg/L', 'mg/l')
    return {'canonical_name': matches[0] if len(matches) == 1 and not ambiguous else None,
            'status': 'ambiguous' if ambiguous else ('alias' if matches else 'unmapped'),
            'original_header': header, 'unit': unit,
            'conversion': 'none; units and sampling contexts are preserved'}

def query_matches(query, header, unit=None):
    q = normalize(query)
    if not q:
        return False
    name = normalize(header)
    base = normalize(re.sub(r'\([^)]*\)', '', header))
    meta = canonical(header, unit)
    aliases = TERMS.get(meta['canonical_name'], ())
    # Exact token phrases prevent DO from matching unrelated prose words.
    return any((q == a if a in ('do','do2') else
                bool(re.search(r'(?<!\w)' + re.escape(normalize(a)) + r'(?!\w)', q)))
               for a in (*aliases, *([meta['canonical_name']] if meta['canonical_name'] else []))) or q in (name,base)
