LEGAL_VOCAB_AND_RULES = """
vocabulary V {
  type Party
  negligent: Party -> Bool
  causedDamage: Party -> Bool
  liable: Party -> Bool
}

theory T:V {
  // A party is liable iff they are negligent and caused damage
  ! p in Party: liable(p) <=> negligent(p) & causedDamage(p).
}
"""
