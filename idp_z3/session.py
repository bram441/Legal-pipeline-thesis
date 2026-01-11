# idp_z3/session.py

from .legal_kb import build_fo_program, parse_liable_from_models
from .idp_backend import run_idp


class CaseSession:
    """
    Holds the compiled+expanded result for one (baseKB + case facts) instance.
    Reuse this to answer multiple questions about the same case.
    """

    def __init__(self, case):
        self.case = case
        self._ran = False
        self._sat = None
        self._models = None
        self._cache = {}

    def run(self):
        if self._ran:
            return

        parties = self.case["parties"]
        negligent = self.case["negligent"]
        caused_damage = self.case["caused_damage"]

        fo_code = build_fo_program(parties, negligent, caused_damage)
        result = run_idp(fo_code, max_models=5)

        self._sat = result["sat"]
        self._models = result["models"]
        self._ran = True

    @property
    def sat(self):
        self.run()
        return self._sat

    def liable_set(self):
        """
        First cached derived predicate.
        Extend later with other query types/predicates.
        """
        self.run()

        if not self._sat:
            return set()

        if "liable_set" not in self._cache:
            self._cache["liable_set"] = parse_liable_from_models(self._models)

        return self._cache["liable_set"]
