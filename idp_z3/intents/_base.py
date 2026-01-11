class IntentNotImplemented(Exception):
    pass


def not_implemented(intent_name):
    return None, {"error": "intent_not_implemented", "intent": intent_name}
