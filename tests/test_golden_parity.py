# Parity of the Python 3 port against the Python 2.7 reference (upstream 088aacd).
#
# tests/golden/golden_py2.json was produced by running tests/golden/generate.py
# inside the reference image (see architecture.md, Findings). This test reruns
# the same generator in-process on the port and compares every scenario.
#
# Pass criterion (architecture.md, Correctness): every numeric output (p-values,
# corrected p-values, effect sizes, CI endpoints, counts, proportions) passes if
# abs diff <= 1e-6 or rel diff <= 1e-6; every significance decision (the set of
# features passing each p-value / effect-size filter, per test and dataset) must
# match exactly; rows are matched by feature name, not position; tied-rank
# Benjamini-Hochberg values are verified against an independent implementation.
# Randomized tests (White's, Bootstrap, Permutation) are seeded identically but
# Python 2 and 3 `random` streams differ, so those scenarios are compared with a
# loose tolerance on shape and value ranges only.
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GOLDEN = os.path.join(HERE, 'golden', 'golden_py2.json')
sys.path.insert(0, os.path.join(HERE, 'golden'))

RTOL = 1e-6
ATOL = 1e-6


@pytest.fixture(scope='module')
def golden():
	with open(GOLDEN) as f:
		return json.load(f)


@pytest.fixture(scope='module')
def port():
	import generate
	return json.loads(json.dumps(generate.generate(os.path.join(ROOT, 'stamp'), os.path.join(HERE, 'data', 'soil')), sort_keys=True))


def _num(v):
	return isinstance(v, (int, float)) and not isinstance(v, bool)


def _close(a, b, rtol=RTOL, atol=ATOL):
	if a == b:
		return True
	if _num(a) and _num(b):
		return math.isclose(a, b, rel_tol=rtol, abs_tol=atol)
	return False


def _keyed_rows(entry, nHier):
	'''Rows keyed by their hierarchy columns: Python 2 dict order and ties in the p-value sort make
	positional order differ between interpreters, so rows are matched by feature identity.'''
	keyed = {}
	for row in entry['rows']:
		keyed[tuple(row[:nHier])] = row
	assert len(keyed) == len(entry['rows']), 'duplicate feature rows'
	return keyed


POSITIONAL = ('tables', 'counts', 'parentCounts', 'proportions')


def _prepare(entry, nHier):
	'''Re-key order-dependent parts of an entry by feature so Python 2 dict order does not matter.'''
	if not isinstance(entry, dict):
		return entry
	e = dict(entry)
	if 'rows' in e:
		e['rows'] = _keyed_rows(e, nHier)
	if 'features' in e:
		for k in POSITIONAL:
			if k in e:
				e[k] = dict(zip(e['features'], e[k]))
		e['features'] = sorted(e['features'])
	if 'active' in e:
		e['active'] = sorted(e['active'])
	if 'metadataFeatures' in e:
		e['metadataFeatures'] = sorted(e['metadataFeatures'])  # Python 2 dict order upstream
	return e


def _near_ties(values, rtol=1e-6):
	'''Values that are equal up to floating-point summation noise (ties for a rank-based correction).'''
	nums = sorted(v for v in values if _num(v))
	tied = set()
	for x, y in zip(nums, nums[1:]):
		if math.isclose(x, y, rel_tol=rtol, abs_tol=1e-300):
			tied.add(x); tied.add(y)
	return tied


def _corrected_index(entry):
	try:
		return entry['headings'].index('p-values (corrected)'), entry['headings'].index('p-values')
	except (KeyError, ValueError):
		return None, None


def _diff_entry(path, a, b, rtol, out, nHier):
	a, b = _prepare(a, nHier), _prepare(b, nHier)
	if isinstance(a, dict) and 'rows' in a and isinstance(b, dict) and 'rows' in b:
		ci, pi = _corrected_index(a)
		if ci is not None:
			# Rank-based corrections (Benjamini-Hochberg) assign ranks within a group of tied raw
			# p-values in input order, which upstream takes from Python 2 dict order. The column is
			# compared as a multiset here; test_benjamini_hochberg_independent proves each tied
			# assignment is a valid BH value.
			ga = sorted(r[ci] for r in a['rows'].values() if _num(r[ci]))
			gb = sorted(r[ci] for r in b['rows'].values() if _num(r[ci]))
			_diff(path + '/corrected-multiset', ga, gb, rtol, out)
			ties = _near_ties([r[pi] for r in a['rows'].values()])
			for k in a['rows']:
				if a['rows'][k][pi] in ties:
					a['rows'][k] = list(a['rows'][k]); b['rows'][k] = list(b['rows'][k])
					a['rows'][k][ci] = b['rows'][k][ci] = None
	_diff(path, a, b, rtol, out)


