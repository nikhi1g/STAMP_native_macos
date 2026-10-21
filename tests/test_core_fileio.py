"""File readers: StampIO, MetadataIO, COG_IO, MgRastIO, plus profile construction and PCA.

Expected values are computed independently from the raw files with the csv module.
"""
import csv
import glob
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from stamp.metagenomics.fileIO.StampIO import StampIO
from stamp.metagenomics.fileIO.MetadataIO import MetadataIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM = os.path.join(ROOT, 'stamp')
EXAMPLES = os.path.join(UPSTREAM, 'examples')
ENTERO = os.path.join(EXAMPLES, 'EnterotypesArumugam')
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000}


def read_tsv(path):
	with open(path, newline='') as f:
		return [row for row in csv.reader(f, delimiter='\t') if row and any(c.strip() for c in row)]


@pytest.fixture(scope='module')
def entero():
	tree, err = StampIO(PREFS).read(os.path.join(ENTERO, 'Enterotypes.profile.spf'))
	assert err is None
	return tree


def test_stampio_enterotypes(entero):
	rows = read_tsv(os.path.join(ENTERO, 'Enterotypes.profile.spf'))
	header, body = rows[0], rows[1:]
	assert entero.hierarchyHeadings == ['Phyla', 'Genera'] == header[:2]
	assert entero.sampleNames == [h.strip() for h in header[2:]]
	assert entero.numSamples() == 39
	columnSums = np.array([[float(x) for x in r[2:]] for r in body]).sum(axis=0)
	assert entero.numSeqInSample == pytest.approx(list(columnSums), rel=1e-12)
	assert entero.numSequencesInSample(entero.sampleNames[3]) == pytest.approx(columnSums[3], rel=1e-12)
	leaves = entero.getLeafNodes()
	assert len(leaves) == 248
	phyla = {r[0] for r in body}
	assert {c.name for c in entero.root.children} == phyla
	assert entero.getHierarchicalLevelDepth('Genera') == 2


