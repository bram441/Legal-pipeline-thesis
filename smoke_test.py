from idp_engine import IDP
from idp_engine.Run import model_check, model_expand

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

def main():
    kb = IDP.from_str(FO_CODE)
    T_block, S_block = kb.get_blocks("T, S")

    print("model_check(T,S) =", model_check(T_block, S_block))

    print("\n=== model_expand(T,S) output ===")
    for chunk in model_expand(T_block, S_block, max=5, timeout_seconds=5):
        print(chunk)

if __name__ == "__main__":
    main()