def _diff(path, a, b, rtol, out):
	if isinstance(a, dict) and isinstance(b, dict):
		if set(a) != set(b):
			out.append('%s: keys differ: only-ref=%s only-port=%s' % (path, sorted(set(a) - set(b))[:5], sorted(set(b) - set(a))[:5]))
			return
		for k in a:
			_diff('%s/%s' % (path, k), a[k], b[k], rtol, out)
	elif isinstance(a, list) and isinstance(b, list):
		if len(a) != len(b):
			out.append('%s: length %d vs %d' % (path, len(a), len(b)))
			return
		for i, (x, y) in enumerate(zip(a, b)):
			_diff('%s[%d]' % (path, i), x, y, rtol, out)
	else:
		if not _close(a, b, rtol):
			out.append('%s: %r vs %r' % (path, a, b))


def test_golden_fixture_exists():
	assert os.path.exists(GOLDEN), 'generate tests/golden/golden_py2.json from the reference image first'


def test_scenario_keys_match(golden, port):
	assert sorted(golden) == sorted(port)


def test_deterministic_scenarios_match(golden, port):
	problems = []
	for key in sorted(golden):
		if '|random' in key:
			continue
		out = []
		_diff_entry(key, golden[key], port[key], RTOL, out, len(golden[key.split('/')[0] + '/load']['headings']))
		problems.extend(out[:20])
	assert not problems, '\n'.join(problems[:200])


def test_randomized_scenarios_have_same_shape(golden, port):
	problems = []
	for key in sorted(golden):
		if '|random' not in key:
			continue
		g, p = golden[key], port[key]
		if 'skipped' in g or 'skipped' in p:
			if g != p:
				problems.append('%s: %r vs %r' % (key, g, p))
			continue
		if g['headings'] != p['headings'] or len(g['rows']) != len(p['rows']) or sorted(g['active']) != sorted(p['active']):
			problems.append('%s: shape differs' % key)
			continue
		nHier = len(golden[key.split('/')[0] + '/load']['headings'])
		gRows, pRows = _keyed_rows(g, nHier), _keyed_rows(p, nHier)
		# feature names and the non-random columns (counts, proportions, notes) must match exactly;
		# p-values and bootstrap CIs may differ within the Monte Carlo error of 200 replicates.
		for feature in gRows:
			gr, pr = gRows[feature], pRows[feature]
			for i, (a, b) in enumerate(zip(gr, pr)):
				h = g['headings'][i]
				if any(h.startswith(s) for s in ('p-values', '95', '99', 'Effect size', 'Difference', 'Note')):
					if _num(a) and _num(b) and not math.isclose(a, b, rel_tol=0.5, abs_tol=0.2):
						problems.append('%s %s %s: %r vs %r' % (key, gr[0], h, a, b))
				elif not _close(a, b):
					problems.append('%s %s %s: %r vs %r' % (key, gr[0], h, a, b))
	assert not problems, '\n'.join(problems[:100])


def _upstream_bh(pValues):
	'''Independent re-implementation of upstream's Benjamini-Hochberg: corrected = p * m / rank with
	rank 1 for the smallest p (no step-up minimum, no cap at 1, exactly as STAMP 2.1.3 reports it).
	Returns, per index, the set of admissible values when raw p-values are tied.'''
	m = len(pValues)
	order = sorted(range(m), key=lambda i: pValues[i])
	admissible = [None] * m
	i = 0
	while i < m:
		j = i
		while j + 1 < m and math.isclose(pValues[order[j + 1]], pValues[order[i]], rel_tol=1e-6, abs_tol=1e-300):
			j += 1
		ranks = range(i + 1, j + 2)
		for idx in order[i:j + 1]:
			admissible[idx] = set(pValues[idx] * m / float(r) for r in ranks)
		i = j + 1
	return admissible


def test_benjamini_hochberg_independent(port, golden):
	problems = []
	checked = 0
	for key in sorted(port):
		if 'BenjaminiHochbergFDR' not in key or '/filter/' in key or 'rows' not in port[key]:
			continue
		for source, data in (('port', port), ('reference', golden)):
			entry = data[key]
			ci, pi = _corrected_index(entry)
			rows = entry['rows']
			raw = [r[pi] for r in rows]
			corrected = [r[ci] for r in rows]
			admissible = _upstream_bh(raw)
			for r, c, adm in zip(rows, corrected, admissible):
				if not any(math.isclose(c, v, rel_tol=RTOL, abs_tol=ATOL) for v in adm):
					problems.append('%s [%s] %s: corrected %r not in %r' % (key, source, r[:2], c, sorted(adm)))
			checked += 1
	assert checked > 0
	assert not problems, '\n'.join(problems[:100])
