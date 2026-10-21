# The 109BL lab manual's "STAMP Demo Data Tutorial" (CI-5): Skirball Fire soil samples,
# profile level Phylum, two groups by "Burn status", extended error bar, p-value filter
# checked -> "only Bacteroidetes remains" (enriched in unburned soil).
#
# Data: the historical Skirball S18 public tutorial table (14 samples) collapsed to phylum,
# from projLab/mimg (lib/analysis/ci2/fixtures/skirball-reference/phylum_sums.tsv.gz) with
# the all-"Unclassified" kingdom column dropped, as STAMP's hierarchy check requires.
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, 'data', 'skirball', 'skirball_phylum.spf')
METADATA = os.path.join(HERE, 'data', 'skirball', 'skirball_metadata.tsv')
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000}


def _group_profile():
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
	tree, err = StampIO(PREFS).read(PROFILE)
	assert err is None, err
	metadata, warning = MetadataIO(PREFS).read(METADATA, tree)
	assert warning is None, warning
	metadata.setActiveField('Burn status', tree)
	assert sorted(tree.groupDict) == ['Burned', 'Unburned']
	assert len(tree.groupDict['Burned']) == 7 and len(tree.groupDict['Unburned']) == 7
	return tree.createGroupProfile('Burned', 'Unburned', 'Entire sample', 'Phylum', metadata, 'Retain unclassified reads')


@pytest.mark.parametrize('testName', ['Welch', 'Ttest'])
def test_only_bacteroidetes_remains_after_p_value_filter(testName):
	import importlib
	from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	test = getattr(importlib.import_module('stamp.plugins.groups.statisticalTests.' + testName), testName)(PREFS)
	profile = _group_profile()
	assert profile.getNumFeatures() == 37

	stats = GroupStatsTests(PREFS)
	stats.run(test, 'Two-sided', test.confIntervMethods[0], 0.95, profile)
	stats.results.performMultCompCorrection(NoCorrection(PREFS))
	stats.results.selectAllFeautres()
	stats.results.filterFeatures(0.05, None, None, None, None, None, None, None, None, 'OR', None, None)
	assert stats.results.getActiveFeatures() == ['Bacteroidetes']

	# enriched in unburned soil: a negative Burned - Unburned difference
	features = stats.results.getColumn('Features', False)
	effect = stats.results.getColumn('EffectSize', False)
	assert effect[features.index('Bacteroidetes')] < 0
	p = stats.results.getColumn('pValues', False)[features.index('Bacteroidetes')]
	assert p < 0.001
