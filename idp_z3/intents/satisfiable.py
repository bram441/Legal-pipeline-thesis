from idp_z3.tasks import satisfiable_check

def run(case, base_kb_text, query):
    out = satisfiable_check(case, base_kb_text=base_kb_text)
    sat = bool(out.get("sat"))
    return sat, {"sat": sat}
