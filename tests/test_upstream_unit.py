"""Run upstream STAMP_test.py (33 unittest cases) under pytest, unchanged.

conftest.py puts stamp/ on sys.path, so the upstream module imports as `STAMP_test`;
pytest collects the unittest.TestCase classes re-exported here.
"""
import unittest

import STAMP_test
from STAMP_test import (  # noqa: F401  (collected by pytest)
	VerifyPostHocTests,
	VerifyStatisticalTests,
	VerifyEffectSizeFilters,
	VerifyConfidenceIntervalMethods,
	VerifyMultipleComparisonCorrectionMethods,
	VerifyOther,
)


def test_upstream_suite_has_33_tests():
	suite = unittest.defaultTestLoader.loadTestsFromModule(STAMP_test)
	assert suite.countTestCases() == 33
