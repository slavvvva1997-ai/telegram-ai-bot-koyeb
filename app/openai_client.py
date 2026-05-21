from openai import AsyncOpenAI

from app.prompts import SYSTEM_PROMPTS
from app.storage import ChatMemory


class OpenAIService:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def answer(self, mode: str, user_text: str, memory: ChatMemory) -> str:
        if self._client is None:
            return "OPENAI_API_KEY не настроен. Добавьте ключ в переменные окружения хостинга."

        system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["general"])
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if memory.summary:
            messages.append({"role": "system", "content": f"Короткое резюме прошлого диалога: {memory.summary}"})
        messages.extend(memory.messages[-5:])
        messages.append({"role": "user", "content": user_text})

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=1200,
        )
        content = response.choices[0].message.content or ""
        return content.strip() or "Не получилось получить ответ от AI."
