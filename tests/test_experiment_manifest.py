import copy
import unittest

from fundamental_analysis.experiment_manifest import load_experiment_manifest, validate_experiment_manifest


class ExperimentManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_experiment_manifest()

    def test_revised_manifest_matches_registry(self):
        self.assertEqual(self.manifest["manifest_version"], "1.1")
        self.assertEqual(validate_experiment_manifest(self.manifest), [])

    def test_old_distribution_rejected_even_with_same_total(self):
        groups = self.manifest["universe"]["groups"]
        groups["tradicionais_ciclicas"]["expected_count"] = 12
        groups["fcf_negativo_early_growth"]["expected_count"] = 17
        errors = validate_experiment_manifest(self.manifest)
        self.assertEqual(sum("contagem do grupo" in error for error in errors), 2)

    def test_missing_extra_and_malformed_groups_rejected(self):
        for value in ({}, None, {"inventado": {"expected_count": 50}}):
            with self.subTest(value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["universe"]["groups"] = value
                self.assertTrue(validate_experiment_manifest(manifest))

    def test_wrong_total_rejected(self):
        self.manifest["universe"]["expected_total_companies"] = 49
        self.assertIn("total do universo diverge do cadastro", validate_experiment_manifest(self.manifest))

