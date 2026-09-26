from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.notification_service import (
    build_notification_payloads,
    get_registered_mobile_tokens,
    get_registered_tokens,
    get_registered_web_tokens,
    register_device_token,
    register_mobile_token,
    register_web_token,
    send_notifications_to_registered_devices,
    send_test_push,
)

app = FastAPI(title="StudySync Notification Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeviceTokenRequest(BaseModel):
    token: str
    device_type: str = "mobile"


class TestNotificationRequest(BaseModel):
    token: str
    title: str = "StudySync test"
    body: str = "Thông báo thử từ backend."
    device_type: str = "mobile"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "StudySync Notification Backend"}


# The registration endpoint is shared by both web and phone clients:
# - web clients: browser Notification API obtains a token and send device_type="web"
# - mobile clients: Android/iOS app obtains an FCM token and send device_type="mobile"
@app.post("/device/register")
def register_device(payload: DeviceTokenRequest) -> dict[str, Any]:
    if payload.device_type == "web":
        tokens = register_web_token(payload.token)
    else:
        tokens = register_mobile_token(payload.token)
    return {"status": "registered", "device_type": payload.device_type, "tokens": tokens}


@app.get("/device/tokens")
def list_tokens() -> dict[str, Any]:
    return {
        "all": get_registered_tokens(),
        "web": get_registered_web_tokens(),
        "mobile": get_registered_mobile_tokens(),
    }


@app.get("/notifications/payloads")
def preview_notifications() -> dict[str, Any]:
    return {"notifications": build_notification_payloads()}


@app.post("/notifications/test")
def test_notification(payload: TestNotificationRequest) -> dict[str, Any]:
    return send_test_push(payload.token, payload.title, payload.body, device_type=payload.device_type)


@app.post("/notifications/send")
def send_now() -> dict[str, Any]:
    return {"notifications": send_notifications_to_registered_devices()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000, reload=True)
