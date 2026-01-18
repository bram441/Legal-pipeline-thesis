# idp_backend.py
from idp_engine import IDP
from idp_engine.Run import model_check, model_expand

# Executes an FO(.) program with IDP-Z3 and returns satisfiability + expanded models.
# This is the low-level backend wrapper around IDP.from_str, model_check, and model_expand.
# It is intentionally generic: it does not assume any particular legal domain predicates.
#
# Params:
#   fo_code (str): Full FO(.) program as a string (vocabulary + theory + structure).
#   theory_name (str | None): Optional name of the theory to check/expand (if your FO code contains multiple theories).
#   struct_name (str | None): Optional name of the structure to use (if your FO code contains multiple structures).
#   max_models (int): Maximum number of models to expand/return.
#   timeout_seconds (int | None): Optional timeout guard for IDP operations.
#
# Returns:
#   dict: A result dictionary with:
#     - "sat" (bool): Whether the theory is satisfiable in the given structure.
#     - "models" (list[str]): One or more expanded model(s) rendered as text.
#     - optionally other debug fields depending on your implementation.

def run_idp(fo_code, theory_name="T", struct_name="S", max_models=10, timeout_seconds=5):
    kb = IDP.from_str(fo_code)

    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]

    S = kb.structures[struct_name]

    sat_status = model_check(*theories, S)

    models = []
    for chunk in model_expand(*theories, S, max=max_models, timeout_seconds=timeout_seconds):
        models.append(chunk)

    return {"sat": sat_status == "sat", "models": models}



if __name__ == "__main__":
    # Very small self-test, reusing the likes example.
    FO_CODE = """
    vocabulary V {
      type Person
      likes: Person -> Bool
    }

    structure S:V {
      Person := {alice, bob}.
    }

    theory T:V {
      ? p in Person: likes(p).
    }
    """

    result = run_idp(FO_CODE)
    print("SAT?", result["sat"])
    print("\n--- MODELS ---")
    for m in result["models"]:
        print(m)
