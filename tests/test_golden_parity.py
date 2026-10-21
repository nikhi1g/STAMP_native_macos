# Parity of the Python 3 port against the Python 2.7 reference (upstream 088aacd).
#
# tests/golden/golden_py2.json was produced by running tests/golden/generate.py
# inside the reference image (see architecture.md, Findings). This test reruns
# the same generator in-process on the port and compares every scenario.
#
# Pass criterion (architecture.md): p-values, effect sizes and confidence
# intervals equal to 1e-9 relative tolerance; filtered feature lists exact.
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

RTOL = 1e-9
ATOL = 1e-12


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
		_diff(key, golden[key], port[key], RTOL, out)
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
		if g['headings'] != p['headings'] or len(g['rows']) != len(p['rows']) or g['active'] != p['active']:
			problems.append('%s: shape differs' % key)
			continue
		# feature names and the non-random columns (counts, proportions, notes) must match exactly;
		# p-values and bootstrap CIs may differ within the Monte Carlo error of 200 replicates.
		for gr, pr in zip(g['rows'], p['rows']):
			for i, (a, b) in enumerate(zip(gr, pr)):
				h = g['headings'][i]
				if any(h.startswith(s) for s in ('p-values', '95% ', '99% ', 'Effect size', 'Difference')):
					if _num(a) and _num(b) and not math.isclose(a, b, rel_tol=0.5, abs_tol=0.2):
						problems.append('%s %s %s: %r vs %r' % (key, gr[0], h, a, b))
				elif not _close(a, b):
					problems.append('%s %s %s: %r vs %r' % (key, gr[0], h, a, b))
	assert not problems, '\n'.join(problems[:100])
