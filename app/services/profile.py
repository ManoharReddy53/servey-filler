from app.models.domain import ProfileFact


class ProfileFacts:
    def __init__(self, facts: list[ProfileFact] | None = None) -> None:
        self._facts = {fact.key: fact for fact in facts or [] if fact.verified}

    def get(self, key: str) -> ProfileFact | None:
        return self._facts.get(key)

    def all(self) -> list[ProfileFact]:
        return list(self._facts.values())