GOOD_PROFILES = {
	'BIOM-test/predicted_metagenomes.L3.ground_truth.spf': (['Observation Ids'], 2, 333),
	'CI_example.spf': (['Level 1', 'Level 2'], 2, 12),
	'CoalSeamGas/coal.spf': (['Domain', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species'], 44, 682),
	'CowRumen-MG-RAST/CowRumen.spf': (['level 1', 'level 2', 'level 3', 'function'], 4, 7196),
	'EBPR/MartinEBPR_A_phosphatis_Phosphate_Metabolism.spf': (['Functional Role Assignment'], 2, 26),
	'IronMineEdwards/EdwardsIronMine.spf': (['Classification', 'Subclassification', 'Subsystem'], 2, 247),
	'Melainabacteria/cog_category_table.spf': (['COG Category'], 97, 24),
	'heatmap.spf': (['Category'], 4, 3),
	'table_stamp.txt': (['Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species'], 62, 40),
}


@pytest.mark.parametrize('name', sorted(GOOD_PROFILES))
def test_stampio_example_profiles(name):
	tree, err = StampIO(PREFS).read(os.path.join(EXAMPLES, name))
	assert err is None
	headings, samples, leaves = GOOD_PROFILES[name]
	assert (tree.hierarchyHeadings, tree.numSamples(), len(tree.getLeafNodes())) == (headings, samples, leaves)


@pytest.mark.parametrize('name, message', [
	('FinegoldAutism/Autism.spf', 'Data does not form a strict hierarchy. Child Pasteurellales has multiple parents (e.g., Gammeproteobacteria, Gammaproteobacteria).'),
	('EBPR/MartinEBPR.spf', 'Child RuvABC_plus_a_hypothetical has an unclassified parent.'),
	('MouseGut-IMG-M/MouseGut.COG.profile.tsv', 'Data does not form a strict hierarchy. Child Predicted sugar kinase has multiple parents (e.g., COG0061, COG0063).'),
])
def test_stampio_rejects_non_hierarchies(name, message):
	assert StampIO(PREFS).read(os.path.join(EXAMPLES, name)) == (None, message)


def test_stampio_format_errors(tmp_path):
	one = tmp_path / 'one.spf'
	one.write_text('Feature\tS1\na\t1\n')
	assert StampIO(PREFS).read(str(one)) == (None, 'Profile file must contain at least two samples.')
	noFeature = tmp_path / 'nofeature.spf'
	noFeature.write_text('S1\tS2\n1\t2\n')
	assert StampIO(PREFS).read(str(noFeature)) == (None, 'Profile file must contain a column indicating feature names.')
	bad = tmp_path / 'bad.spf'
	bad.write_text('Feature\tS1\tS2\na\t1\t2\nb\t1\tx\n')
	tree, err = StampIO(PREFS).read(str(bad))
	assert err == 'Failed to correctly parse line: 3'
	# CRLF line endings are read as universal newlines
	crlf = tmp_path / 'crlf.spf'
	crlf.write_bytes(b'Feature\tS1\tS2\r\na\t1\t2\r\nb\t3\t4\r\n')
	tree, err = StampIO(PREFS).read(str(crlf))
	assert err is None and tree.sampleNames == ['S1', 'S2'] and tree.numSeqInSample == [4.0, 6.0]


def test_unclassified_treatment():
	tree, err = StampIO(PREFS).read(os.path.join(EXAMPLES, 'CoalSeamGas', 'coal.spf'))
	s1, s2 = tree.sampleNames[:2]
	removed = tree.createSampleProfile(s1, s2, 'Entire sample', 'Family', 'Remove unclassified reads')
	retained = tree.createSampleProfile(s1, s2, 'Entire sample', 'Family', 'Retain unclassified reads')
	freqOnly = tree.createSampleProfile(s1, s2, 'Entire sample', 'Family', 'Use only for calculating frequency profiles')
	unclassified = [f for f in retained.getFeatures() if 'unclassified' in f.lower()]
	assert unclassified and not any('unclassified' in f.lower() for f in removed.getFeatures())
	assert set(removed.getFeatures()) == set(retained.getFeatures()) - set(unclassified) == set(freqOnly.getFeatures())
	total = tree.numSequencesInSample(s1)
	f = removed.getFeatures()[0]
	# parent counts: 'Remove' drops unclassified reads from the parent total, 'frequency only' keeps them
	assert freqOnly.getParentCounts(f)[0] == pytest.approx(total)
	assert removed.getParentCounts(f)[0] == pytest.approx(total - sum(retained.getFeatureCounts(u)[0] for u in unclassified))


def test_metadataio_enterotypes(entero):
	md, err = MetadataIO(PREFS).read(os.path.join(ENTERO, 'Enterotypes.metadata.tsv'), entero)
	assert err is None
	rows = read_tsv(os.path.join(ENTERO, 'Enterotypes.metadata.tsv'))
	header = rows[0]
	assert md.getFeatures() == header[1:]
	assert [f for f in header if f.endswith('[filtered]')] == ['Clinical Status [filtered]', 'Nationality [filtered]', 'Gender [filtered]']
	assert sorted(md.activeSamples) == sorted(entero.sampleNames)
	assert md.numActiveSamples() == 39
	for row in rows[1:]:
		for field, value in zip(header[1:], row[1:]):
			assert md.getValue(row[0], field) == value.strip()
	assert not md.isNumericalData('Gender [filtered]')

	field = 'Clinical Status [filtered]'
	md.setActiveField(field, entero)
	col = header.index(field)
	expected = {}
	for row in rows[1:]:
		expected.setdefault(row[col], []).append(row[0])
	assert {k: sorted(v) for k, v in entero.groupDict.items()} == {k: sorted(v) for k, v in expected.items()}
	assert 'na' in entero.groupDict and all(entero.groupActive.values())
	assert entero.numSequencesInGroup('healthy', md) == pytest.approx(
		sum(entero.numSequencesInSample(s) for s in expected['healthy']))

	table, headings = md.getTableData()
	assert headings == ['Sample Id'] + sorted(header[1:])
	assert [r[0] for r in table] == sorted(entero.sampleNames)


def test_metadataio_numeric_fields():
	path = os.path.join(EXAMPLES, 'FinegoldAutism', 'Austism.metadata.tsv')
	rows = read_tsv(path)
	stub = SimpleNamespace(sampleNames=[r[0] for r in rows[1:]])
	md, err = MetadataIO(PREFS).read(path, stub)
	assert err is None
	assert md.isNumericalData('Severity') and not md.isNumericalData('Group')
	assert sorted(md.getUniqueValues('Autistic')) == sorted({r[2] for r in rows[1:]})


def test_metadataio_warnings(entero, tmp_path):
	path = tmp_path / 'md.tsv'
	lines = ['Sample Id\tGroup'] + ['%s\tA' % s for s in entero.sampleNames[1:]] + ['ghost\tB', '']
	path.write_text('\n'.join(lines))
	md, err = MetadataIO(PREFS).read(str(path), entero)
	assert err == 'Missing metadata for the following samples: ' + entero.sampleNames[0]
	lines = ['Sample Id\tGroup'] + ['%s\tA' % s for s in entero.sampleNames] + ['ghost\tB']
	path.write_text('\n'.join(lines))
	md, err = MetadataIO(PREFS).read(str(path), entero)
	assert err == 'Unknown sample(s) specified in metadata file: ghost\n\n'
	assert md.numActiveSamples() == 39


def test_cog_io_appends_categories(tmp_path, monkeypatch):
	from stamp.metagenomics.fileIO import COG_IO as cogModule
	monkeypatch.setattr(cogModule, 'getMainDir', lambda: UPSTREAM)
	whog = {}
	with open(os.path.join(UPSTREAM, 'stamp', 'data', 'whog.txt')) as f:
		for line in f:
			if line.startswith('['):
				whog[line.split()[1]] = line[1:line.index(']')]
	assert (whog['COG0001'], whog['COG0002'], whog['COG0059']) == ('H', 'E', 'EH')

	out = tmp_path / 'features.spf'
	cogModule.COG_IO().appendCategories(os.path.join(EXAMPLES, 'Assign_COGs_Example.tsv'), 'Treat multi-code COGs as features', str(out), PREFS)
	rows = read_tsv(str(out))
	assert rows[0] == ['COG classes', 'COG category names', 'COG category codes', 'COG annotations', 'COG IDs', 'Sample 1', 'Sample 2']
	assert rows[1] == ['Metabolism', 'Coenzyme transport and metabolism', 'H', 'Could', 'COG0001', '5', '1']
	assert rows[3] == ['EH', 'EH', 'EH', 'anything', 'COG0059', '4', '1']
	assert len(rows) == 4

	out2 = tmp_path / 'split.spf'
	cogModule.COG_IO().appendCategories(os.path.join(EXAMPLES, 'Assign_COGs_Example.tsv'), 'Assign sequence to each COG code', str(out2), PREFS)
	rows = read_tsv(str(out2))
	assert [r[2] for r in rows[1:]] == ['H', 'E', 'E', 'H']
	assert rows[3][:2] == ['Metabolism', 'Amino acid transport and metabolism']
	# splitting a multi-code COG gives its annotation two parents, which StampIO rejects
	assert StampIO(PREFS).read(str(out2)) == (None, 'Data does not form a strict hierarchy. Child anything has multiple parents (e.g., E, H).')
	tree, err = StampIO(PREFS).read(str(out))
	assert err is None and tree.numSeqInSample == [5 + 1 + 4, 1 + 8 + 1]


def test_mgrast_metabolic_parser(tmp_path):
	from stamp.metagenomics.fileIO.MgRastIO import MgRastIO
	path = tmp_path / 'mgrast.tsv'
	path.write_text('l1\tl2\tl3\tcount\n'
					'A\ta1\tx\t3\n'
					'A\t\ty\t2\n'
					'B\tb1\tz\t5.5\n')
	profile, parent, hierarchy, total = MgRastIO().parseMetabolicFile(str(path), 1, 0)
	# blank level-2 names are replaced with the level-1 name
	assert profile == {'a1': 3.0, 'A': 2.0, 'b1': 5.5}
	assert parent == {'A': 5.0, 'B': 5.5}
	assert hierarchy == {'a1': ['A'], 'A': ['A'], 'b1': ['B']}
	assert total == 10.5
	assert MgRastIO().parsePhylogeneticFile(str(path), 'l1') == {}


def test_group_feature_matrix_and_pca(entero):
	from stamp.metagenomics.PCA import pca
	md, _ = MetadataIO(PREFS).read(os.path.join(ENTERO, 'Enterotypes.metadata.tsv'), entero)
	md.setActiveField('Enterotype', entero)
	gp = entero.createGroupProfile('Enterotype 1', 'Enterotype 3', 'Entire sample', 'Genera', md, 'Remove unclassified reads')
	matrix = gp.getFeatureMatrix()
	assert matrix.shape == (8 + 18, gp.getNumFeatures())
	assert np.allclose(matrix.sum(axis=1), 1.0)  # proportions of each sample sum to one
	posEig, varEig = pca(matrix.copy(), 'eig')
	posSvd, varSvd = pca(matrix.copy(), 'svd')
	assert sum(varSvd) == pytest.approx(1.0)
	assert varEig[:5] == pytest.approx(varSvd[:5], rel=1e-8)
	# principal coordinates agree up to sign per component
	for c in range(3):
		assert np.allclose(np.abs(posEig[:, c]), np.abs(posSvd[:, c]), rtol=1e-6, atol=1e-10)
	ref = np.linalg.svd(matrix - matrix.mean(axis=0), compute_uv=False) ** 2
	assert varSvd == pytest.approx(ref / ref.sum(), rel=1e-9)


def test_directory_helper():
	from stamp.metagenomics.DirectoryHelper import runningExecutable, getMainDir
	assert not runningExecutable()
	assert getMainDir() == sys.path[0]
