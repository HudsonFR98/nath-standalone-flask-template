import json
import unittest

from ..generation import GenerationResolver, StateSnapshot


def show_json(resources):
    return json.dumps({"format_version": "1.0", "values": {"root_module": {"resources": resources}}})


VM = {"address": "proxmox_virtual_environment_vm.app", "values": {"name": "serv-nath-nsft-prod-02"}}


def counter(value):
    return {"address": "terraform_data.generation", "values": {"input": value, "output": value}}


class StateSnapshotTests(unittest.TestCase):
    def test_empty_state(self):
        snapshot = StateSnapshot.from_show_json(json.dumps({"format_version": "1.0"}))
        self.assertFalse(snapshot.vm_present)
        self.assertIsNone(snapshot.stored_generation)

    def test_full_state(self):
        snapshot = StateSnapshot.from_show_json(show_json([VM, counter(2)]))
        self.assertTrue(snapshot.vm_present)
        self.assertEqual(snapshot.stored_generation, 2)

    def test_counter_only(self):
        snapshot = StateSnapshot.from_show_json(show_json([counter(3)]))
        self.assertFalse(snapshot.vm_present)
        self.assertEqual(snapshot.stored_generation, 3)

    def test_accepts_dict_payload_and_float_generation(self):
        snapshot = StateSnapshot.from_show_json({"values": {"root_module": {"resources": [counter(4.0)]}}})
        self.assertEqual(snapshot.stored_generation, 4)


class GenerationResolverTests(unittest.TestCase):
    def test_fresh_state_returns_seed(self):
        self.assertEqual(GenerationResolver(seed=7).resolve(StateSnapshot(False, None)), 7)

    def test_live_vm_keeps_generation(self):
        self.assertEqual(GenerationResolver().resolve(StateSnapshot(True, 2)), 2)

    def test_destroyed_vm_increments(self):
        self.assertEqual(GenerationResolver().resolve(StateSnapshot(False, 2)), 3)

    def test_seed_ignored_once_state_exists(self):
        self.assertEqual(GenerationResolver(seed=9).resolve(StateSnapshot(True, 2)), 2)

    def test_rejects_invalid_seed(self):
        with self.assertRaises(ValueError):
            GenerationResolver(seed=0)


if __name__ == "__main__":
    unittest.main()
