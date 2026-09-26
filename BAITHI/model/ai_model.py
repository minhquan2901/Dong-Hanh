from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _setting(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        secret_value = st.secrets.get(name, default)
        return str(secret_value).strip()
    except Exception:
        return default


class AIModel:
    """Kết nối Gemini hoặc API tương thích OpenAI."""

    def __init__(self) -> None:
        self.api_key = _setting("AI_API_KEY")
        self.provider = _setting("AI_PROVIDER", "openai").lower()
        self.api_url = _setting(
            "AI_API_URL", "https://api.openai.com/v1/chat/completions"
        )
        self.model_name = _setting("AI_MODEL", "gpt-4o-mini")
        if self.provider == "gemini":
            self.api_url = _setting(
                "GEMINI_API_URL",
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            )
            self.model_name = _setting("GEMINI_MODEL", "gemini-3.8-flash")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and self.api_key not in {
            "PASTE_A_NEW_KEY_HERE",
            "your_api_key_here",
        }

    @property
    def configuration_error(self) -> str:
        if not self.is_configured:
            return "Chưa cấu hình AI_API_KEY trong file .env."
        if self.provider not in {"openai", "gemini"}:
            return "AI_PROVIDER phải là openai hoặc gemini trong file .env."
        if self.provider == "openai" and "api.openai.com" in self.api_url and not self.api_key.startswith("sk-"):
            return "AI_API_KEY không phải key OpenAI. Hãy đặt AI_PROVIDER=gemini nếu bạn dùng key Gemini."
        return ""

    def _gemini_payload(self, messages: list[dict[str, str]]) -> bytes:
        tutor_instruction = (
            "Bạn là StudySync, một gia sư Socratic thân thiện cho học sinh 10-18 tuổi. "
            "Mục tiêu là giúp người học tự tư duy, không làm bài thay. "
            "Không đưa đáp án cuối cùng ngay khi người học chỉ gửi đề bài. "
            "Hãy hỏi một câu gợi mở ở mỗi bước, chia bài thành các bước nhỏ, "
            "yêu cầu người học thử bước tiếp theo rồi mới phản hồi. "
            "Nếu người học trả lời sai, chỉ rõ sai ở bước nào, giải thích vì sao sai "
            "bằng ngôn ngữ dễ hiểu, sau đó đưa một ví dụ tương tự đơn giản hơn để họ tự làm. "
            "Có thể dùng gợi ý từng phần, công thức liên quan và cách tự kiểm tra, "
            "nhưng không tiết lộ kết quả cuối cùng trước khi người học đã trình bày cách làm. "
            "Nếu người học đã làm gần đúng, hãy khen điểm đúng và chỉ gợi ý phần cần sửa. "
            "Luôn trả lời bằng tiếng Việt, ngắn gọn, tích cực và không phán xét."
        )
        contents = [
            {
                "role": "model" if item["role"] == "assistant" else "user",
                "parts": [{"text": item["content"]}],
            }
            for item in messages[-12:]
        ]
        return json.dumps({
            "system_instruction": {
                "parts": [{"text": tutor_instruction}]
            },
            "contents": contents,
            "generationConfig": {"temperature": 0.7},
        }).encode("utf-8")

    def _local_tutor_reply(self, messages: list[dict[str, str]]) -> str:
        question = messages[-1].get("content", "") if messages else "câu hỏi này"
        return (
            "Gemini đang quá tải nên mình chưa thể trả lời tự động. "
            f"Bạn hãy thử viết dữ kiện đã biết và bước đầu tiên cho '{question[:100]}'. "
            "Mình sẽ giúp kiểm tra cách suy luận, giải thích chỗ sai và gợi ý bước tiếp theo, "
            "không đưa đáp án ngay."
        )

    def reply(self, messages: list[dict[str, str]]) -> str:
        if self.configuration_error:
            return self.configuration_error

        if self.provider == "gemini":
            endpoints = [
                f"{self.api_url}?key={self.api_key}",
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}",
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={self.api_key}",
            ]
            payload = self._gemini_payload(messages)
            headers = {"Content-Type": "application/json"}
        else:
            tutor_instruction = (
                "Bạn là StudySync, gia sư Socratic cho học sinh 10-18 tuổi. "
                "Không đưa đáp án cuối cùng ngay; hãy đặt câu hỏi gợi mở, chia nhỏ cách suy nghĩ "
                "và yêu cầu học sinh tự làm từng bước. Khi học sinh sai, chỉ rõ bước sai, giải thích "
                "vì sao, rồi đưa ví dụ tương tự để học sinh tự giải. Chỉ đưa đáp án sau khi học sinh đã "
                "trình bày nỗ lực và xác nhận muốn xem lời giải. Luôn trả lời tiếng Việt, tích cực và dễ hiểu."
            )
            endpoints = [self.api_url]
            payload = json.dumps(
                {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": tutor_instruction},
                        *messages[-12:],
                    ],
                    "temperature": 0.7,
                }
            ).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        try:
            result = None
            last_error = None
            for endpoint in endpoints:
                for attempt in range(2):
                    api_request = request.Request(endpoint, data=payload, headers=headers, method="POST")
                    try:
                        with request.urlopen(api_request, timeout=45) as response:
                            result = json.loads(response.read().decode("utf-8"))
                        break
                    except HTTPError as error:
                        last_error = error
                        if error.code != 503 or attempt == 1:
                            break
                        time.sleep(1.5 * (attempt + 1))
                if result is not None:
                    break
            if result is None and last_error is not None:
                raise last_error
            if result is None:
                return self._local_tutor_reply(messages)
            if self.provider == "gemini":
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
            return result["choices"][0]["message"]["content"].strip()
        except HTTPError as error:
            try:
                detail = error.read().decode("utf-8", errors="replace")
                provider_message = json.loads(detail).get("error", {}).get("message", detail)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                provider_message = "Nhà cung cấp không trả về chi tiết lỗi."
            if error.code == 429:
                return (
                    "AI đã được cấu hình nhưng tài khoản hiện hết hạn mức. Hãy kiểm tra Billing/Quota của nhà cung cấp "
                    "rồi khởi động lại server."
                )
            if error.code == 503 and self.provider == "gemini":
                return self._local_tutor_reply(messages)
            return f"StudySync chưa nhận được phản hồi từ AI (HTTP {error.code}). {provider_message}"
        except URLError as error:
            return f"StudySync không kết nối được tới AI: {error.reason}."
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            return f"StudySync nhận dữ liệu AI không đúng định dạng ({type(error).__name__})."
