import requests
import time


class JiraClient:
    def __init__(
        self,
        base_url: str,
        email: str | None = None,
        api_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        auth_method: str = "token",
        api_version: str = "3",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.api_version = (api_version or "3").strip()

        method = (auth_method or "token").lower()
        if method == "basic":
            if not username or not password:
                raise ValueError("Basic 认证需要提供 JIRA_USERNAME 与 JIRA_PASSWORD")
            self.session.auth = (username, password)
        else:
            if not email or not api_token:
                raise ValueError("Token 认证需要提供 JIRA_EMAIL 与 JIRA_API_TOKEN")
            self.session.auth = (email, api_token)

    def search_issues(self, jql: str, max_results: int = 50, retries: int = 3) -> list[dict]:
        url = f"{self.base_url}/rest/api/{self.api_version}/search"
        params = {"jql": jql, "maxResults": max_results}
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                return data.get("issues", [])
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(1.0 * attempt)
        if last_exc:
            raise last_exc
        return []

    def list_fields(self, retries: int = 3) -> list[dict]:
        url = f"{self.base_url}/rest/api/{self.api_version}/field"
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(1.0 * attempt)
        if last_exc:
            raise last_exc
        return []