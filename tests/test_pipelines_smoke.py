import os

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stamp', 'examples', 'EnterotypesArumugam')


def test_three_pipelines_run_headless():
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
	prefs = {'Pseudocount': 0.5, 'Replicates': 1000}
	tree, err = StampIO(prefs).read(os.path.join(EX, 'Enterotypes.profile.spf'))
	md, err = MetadataIO(prefs).read(os.path.join(EX, 'Enterotypes.metadata.tsv'), tree)
	names = tree.sampleNames
	sp = tree.createSampleProfile(names[0], names[1], 'Entire sample', tree.hierarchyHeadings[-1], 'Remove unclassified reads')
	from stamp.metagenomics.stats.SampleStatsTests import SampleStatsTests
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptotic import DiffBetweenPropAsymptotic
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	t = SampleStatsTests(prefs)
	t.run(Fishers(prefs), 'Two-sided', DiffBetweenPropAsymptotic(prefs), 0.95, sp)
	t.results.performMultCompCorrection(NoCorrection(prefs))
	assert len(t.results.data) == 247
	# two groups
	md.setActiveField('Enterotype', tree)
	gp = tree.createGroupProfile('Enterotype 1', 'Enterotype 2', 'Entire sample', tree.hierarchyHeadings[0], md, 'Remove unclassified reads')
	from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	from stamp.plugins.groups.statisticalTests.Ttest import Ttest
	from stamp.plugins.groups.effectSizeFilters.DiffBetweenProp import DiffBetweenProp
	g = GroupStatsTests(prefs)
	g.run(Welch(prefs), 'Two-sided', None, 0.95, gp)
	g.results.performMultCompCorrection(NoCorrection(prefs))
	assert len(g.results.data) == 16
	# multi groups
	mgp = tree.createMultiGroupProfile(list(tree.groupDict.keys()), 'Entire sample', tree.hierarchyHeadings[0], md, 'Remove unclassified reads')
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatsTests
	from stamp.plugins.multiGroups.statisticalTests.ANOVA import ANOVA
	from stamp.plugins.multiGroups.postHoc.TukeyKramer import TukeyKramer
	m = MultiGroupStatsTests(prefs)
	from stamp.plugins.multiGroups.effectSizeFilters.EtaSquared import EtaSquared
	m.run(ANOVA(prefs), EtaSquared(prefs), mgp)
	m.results.performMultCompCorrection(NoCorrection(prefs))
	assert len(m.results.data) == 16
