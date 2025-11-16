# idp_backend.py
from idp_engine import IDP
from idp_engine.Run import model_check, model_expand


def run_idp(fo_code, theory_name="T", struct_name="S", max_models=10, timeout_seconds=5):
    """
    Run IDP-Z3 model_check + model_expand on a FO(.) program.

    Returns a dict:
      {
        "sat": bool,
        "models": [str, ...],   # pretty-printed models + final message
      }
    """
    kb = IDP.from_str(fo_code)

    # Access blocks by name (simpler than get_blocks for now)
    T = kb.theories[theory_name]
    S = kb.structures[struct_name]

    sat_status = model_check(T, S)

    models = []
    for chunk in model_expand(T, S, max=max_models, timeout_seconds=timeout_seconds):
        models.append(chunk)

    return {
        "sat": sat_status == "sat",
        "models": models,
    }


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
