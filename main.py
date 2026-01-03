import json

from pipeline.pipeline import answer_legal_prompt
from dotenv import load_dotenv



def main():
    case_text = (
        "Alice was speeding and crashed into Bob's parked car. "
        "Alice clearly violated the traffic rules and admits fault. "
        "Bob's car suffered significant damage."
    )

    questions = [
        "Who is liable?",
        "Is Alice liable?",
        "Why is Alice liable? Please explain.",
    ]

    for q in questions:
        print("\n---")
        print("Q:", q)
        result = answer_legal_prompt(case_text, q)

        print("SAT?", result["sat"])
        print("Case:", json.dumps(result["case"], indent=2))
        print("Query:", json.dumps(result["query"], indent=2))
        print("Answer:", result["natural_language"])

        if result["explanation"]:
            print("Explanation:\n" + result["explanation"])


if __name__ == "__main__":
    load_dotenv()
    main()
