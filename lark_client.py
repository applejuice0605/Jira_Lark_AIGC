import requests
import time


class LarkClient:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def _post(self, payload: dict, retries: int = 3, backoff_sec: float = 1.0) -> dict:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(self.webhook_url, json=payload, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(backoff_sec * attempt)
        raise last_exc  # type: ignore

    def send_text(self, text: str) -> dict:
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._post(payload)

    def send_post(self, title: str, lines: list[str]) -> dict:
        content = [[{"tag": "text", "text": "\n".join(lines)}]]
        payload = {
            "msg_type": "post",
            "content": {"post": {"zh_cn": {"title": title, "content": content}}},
        }
        return self._post(payload)

    def send_post_content(self, title: str, content: list[list[dict]]) -> dict:
        payload = {
            "msg_type": "post",
            "content": {"post": {"zh_cn": {"title": title, "content": content}}},
        }
        return self._post(payload)

    def send_interactive_card(self, card: dict) -> dict:
        payload = {
            "msg_type": "interactive",
            "card": card,
        }
        return self._post(payload)