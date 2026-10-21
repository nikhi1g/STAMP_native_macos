# Golden-output generator for STAMP parity tests.
#
# Runs unchanged under Python 2.7 (the upstream 088aacd reference inside the
# Docker image built from stamp_metagenomic_profiles' Dockerfile) and under the
# Python 3 port. It drives the same non-GUI code path the main window uses
# (ProfileTree -> *Profile -> *StatsTests -> performMultCompCorrection ->
# filterFeatures) over the bundled examples and the 109BL soil tables and dumps
# every result table as JSON.
#
#   python generate.py <upstream root> <soil data dir> <out.json>
#
# Randomized tests (White's, Bootstrap, Permutation) are seeded; their output is
# recorded but the parity test compares them with loose tolerances because the
# Python 2 and 3 `random` modules do not produce the same streams.
from __future__ import print_function
import json
import os
import random
import sys

upstream = os.path.abspath(sys.argv[1])
soilDir = os.path.abspath(sys.argv[2])
outPath = sys.argv[3]
sys.path.insert(0, upstream)

import numpy

from stamp.metagenomics.fileIO.StampIO import StampIO
from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
from stamp.metagenomics.stats.SampleStatsTests import SampleStatsTests
from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatsTests

prefs = {'Pseudocount': 0.5, 'Executable directory': upstream, 'Replicates': 200,
         'Minimum reported p-value exponent': -15}

def load(path, cls):
	module = __import__(path, fromlist=['*'])
	return getattr(module, cls)(prefs)

SAMPLE_TESTS = ['ChiSquare', 'ChiSquareYates', 'DiffBetweenProp', 'Fishers', 'GTest', 'GTestFisher', 'GTestYates', 'Hypergeometric']
SAMPLE_TESTS_RANDOM = ['Bootstrap', 'Permutation']
SAMPLE_CI = ['DiffBetweenPropAsymptotic', 'DiffBetweenPropAsymptoticCC', 'NewcombeWilson', 'OddsRatio', 'RatioProportions']
SAMPLE_ES = ['DiffBetweenProp', 'OddsRatio', 'RatioProportions']
GROUP_TESTS = ['Ttest', 'Welch']
GROUP_TESTS_RANDOM = ['White']
GROUP_ES = ['DiffBetweenProp', 'RatioProportions']
MULTI_TESTS = ['ANOVA', 'KruskalWallis']
MULTI_ES = ['EtaSquared']
POSTHOC = ['GamesHowell', 'Scheffe', 'TukeyKramer', 'WelchUncorrected']
CORRECTIONS = ['NoCorrection', 'Bonferroni', 'Sidak', 'BenjaminiHochbergFDR']
UNCLASSIFIED = ['Retain unclassified reads', 'Remove unclassified reads', 'Use only for calculating frequency profiles']

def clean(v):
	if isinstance(v, (list, tuple)):
		return [clean(x) for x in v]
	if isinstance(v, dict):
		return dict((str(k), clean(x)) for k, x in v.items())
	if isinstance(v, (numpy.floating,)):
		return float(v)
	if isinstance(v, (numpy.integer,)):
		return int(v)
	if isinstance(v, float):
		if v != v:
			return 'nan'
		if v in (float('inf'), float('-inf')):
			return 'inf' if v > 0 else '-inf'
		return v
	if isinstance(v, bytes) and not isinstance(v, str):
		return v.decode('utf-8')
	try:
		unicode  # noqa: Python 2 only
		if isinstance(v, unicode):
			return v.encode('utf-8').decode('utf-8')
	except NameError:
		pass
	return v

def record(results, extra=None):
	data, headings = results.tableData(False)
	d = {'headings': clean(headings), 'rows': clean(data), 'active': clean(list(results.getActiveFeatures()))}
	if extra:
		d.update(extra)
	return d

out = {}

def datasets():
	ex = os.path.join(upstream, 'examples', 'EnterotypesArumugam')
	yield ('enterotypes', os.path.join(ex, 'Enterotypes.profile.spf'), os.path.join(ex, 'Enterotypes.metadata.tsv'), 'Enterotype', 'Nationality')
	for level in ['phylum', 'class', 'genus']:
		yield ('soil_' + level, os.path.join(soilDir, 'soil_%s_abundance.tsv' % level), os.path.join(soilDir, 'metadata.tsv'), 'Undisturbed vs Disturbed', 'Site')

for name, profilePath, metadataPath, groupField, groupField2 in datasets():
	tree, err = StampIO(prefs).read(profilePath)
	assert err is None, err
	metadata, warn = MetadataIO(prefs).read(metadataPath, tree)
	out[name + '/load'] = {'samples': clean(tree.sampleNames), 'headings': clean(tree.hierarchyHeadings),
		'numSequences': clean([tree.numSequencesInSample(s) for s in tree.sampleNames]),
		'metadataFeatures': clean(metadata.getFeatures()), 'metadataWarning': clean(warn)}
	samples = tree.sampleNames
	levels = list(tree.hierarchyHeadings)
	configs = [('Entire sample', levels[-1])]
	if len(levels) > 1:
		configs.append(('Entire sample', levels[0]))
		configs.append((levels[0], levels[-1]))

	# ---- two samples
	for parent, level in configs:
		for unclassified in UNCLASSIFIED:
			profile = tree.createSampleProfile(samples[0], samples[1], parent, level, unclassified)
			key = '%s/samples/%s|%s|%s' % (name, parent, level, unclassified)
			out[key + '/profile'] = {'features': clean(profile.getFeatures()),
				'tables': clean([profile.getTableData(f) for f in profile.getFeatures()]),
				'numFeatures': profile.getNumFeatures(), 'numParentCategories': profile.getNumParentCategories()}
			if unclassified != UNCLASSIFIED[1] and (parent, level) != configs[0]:
				continue
			for testName in SAMPLE_TESTS:
				test = load('stamp.plugins.samples.statisticalTests.' + testName, testName)
				ciList = SAMPLE_CI if testName == 'Fishers' else SAMPLE_CI[:1]
				for ciName in ciList:
					ci = load('stamp.plugins.samples.confidenceIntervalMethods.' + ciName, ciName)
					for testType in ['Two-sided', 'One-sided']:
						if testType == 'One-sided' and ciName != SAMPLE_CI[0]:
							continue
						for coverage in ([0.95, 0.99] if (testName == 'Fishers' and ciName == 'NewcombeWilson') else [0.95]):
							st = SampleStatsTests(prefs)
							st.run(test, testType, ci, coverage, profile)
							for corrName in (CORRECTIONS if testName == 'Fishers' and ciName == SAMPLE_CI[0] and testType == 'Two-sided' else CORRECTIONS[:1]):
								corr = load('stamp.plugins.common.multipleComparisonCorrections.' + corrName, corrName)
								st.results.performMultCompCorrection(corr)
								st.results.filterFeatures(None, None, None, None, None, None, None, None, None, 'OR', None, None)
								k = '%s/%s|%s|%s|%s|%s' % (key, testName, ciName, testType, coverage, corrName)
								out[k] = record(st.results, {'correctionInfo': clean(st.results.multCompCorrectionInfo)})
								if corrName == 'NoCorrection' and ciName == SAMPLE_CI[0] and testType == 'Two-sided':
									es1 = load('stamp.plugins.samples.effectSizeFilters.DiffBetweenProp', 'DiffBetweenProp')
									es2 = load('stamp.plugins.samples.effectSizeFilters.RatioProportions', 'RatioProportions')
									es3 = load('stamp.plugins.samples.effectSizeFilters.OddsRatio', 'OddsRatio')
									filters = {
										'p05': (0.05, None, None, None, None, None, None, None, None, 'OR', None, None),
										'p05_seqmax10': (0.05, 'maximum', 10, None, None, None, None, None, None, 'OR', None, None),
										'seqmin10': (None, 'minimum', 10, None, None, None, None, None, None, 'OR', None, None),
										'seqind_5_20': (None, 'independent', 5, 20, None, None, None, None, None, 'OR', None, None),
										'parentmax100': (None, None, None, None, 'maximum', 100, None, None, None, 'OR', None, None),
										'parentind_50_50': (None, None, None, None, 'independent', 50, 50, None, None, 'OR', None, None),
										'dp1': (None, None, None, None, None, None, None, es1, 1.0, 'OR', None, None),
										'rp2': (None, None, None, None, None, None, None, es2, 2.0, 'OR', None, None),
										'or2': (None, None, None, None, None, None, None, es3, 2.0, 'OR', None, None),
										'dp1_OR_rp2': (None, None, None, None, None, None, None, es1, 1.0, 'OR', es2, 2.0),
										'dp1_AND_rp2': (None, None, None, None, None, None, None, es1, 1.0, 'AND', es2, 2.0),
										'p05_dp05_AND_rp15': (0.05, None, None, None, None, None, None, es1, 0.5, 'AND', es2, 1.5),
									}
									for fname, args in filters.items():
										st.results.filterFeatures(*args)
										out[k + '/filter/' + fname] = {'active': clean(list(st.results.getActiveFeatures()))}
									st.results.setSelectedFeatures(list(profile.getFeatures())[:5])
									st.results.filterFeatures(None, None, None, None, None, None, None, None, None, 'OR', None, None)
									out[k + '/filter/selected5'] = {'active': clean(list(st.results.getActiveFeatures()))}
									st.results.selectAllFeautres()
			for testName in SAMPLE_TESTS_RANDOM:
				test = load('stamp.plugins.samples.statisticalTests.' + testName, testName)
				ci = load('stamp.plugins.samples.confidenceIntervalMethods.' + SAMPLE_CI[0], SAMPLE_CI[0])
				random.seed(1); numpy.random.seed(1)
				st = SampleStatsTests(prefs)
				st.run(test, 'Two-sided', ci, 0.95, profile)
				st.results.performMultCompCorrection(load('stamp.plugins.common.multipleComparisonCorrections.NoCorrection', 'NoCorrection'))
				st.results.filterFeatures(None, None, None, None, None, None, None, None, None, 'OR', None, None)
				out['%s/%s|random' % (key, testName)] = record(st.results)

	# ---- two groups
	for field in [groupField, groupField2]:
		metadata.setActiveField(field, tree)
		groups = sorted(tree.groupDict.keys())
		out['%s/groups/%s/groupDict' % (name, field)] = clean(dict((g, sorted(tree.groupDict[g])) for g in groups))
		out['%s/groups/%s/numSequencesInGroup' % (name, field)] = clean(dict((g, tree.numSequencesInGroup(g, metadata)) for g in groups))
		pairs = [(groups[0], groups[1]), (groups[0], '<All other samples>')]
		for parent, level in configs:
			for g1, g2 in pairs:
				profile = tree.createGroupProfile(g1, g2, parent, level, metadata, UNCLASSIFIED[1])
				key = '%s/groups/%s|%s|%s|%s|%s' % (name, field, parent, level, g1, g2)
				out[key + '/profile'] = {'features': clean(profile.getFeatures()),
					'counts': clean([profile.getFeatureCounts(f) for f in profile.getFeatures()]),
					'parentCounts': clean([profile.getParentFeatureCounts(f) for f in profile.getFeatures()]),
					'proportions': clean([profile.getFeatureProportions(f) for f in profile.getFeatures()]),
					'samplesInGroup1': clean(sorted(profile.samplesInGroup1)), 'samplesInGroup2': clean(sorted(profile.samplesInGroup2))}
				if (parent, level) != configs[0] and field != groupField:
					continue
				for testName in GROUP_TESTS:
					test = load('stamp.plugins.groups.statisticalTests.' + testName, testName)
					for testType in ['Two-sided', 'One-sided']:
						for coverage in [0.95, 0.99]:
							if (testType == 'One-sided' or coverage == 0.99) and (parent, level) != configs[0]:
								continue
							st = GroupStatsTests(prefs)
							st.run(test, testType, test.confIntervMethods[0], coverage, profile)
							for corrName in (CORRECTIONS if testType == 'Two-sided' and coverage == 0.95 else CORRECTIONS[:1]):
								corr = load('stamp.plugins.common.multipleComparisonCorrections.' + corrName, corrName)
								st.results.performMultCompCorrection(corr)
								st.results.filterFeatures(None, None, None, None, None, None, None, None, None, 'OR', None, None)
								k = '%s/%s|%s|%s|%s' % (key, testName, testType, coverage, corrName)
								out[k] = record(st.results, {'correctionInfo': clean(st.results.multCompCorrectionInfo)})
								if corrName == 'NoCorrection' and testType == 'Two-sided' and coverage == 0.95:
									es1 = load('stamp.plugins.groups.effectSizeFilters.DiffBetweenProp', 'DiffBetweenProp')
									es2 = load('stamp.plugins.groups.effectSizeFilters.RatioProportions', 'RatioProportions')
									filters = {
										'p05': (0.05, None, None, None, None, None, None, None, None, 'OR', None, None),
										'p05_seqmax10': (0.05, 'maximum', 10, None, None, None, None, None, None, 'OR', None, None),
										'seqmin10': (None, 'minimum', 10, None, None, None, None, None, None, 'OR', None, None),
										'seqind_5_20': (None, 'independent', 5, 20, None, None, None, None, None, 'OR', None, None),
										'parentmax100': (None, None, None, None, 'maximum', 100, None, None, None, 'OR', None, None),
										'dp1': (None, None, None, None, None, None, None, es1, 1.0, 'OR', None, None),
										'rp2': (None, None, None, None, None, None, None, es2, 2.0, 'OR', None, None),
										'dp1_OR_rp2': (None, None, None, None, None, None, None, es1, 1.0, 'OR', es2, 2.0),
										'dp1_AND_rp2': (None, None, None, None, None, None, None, es1, 1.0, 'AND', es2, 2.0),
										'p05_dp05_AND_rp15': (0.05, None, None, None, None, None, None, es1, 0.5, 'AND', es2, 1.5),
									}
									for fname, args in filters.items():
										st.results.filterFeatures(*args)
										out[k + '/filter/' + fname] = {'active': clean(list(st.results.getActiveFeatures()))}
				if (parent, level) == configs[0] and g2 != '<All other samples>':
					for testName in GROUP_TESTS_RANDOM:
						test = load('stamp.plugins.groups.statisticalTests.' + testName, testName)
						if min(len(profile.samplesInGroup1), len(profile.samplesInGroup2)) < 8:
							out['%s/%s|random' % (key, testName)] = {'skipped': 'group with fewer than 8 samples (upstream crashes)'}
							continue
						random.seed(1); numpy.random.seed(1)
						st = GroupStatsTests(prefs)
						st.run(test, 'Two-sided', test.confIntervMethods[0], 0.95, profile)
						st.results.performMultCompCorrection(load('stamp.plugins.common.multipleComparisonCorrections.NoCorrection', 'NoCorrection'))
						st.results.filterFeatures(None, None, None, None, None, None, None, None, None, 'OR', None, None)
						out['%s/%s|random' % (key, testName)] = record(st.results)

	# ---- multiple groups
	for field in [groupField, groupField2]:
		metadata.setActiveField(field, tree)
		for parent, level in configs:
			profile = tree.createMultiGroupProfile(list(tree.groupDict.keys()), parent, level, metadata, UNCLASSIFIED[1])
			key = '%s/multi/%s|%s|%s' % (name, field, parent, level)
			out[key + '/profile'] = {'features': clean(profile.getFeatures()), 'activeGroupNames': clean(profile.activeGroupNames),
				'activeSamplesInGroups': clean(profile.activeSamplesInGroups),
				'counts': clean([profile.getActiveFeatureCounts(f) for f in profile.getFeatures()]),
				'parentCounts': clean([profile.getActiveParentCounts(f) for f in profile.getFeatures()]),
				'proportions': clean([profile.getActiveFeatureProportions(f) for f in profile.getFeatures()])}
			if (parent, level) != configs[0] and field != groupField:
				continue
			for testName in MULTI_TESTS:
				test = load('stamp.plugins.multiGroups.statisticalTests.' + testName, testName)
				for esName in MULTI_ES:
					es = load('stamp.plugins.multiGroups.effectSizeFilters.' + esName, esName)
					st = MultiGroupStatsTests(prefs)
					st.run(test, es, profile)
					for corrName in (CORRECTIONS if testName == 'ANOVA' else CORRECTIONS[:1]):
						corr = load('stamp.plugins.common.multipleComparisonCorrections.' + corrName, corrName)
						st.results.performMultCompCorrection(corr)
						st.results.filterFeatures(None, None, None)
						k = '%s/%s|%s|%s' % (key, testName, esName, corrName)
						out[k] = record(st.results, {'correctionInfo': clean(st.results.multCompCorrectionInfo)})
						if corrName == 'NoCorrection':
							for fname, args in {'p05': (0.05, None, None), 'eta01': (None, es, 0.1), 'p05_eta005': (0.05, es, 0.05)}.items():
								st.results.filterFeatures(*args)
								out[k + '/filter/' + fname] = {'active': clean(list(st.results.getActiveFeatures()))}
							st.results.filterFeatures(None, None, None)
					if testName == 'ANOVA' and (parent, level) == configs[0]:
						features = [row[0] for row in st.results.data[:3]]
						for phName in POSTHOC:
							ph = load('stamp.plugins.multiGroups.postHoc.' + phName, phName)
							for feature in features:
								for coverage in [0.95, 0.99]:
									st.runPostHocTest(ph, profile, feature, coverage)
									r = st.results.postHocResults
									out['%s/posthoc/%s|%s|%s' % (key, phName, feature, coverage)] = clean({
										'pValues': r.pValues, 'effectSizes': r.effectSizes, 'lowerCIs': r.lowerCIs, 'upperCIs': r.upperCIs,
										'labels': r.labels, 'note': r.note, 'alpha': r.alpha})

with open(outPath, 'w') as f:
	json.dump(out, f, sort_keys=True, indent=0, separators=(',', ':'))
print('wrote', outPath, len(out), 'entries')
