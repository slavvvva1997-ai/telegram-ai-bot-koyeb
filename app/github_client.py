import httpx


class GitHubService:
    def __init__(self, token: str, repo: str) -> None:
        self.token = token
        self.repo = repo

    @property
    def configured(self) -> bool:
        return bool(self.token and self.repo and "/" in self.repo)

    async def create_issue(self, title: str, body: str) -> str:
        if not self.configured:
            raise RuntimeError("GITHUB_TOKEN или GITHUB_REPO не настроены.")

        url = f"https://api.github.com/repos/{self.repo}/issues"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"title": title[:240], "body": body, "labels": ["cursor-task"]}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["html_url"]
