"""Merge this run's moments into the latest repo copy (two runners save at once)."""
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
for k, v in b.items():
    have = [x['w'] for x in a.get(k, [])]; a.setdefault(k, []).extend(x for x in v if x['w'] not in have)
json.dump(a, open(sys.argv[1], 'w'))
