from pydantic import BaseModel


class HostedLLMClient:
    """Hosted API: karmaşık veya düşük güvenli işler."""

    name = "hosted"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError
