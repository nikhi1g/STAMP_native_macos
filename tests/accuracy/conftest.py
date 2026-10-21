"""Fixtures for the accuracy suite: plugin inputs extracted from real profiles through the same
profile objects the app builds (StampIO -> ProfileTree -> Sample/Group/MultiGroupProfile), plus a
terminal summary of the largest error measured for every compared quantity."""
import os

import pytest

import oracle

PREFS = oracle.PREFS


def _read(path, metadata=None):
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
	tree, err = StampIO(PREFS).read(path)
	assert err is None, err
	md = None
	if metadata:
		md, _ = MetadataIO(PREFS).read(metadata, tree)
	return tree, md


@pytest.fixture(scope='session')
def skirball_files(tmp_path_factory):
	d = tmp_path_factory.mktemp('skirball')
	sub, samples = oracle.skirball_phylum_profile(str(d / 'skirball400_phylum_class.spf'))
	full = oracle.skirball_sums_profile(str(d / 'skirball_phylum_sums.spf'))
	return {'subset': sub, 'sums': full, 'metadata': os.path.join(oracle.SKIRBALL, 'skirball-metadata.tsv')}


@pytest.fixture(scope='session')
def sample_tables(skirball_files):
	"""(label, seq1, seq2, total1, total2) for every feature of several two-sample profiles."""
	out = []
	tree, _ = _read(os.path.join(oracle.EXAMPLES, 'IronMineEdwards', 'EdwardsIronMine.spf'))
	sp = tree.createSampleProfile('Red', 'Black', 'Entire sample', 'Subsystem', 'Remove unclassified reads')
	out += [('iron/' + f,) + tuple(sp.getTableData(f)) for f in sp.getFeatures()]
	tree, _ = _read(skirball_files['subset'])
	for parent, level in [('Entire sample', 'Phylum'), ('Phylum', 'Class')]:
		sp = tree.createSampleProfile('S1', 'S8', parent, level, 'Retain unclassified reads')
		out += [('skirball400 S1/S8 %s/%s/' % (parent, level) + f,) + tuple(sp.getTableData(f)) for f in sp.getFeatures()]
	tree, _ = _read(skirball_files['sums'])
	sp = tree.createSampleProfile('S2', 'S5', 'Entire sample', 'Phylum', 'Remove unclassified reads')
	out += [('skirball S2/S5/' + f,) + tuple(sp.getTableData(f)) for f in sp.getFeatures()]
	tree, _ = _read(os.path.join(oracle.SOIL, 'soil_class_abundance.tsv'))
	sp = tree.createSampleProfile('UNC', 'GP', 'Entire sample', 'class', 'Remove unclassified reads')
	out += [('soil UNC/GP/' + f,) + tuple(sp.getTableData(f)) for f in sp.getFeatures()]
	return out



@pytest.fixture(scope='session')
def group_profiles(skirball_files):
	"""(label, GroupProfile) for real two-group comparisons."""
	out = []
	tree, md = _read(skirball_files['sums'], skirball_files['metadata'])
	md.setActiveField('Burn status', tree)
	out.append(('skirball burned/unburned', tree.createGroupProfile('Burned', 'Unburned', 'Entire sample', 'Phylum', md, 'Remove unclassified reads')))
	tree, md = _read(skirball_files['subset'], skirball_files['metadata'])
	md.setActiveField('Burn status', tree)
	out.append(('skirball400 burned/unburned class', tree.createGroupProfile('Burned', 'Unburned', 'Phylum', 'Class', md, 'Remove unclassified reads')))
	tree, md = _read(os.path.join(oracle.SOIL, 'soil_phylum_abundance.tsv'), os.path.join(oracle.SOIL, 'metadata.tsv'))
	md.setActiveField('Undisturbed vs Disturbed', tree)
	out.append(('soil Undisturbed(2)/Disturbed(4)', tree.createGroupProfile('Undisturbed', 'Disturbed', 'Entire sample', 'phylum', md, 'Remove unclassified reads')))
	ex = os.path.join(oracle.EXAMPLES, 'EnterotypesArumugam')
	tree, md = _read(os.path.join(ex, 'Enterotypes.profile.spf'), os.path.join(ex, 'Enterotypes.metadata.tsv'))
	md.setActiveField('Enterotype', tree)
	out.append(('enterotypes 1/2', tree.createGroupProfile('Enterotype 1', 'Enterotype 2', 'Entire sample', 'Genera', md, 'Remove unclassified reads')))
	return out


@pytest.fixture(scope='session')
def group_inputs(group_profiles):
	"""(label, counts1, counts2, parents1, parents2) per feature."""
	out = []
	for name, gp in group_profiles:
		for f in gp.getFeatures():
			c1, c2 = gp.getFeatureCounts(f)
			p1, p2 = gp.getParentFeatureCounts(f)
			out.append(('%s/%s' % (name, f), c1, c2, p1, p2))
	return out


@pytest.fixture(scope='session')
def multi_profiles(skirball_files):
	out = []
	ex = os.path.join(oracle.EXAMPLES, 'EnterotypesArumugam')
	tree, md = _read(os.path.join(ex, 'Enterotypes.profile.spf'), os.path.join(ex, 'Enterotypes.metadata.tsv'))
	md.setActiveField('Enterotype', tree)
	mgp = tree.createMultiGroupProfile(list(tree.groupDict.keys()), 'Entire sample', 'Genera', md, 'Remove unclassified reads')
	active = ('Enterotype 1', 'Enterotype 2', 'Enterotype 3')
	mgp.setActiveGroups({g: g in active for g in tree.groupDict})
	out.append(('enterotypes 3 groups', mgp))
	tree, md = _read(skirball_files['sums'], skirball_files['metadata'])
	md.setActiveField('Burn status', tree)
	out.append(('skirball burn status (2 groups)', tree.createMultiGroupProfile(list(tree.groupDict.keys()), 'Entire sample', 'Phylum', md, 'Remove unclassified reads')))
	md.setActiveField('Section', tree)
	out.append(('skirball section (2 groups)', tree.createMultiGroupProfile(list(tree.groupDict.keys()), 'Entire sample', 'Phylum', md, 'Remove unclassified reads')))
	return out


@pytest.fixture(scope='session')
def multi_inputs(multi_profiles):
	"""(label, data, groupNames): data is getActiveFeatureProportions (percent per sample)."""
	out = []
	for name, mgp in multi_profiles:
		for f in mgp.getFeatures():
			out.append(('%s/%s' % (name, f), mgp.getActiveFeatureProportions(f), list(mgp.activeGroupNames)))
	return out


def pytest_terminal_summary(terminalreporter):
	if not oracle.MEASURED:
		return
	tr = terminalreporter
	tr.section('accuracy: largest error measured per quantity (port vs mpmath oracle)')
	tr.write_line('%-58s %10s %10s %6s  %s' % ('quantity', 'max rel', 'max abs', 'n', 'tolerance (rel, abs)'))
	for label in sorted(oracle.MEASURED):
		r, a, n, tol = oracle.MEASURED[label]
		tol_s = 'reported only' if tol[0] is None else '%.0e, %.0e' % tol
		tr.write_line('%-58s %10.2e %10.2e %6d  %s' % (label[:58], r, a, n, tol_s))
